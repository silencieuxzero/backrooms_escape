"""后室:逃出生天 — 探索服务

处理玩家在楼层中探索的完整逻辑：事件抽取、实体遭遇、角色遭遇、
物资箱掉落、任务检测、死亡判定等。
"""

from __future__ import annotations

import random
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .player_state import PlayerState

from .game_data import GameDataService, EXPLORE_EVENTS, BASE_EXPLORE_EVENTS, ITEMS_POOL, ENTITIES


class ExplorationService:
    """楼层探索服务。

    封装探索相关的所有业务逻辑，通过 ``plugin_ref`` 获取配置、日志和子服务。
    """

    def __init__(self, plugin_ref: Any) -> None:
        self._plugin = plugin_ref
        self._data = GameDataService()

    @property
    def _cfg(self) -> Any:
        return self._plugin.config.game

    @property
    def _logger(self) -> Any:
        return self._plugin.ctx.logger

    @property
    def _story_manager(self) -> Any:
        return self._plugin._story_manager

    @property
    def _people_manager(self) -> Any:
        return self._plugin._people_manager

    @property
    def _quest_manager(self) -> Any:
        return self._plugin._quest_manager

    @property
    def _work_manager(self) -> Any:
        return self._plugin._work_manager

    @property
    def _char_encounter_service(self) -> Any:
        return self._plugin._char_encounter_service

    # ── 公共入口 ──

    def process_explore(self, player: PlayerState) -> dict[str, Any]:
        """执行一次楼层探索，返回渲染所需的结果字典。

        Returns:
            包含 event_text, crate_result, health_cost, note_found,
            entity_encounter, char_encounter, work_triggered, work_assigned 等键的字典。
            若玩家死亡，额外包含 ``death`` = True。
        """
        result: dict[str, Any] = {}
        cfg = self._cfg
        player.sanity = max(0, player.sanity - cfg.explore_sanity_cost)
        level_info = self._data.get_level_info(player.current_level)

        # 随机事件
        event = random.choice(EXPLORE_EVENTS)
        event_text = event["text"]
        crate_result = None
        health_cost = None
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

        # 实体遭遇
        entity_encounter = self._roll_entity_encounter(player, level_info)

        # 角色遭遇
        char_encounter = self._roll_character_encounter(player)

        # 理智值过低
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        # Level 1 工作触发
        work_triggered, work_assigned = self._roll_work_trigger(player)

        result.update({
            "event_text": event_text,
            "crate_result": crate_result,
            "health_cost": health_cost,
            "note_found": note_found,
            "entity_encounter": entity_encounter,
            "char_encounter": char_encounter,
            "work_triggered": work_triggered,
            "work_assigned": work_assigned,
            "death": False,
        })

        if player.health <= 0:
            result["death"] = True

        return result

    def process_explore_base(self, player: PlayerState) -> dict[str, Any]:
        """执行一次 Alpha 基地探索，返回渲染所需的结果字典。"""
        result: dict[str, Any] = {}
        cfg = self._cfg
        player.sanity = max(0, player.sanity - 1)
        event = random.choice(BASE_EXPLORE_EVENTS)
        event_area = event["area"]
        event_text = event["text"]
        item_gained = None

        if event.get("give_item"):
            item = self._data.random_item({
                "o1": cfg.item_weight_o1, "o2": cfg.item_weight_o2,
                "o3": cfg.item_weight_o3, "o4": cfg.item_weight_o4,
                "o5": cfg.item_weight_o5, "o6": cfg.item_weight_o6,
                "o7": cfg.item_weight_o7,
            })
            player.inventory.append(dict(item))
            item_gained = item

        char_encounter = self._roll_character_encounter(player)

        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        result.update({
            "event_area": event_area,
            "event_text": event_text,
            "item_gained": item_gained,
            "char_encounter": char_encounter,
            "death": player.health <= 0,
        })
        return result

    # ── 实体遭遇 ──

    def _roll_entity_encounter(self, player: PlayerState, level_info: dict) -> tuple | None:
        cfg = self._cfg
        danger_modifier = {"低": 0.5, "中": 1.0, "高": 1.5, "极高": 2.0}
        encounter_chance = cfg.entity_encounter_chance * danger_modifier.get(level_info["danger"], 1.0)

        if random.random() >= encounter_chance or not level_info.get("entities"):
            return None

        entity_name = random.choice(level_info["entities"])
        entity_data = ENTITIES.get(entity_name)
        if not entity_data:
            return None

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

        return (entity_name, entity_data, edamage)

    # ── 角色遭遇 ──

    def _roll_character_encounter(self, player: PlayerState) -> tuple | None:
        cfg = self._cfg
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
            player.consecutive_misses = 0
            return (
                result.char_id, result.story_text,
                result.gift_text, result.quest_offer,
                result.favorability_increase, result.current_favorability,
            )
        player.consecutive_misses += 1
        return None

    # ── 工作触发 ──

    def _roll_work_trigger(self, player: PlayerState) -> tuple[bool, tuple | None]:
        if player.current_level != 1:
            return False, None

        cfg = self._cfg
        player.l1_explore_count += 1
        interval = cfg.work_trigger_interval
        if player.l1_explore_count < interval:
            return False, None

        player.l1_explore_count = 0
        available = self._work_manager.get_available_works(player.completed_works)
        if not available:
            return True, None

        wid = random.choice(available)
        w = self._work_manager.get_work(wid)
        if w:
            player.available_works.add(wid)
            return True, (wid, w.get("title", wid))
        return True, None

    # ── 物资箱 ──

    def _roll_crate(self, player: PlayerState) -> tuple | None:
        if player.current_level == 0:
            return None

        cfg = self._cfg
        r = random.random()
        crate_size = None
        if r < cfg.crate_large_chance:
            crate_size = "大型物资箱"
        elif r < cfg.crate_large_chance + cfg.crate_medium_chance:
            crate_size = "中型物资箱"
        elif r < cfg.crate_large_chance + cfg.crate_medium_chance + cfg.crate_small_chance:
            crate_size = "小型物资箱"

        if crate_size is None:
            return None

        items = [
            {"name": "o1", "type": "consumable", "effect": "sanity_restore", "value": 30,
             "display_name": "杏仁水",
             "description": "后室中最常见的补给品，喝下可以恢复理智，味道像融化的杏仁冰淇淋。"},
            dict(self._data.random_item({
                "o1": cfg.item_weight_o1, "o2": cfg.item_weight_o2,
                "o3": cfg.item_weight_o3, "o4": cfg.item_weight_o4,
                "o5": cfg.item_weight_o5, "o6": cfg.item_weight_o6,
                "o7": cfg.item_weight_o7,
            })),
        ]
        return crate_size, items

    # ── 工具方法 ──

    @staticmethod
    def _has_item(player: PlayerState, item_name: str) -> bool:
        return any(item["name"] == item_name for item in player.inventory)

    @staticmethod
    def _use_item(player: PlayerState, item_name: str) -> dict | None:
        for i, item in enumerate(player.inventory):
            if item["name"] == item_name:
                return player.inventory.pop(i)
        return None
