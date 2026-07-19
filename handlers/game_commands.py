"""后室:逃出生天 — 游戏流程命令混入

处理核心游戏循环命令：开始游戏、楼层探索、基地探索、寻找出口、回溯楼层。
"""

from __future__ import annotations

import random
from typing import Any

from .base import HandlerBase
from ..core.game_data import EXPLORE_EVENTS
from ..core.player_state import PlayerState
from ..core.state_machine import GameEvent


class GameCommandMixin(HandlerBase):
    """核心游戏流程命令处理器混入。

    提供探索与出口相关的全部 ``_do_*`` 方法。
    """

    async def _do_start(self, stream_id: str) -> None:
        """开始新游戏。"""
        user_id = str(stream_id)
        player = PlayerState(
            user_id=user_id,
            current_level=0,
            health=self.config.game.initial_health,
            sanity=self.config.game.initial_sanity,
            inventory=[],
        )
        player.fsm.apply(GameEvent.START)
        self._players[user_id] = player
        self._save_player(user_id)
        player.visited_levels.add(0)

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_start(ctx)
        await self._send_game_event(stream_id, event_text, player)

    async def _do_use_item(self, stream_id: str, item_index: int) -> None:
        """使用背包物品（按编号）。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if item_index < 1 or item_index > len(player.inventory):
            await self._send(
                stream_id,
                self._renderer.render_item_not_found(str(item_index)),
            )
            return

        item = player.inventory.pop(item_index - 1)

        cfg = self.config.game
        effect = item.get("effect", "")
        value = item.get("value", 0)

        old_health = player.health
        old_sanity = player.sanity

        if effect == "health_restore":
            player.health = min(cfg.initial_health, player.health + value)
        elif effect == "sanity_restore":
            player.sanity = min(cfg.initial_sanity, player.sanity + value)

        ctx = self._make_ctx(player)
        remaining = [i.get("display_name", i["name"]) for i in player.inventory]

        event_text = self._renderer.render_use_item(item, ctx, remaining, old_health, old_sanity)
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    async def _do_explore(self, stream_id: str) -> None:
        """探索当前楼层。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if player.current_level == 399:
            await self._send(stream_id, self._renderer.render_already_at_399())
            return

        cfg = self.config.game
        player.sanity = max(0, player.sanity - cfg.explore_sanity_cost)

        level_info = self._get_level_info(player.current_level)

        # 随机事件
        event = random.choice(EXPLORE_EVENTS)
        event_text = event["text"]
        crate_result: tuple[str, list[dict]] | None = None
        health_cost: int | None = None
        note_found = False

        if event["type"] == "discovery":
            if event.get("give_item"):
                crate_result = self._roll_crate(player)
                if crate_result:
                    _, crate_items = crate_result
                    for it in crate_items:
                        player.inventory.append(it)
                else:
                    event_text += "……但里面已经空了。"
        elif event["type"] == "danger":
            if "health_cost" in event:
                health_cost = event["health_cost"]
                if self._has_item(player, "o2"):
                    health_cost = max(0, health_cost - 5)
                    self._use_item(player, "o2")
                player.health = max(0, player.health - health_cost)
        elif event["type"] == "found_note":
            note_text = self._story_manager.get_random_story()
            if note_text:
                player.pending_note = note_text
                note_found = True

        # 随机遭遇实体
        danger_modifier = {"低": 0.5, "中": 1.0, "高": 1.5, "极高": 2.0}
        encounter_chance = cfg.entity_encounter_chance * danger_modifier.get(level_info["danger"], 1.0)
        entity_encounter: tuple | None = None

        from ..core.game_data import ENTITIES
        if random.random() < encounter_chance and level_info.get("entities"):
            entity_name = random.choice(level_info["entities"])
            entity_data = ENTITIES.get(entity_name)
            if entity_data:
                edamage = entity_data["damage"]
                if self._has_item(player, "o3"):
                    if entity_name in ("笑魇", "猎犬"):
                        edamage = 0
                    else:
                        edamage = max(0, edamage - 10)
                if edamage > 0:
                    if self._has_item(player, "o2"):
                        edamage = max(0, edamage - 5)
                        self._use_item(player, "o2")
                    player.health = max(0, player.health - edamage)
                entity_encounter = (entity_name, entity_data, edamage)

        # Level 1 特殊：在 M.E.G.CN Alpha 基地遇到角色
        char_encounter: tuple[str, str, str | None, str | None, int, int] | None = None
        result = self._char_encounter_service.roll_encounter(
            level=player.current_level,
            unlocked_chars=player.unlocked_chars,
            player_state=player,
            people_story_manager=self._people_manager,
            quest_manager=self._quest_manager,
            ankexin_task_chance=cfg.ankexin_task_chance,
            favorability_per_encounter=cfg.favorability_per_encounter,
            consecutive_misses=player.consecutive_misses,
        )
        if result is not None:
            char_encounter = (
                result.char_id, result.story_text,
                result.gift_text, result.quest_offer,
                result.favorability_increase, result.current_favorability,
            )
            player.consecutive_misses = 0
        else:
            player.consecutive_misses += 1

        # 理智值过低效果
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        # Level 1 基地工作：每探索 work_trigger_interval 次触发安可欣日常任务
        work_triggered = False
        work_assigned: tuple[str, str] | None = None
        if player.current_level == 1:
            player.l1_explore_count += 1
            interval = cfg.work_trigger_interval
            if player.l1_explore_count >= interval:
                player.l1_explore_count = 0
                work_triggered = True
                available = self._work_manager.get_available_works(player.completed_works)
                if available:
                    wid = random.choice(available)
                    w = self._work_manager.get_work(wid)
                    if w:
                        player.available_works.add(wid)
                        work_assigned = (wid, w.get("title", wid))

        # 死亡处理
        if player.health <= 0:
            player.fsm.apply(GameEvent.DIE)
            del self._players[user_id]
            self._delete_player_save(user_id)
            ctx = self._make_ctx(player)
            event_text = self._renderer.render_explore(
                ctx, event_text, crate_result, health_cost,
                note_found, entity_encounter, char_encounter,
                work_triggered, work_assigned, companions=player.companions,
            )
            await self._send_game_event(stream_id, event_text, player)
            return

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_explore(
            ctx, event_text, crate_result, health_cost,
            note_found, entity_encounter, char_encounter,
            work_triggered, work_assigned, companions=player.companions,
        )
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    async def _do_explore_base(self, stream_id: str) -> None:
        """在 Alpha 基地内探索，遇见不同人物与场景。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        if not player.unlocked_chars:
            await self._send(stream_id, "⚠️ 你还不认识基地里的人，先使用 /br explore 探索楼层认识角色吧。")
            return

        await self._auto_end_dialog(stream_id, player)

        if player.current_level != 1:
            await self._send(stream_id, "⚠️ 你不在 Alpha 基地，无法使用基地探索命令。")
            return

        from ..core.game_data import BASE_EXPLORE_EVENTS
        cfg = self.config.game
        player.sanity = max(0, player.sanity - 1)

        event = random.choice(BASE_EXPLORE_EVENTS)
        event_area = event["area"]
        event_text = event["text"]
        item_gained: dict | None = None

        if event.get("give_item"):
            item = self._random_item()
            player.inventory.append(dict(item))
            item_gained = item

        # 角色遭遇
        char_encounter: tuple[str, str, str | None, str | None, int, int] | None = None
        result = self._char_encounter_service.roll_encounter(
            level=player.current_level,
            unlocked_chars=player.unlocked_chars,
            player_state=player,
            people_story_manager=self._people_manager,
            quest_manager=self._quest_manager,
            ankexin_task_chance=cfg.ankexin_task_chance,
            favorability_per_encounter=cfg.favorability_per_encounter,
            consecutive_misses=player.consecutive_misses,
        )
        if result is not None:
            char_encounter = (
                result.char_id, result.story_text,
                result.gift_text, result.quest_offer,
                result.favorability_increase, result.current_favorability,
            )
            player.consecutive_misses = 0
        else:
            player.consecutive_misses += 1

        # 理智值过低效果
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_explore_base(
            ctx, event_area, event_text, item_gained, char_encounter,
        )
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    # _do_exit / _do_exit_to_level 已移至 handlers/exit_commands.py
