"""后室:逃出生天 — 出口处理命令混入

处理出口相关命令：寻找出口、回溯楼层。
"""

from __future__ import annotations

import random

from .base import HandlerBase
from ..core.game_data import EXPLORE_EVENTS
from ..core.state_machine import GameEvent


class ExitCommandMixin(HandlerBase):
    """出口处理命令混入。

    提供出口搜索和楼层回溯的 ``_do_*`` 方法。
    """

    async def _do_exit(self, stream_id: str) -> None:
        """尝试寻找出口。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        cfg = self.config.game

        # Level 399 特殊处理
        if player.current_level == 399:
            await self._send(
                stream_id,
                self._renderer.render_level399_escape(player.current_level, player.companions),
            )
            del self._players[user_id]
            self._delete_player_save(user_id)
            return

        player.sanity = max(0, player.sanity - cfg.exit_search_sanity_cost)

        # 计算出口概率
        exit_chance = cfg.base_exit_chance + player.exit_attempts * cfg.exit_chance_increment
        if self._has_item(player, "o4"):
            exit_chance = 1.0
            self._use_item(player, "o4")
        if self._has_item(player, "o3"):
            exit_chance += 0.05
        if self._has_item(player, "o5"):
            exit_chance += 0.05
        if player.companions:
            exit_chance += 0.05
        exit_chance = min(exit_chance, 1.0)

        if random.random() < exit_chance:
            # 找到出口
            player.exit_attempts = 0
            from_level = player.current_level

            # Level 11 特殊：找到出口直接前往 Level 399
            if from_level == 11:
                player.current_level = 399
                await self._send(
                    stream_id,
                    self._renderer.render_level399_escape(399, player.companions),
                )
                del self._players[user_id]
                self._delete_player_save(user_id)
                return

            shortcut_desc: str | None = None

            from ..core.game_data import SHORTCUT_POOL
            old_level_info = self._get_level_info(from_level)
            level_info = self._get_level_info(player.current_level)
            shortcut = level_info.get("shortcut_to")
            if not shortcut and random.random() < 0.12 and player.current_level < 380:
                sd = random.choice(SHORTCUT_POOL)
                skip = random.randint(*sd["levels_skip"])
                shortcut = min(player.current_level + skip, 398)
                shortcut_desc = sd["description"]
            elif shortcut:
                shortcut_desc = random.choice(SHORTCUT_POOL)["description"]

            if shortcut:
                player.current_level = shortcut
                if not shortcut_desc:
                    shortcut_desc = f"你从 Level {from_level} 直接跳到了 Level {shortcut}！"
                else:
                    shortcut_desc += f"\n你从 Level {from_level} 直接跳到了 Level {shortcut}！"
            else:
                player.current_level += 1

            player.visited_levels.add(player.current_level)
            new_level_info = self._get_level_info(player.current_level)
            ctx = self._make_ctx(player)
            event_text = self._renderer.render_exit_found(
                old_level_info, ctx, new_level_info, shortcut_desc, from_level, player.companions,
            )
            await self._send_game_event(stream_id, event_text, player)

            # 检测任务进度：到达目标楼层
            for qid in list(player.active_quests):
                q = self._quest_manager.get_quest(qid)
                if q and q.get("objective_type") == "reach_level" and q.get("objective_target", 999) <= player.current_level:
                    await self._send(
                        stream_id,
                        f"📋 任务「{q['title']}」目标已达成！使用 /br quest submit {qid} 提交任务领取奖励。",
                    )
        else:
            # 没找到出口
            player.exit_attempts += 1

            event = random.choice(EXPLORE_EVENTS)
            event_text = event["text"]
            ex_crate_result: tuple[str, list[dict]] | None = None
            ex_health_cost: int | None = None
            ex_note_found = False

            if event.get("give_item"):
                ex_crate_result = self._roll_crate(player)
                if ex_crate_result:
                    _, ex_crate_items = ex_crate_result
                    for it in ex_crate_items:
                        player.inventory.append(it)
                else:
                    event_text += "……但里面已经空了。"
            if "health_cost" in event:
                ex_health_cost = event["health_cost"]
                if self._has_item(player, "o2"):
                    ex_health_cost = max(0, ex_health_cost - 5)
                    self._use_item(player, "o2")
                player.health = max(0, player.health - ex_health_cost)
            if event["type"] == "found_note":
                note_text = self._story_manager.get_random_story()
                if note_text:
                    player.pending_note = note_text
                    ex_note_found = True

            # 死亡处理
            if player.health <= 0:
                player.fsm.apply(GameEvent.DIE)
                del self._players[user_id]
                self._delete_player_save(user_id)
                ctx = self._make_ctx(player)
                event_text = self._renderer.render_exit_not_found(
                    ctx, player.exit_attempts, event_text,
                    ex_crate_result, ex_health_cost, ex_note_found,
                )
                await self._send_game_event(stream_id, event_text, player)
                return

            ctx = self._make_ctx(player)
            event_text = self._renderer.render_exit_not_found(
                ctx, player.exit_attempts, event_text,
                ex_crate_result, ex_health_cost, ex_note_found,
            )
            await self._send_game_event(stream_id, event_text, player)

        self._save_player(user_id)

    async def _do_exit_to_level(self, stream_id: str, target_level: int) -> None:
        """尝试回溯到已访问过的指定楼层。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if target_level == player.current_level:
            await self._send(stream_id, "❌ 你现在就在这个楼层，不需要回溯。")
            return

        if target_level not in player.visited_levels:
            await self._send(stream_id, f"❌ 你还没有访问过 Level {target_level}，无法回溯到那里。")
            return

        if target_level == 399:
            await self._send(stream_id, "❌ 不能直接回溯到最终出口 Level 399。")
            return

        cfg = self.config.game
        player.sanity = max(0, player.sanity - 10)

        from_level = player.current_level
        distance = abs(target_level - from_level)
        base_chance = 0.50
        familiarity_bonus = max(0, (10 - target_level) * 0.02)
        attempt_bonus = player.exit_attempts * 0.10
        total_chance = min(0.95, base_chance + familiarity_bonus + attempt_bonus)

        if random.random() < total_chance:
            old_level_info = self._get_level_info(from_level)
            player.current_level = target_level
            player.exit_attempts = 0
            player.visited_levels.add(target_level)
            new_level_info = self._get_level_info(target_level)
            ctx = self._make_ctx(player)
            event_text = (
                f"🔙 你努力回忆着来时的路，在错综复杂的后室走廊中摸索前行……\n\n"
                f"✨ 你成功了！你找到了回到 {new_level_info['title']} 的道路。\n\n"
                f"{new_level_info['description']}"
            )
            await self._send_game_event(stream_id, event_text, player)
        else:
            player.exit_attempts += 1
            if player.sanity <= 0:
                player.health = max(0, player.health - 10)
            ctx = self._make_ctx(player)
            event_text = (
                f"🔙 你努力寻找着回到 Level {target_level} 的道路……\n\n"
                f"❌ 但后室的空间太过混乱，你迷失了方向。理智值 -10\n"
                f"当前楼层：{ctx.level_info['title']}"
            )
            if player.health <= 0:
                player.fsm.apply(GameEvent.DIE)
                del self._players[user_id]
                self._delete_player_save(user_id)
                await self._send_game_event(stream_id, event_text, player)
                return
            await self._send_game_event(stream_id, event_text, player)

        self._save_player(user_id)
