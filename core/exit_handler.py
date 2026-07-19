"""后室:逃出生天 — 出口处理服务

处理玩家寻找出口的完整逻辑：出口概率计算、捷径判定、
回溯楼层、死亡判定等。
"""

from __future__ import annotations

import random
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .player_state import PlayerState

from .game_data import GameDataService, EXPLORE_EVENTS, SHORTCUT_POOL


class ExitService:
    """出口处理服务。

    封装寻找出口和回溯的全部业务逻辑。
    """

    def __init__(self, plugin_ref: Any) -> None:
        self._plugin = plugin_ref
        self._data = GameDataService()

    @property
    def _cfg(self) -> Any:
        return self._plugin.config.game

    @property
    def _story_manager(self) -> Any:
        return self._plugin._story_manager

    @property
    def _quest_manager(self) -> Any:
        return self._plugin._quest_manager

    def try_exit(self, player: PlayerState) -> dict[str, Any]:
        """尝试寻找出口。

        Returns:
            包含 exit_found, new_level, shortcut_desc, from_level,
            old_level_info, new_level_info, 或 exit_not_found 相关字段的字典。
        """
        cfg = self._cfg
        player.sanity = max(0, player.sanity - cfg.exit_search_sanity_cost)

        # 计算出口概率
        exit_chance = cfg.base_exit_chance + player.exit_attempts * cfg.exit_chance_increment
        if self._has_item(player, "o4"):  # 楼层钥匙
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
            return self._handle_exit_found(player)
        return self._handle_exit_not_found(player)

    def _handle_exit_found(self, player: PlayerState) -> dict[str, Any]:
        player.exit_attempts = 0
        from_level = player.current_level

        # Level 11 → 直接到 399
        if from_level == 11:
            player.current_level = 399
            return {"exit_found": True, "to_399": True, "from_level": from_level}

        old_level_info = self._data.get_level_info(from_level)
        shortcut_desc = None

        level_info = self._data.get_level_info(player.current_level)
        shortcut = level_info.get("shortcut_to")
        if not shortcut and random.random() < 0.12 and player.current_level < 380:
            sd = random.choice(SHORTCUT_POOL)
            skip = random.randint(*sd["levels_skip"])
            shortcut = min(player.current_level + skip, 398)
            shortcut_desc = sd["description"]

        # 注: 当前所有知名楼层的 shortcut_to 均为 None，
        # 以下分支留作未来扩展（如为某些楼层配置固定 shortcut_to 值）。
        # elif shortcut:
        #     shortcut_desc = random.choice(SHORTCUT_POOL)["description"]

        if shortcut:
            player.current_level = shortcut
            if not shortcut_desc:
                shortcut_desc = f"你从 Level {from_level} 直接跳到了 Level {shortcut}！"
            else:
                shortcut_desc += f"\n你从 Level {from_level} 直接跳到了 Level {shortcut}！"
        else:
            player.current_level += 1

        player.visited_levels.add(player.current_level)
        new_level_info = self._data.get_level_info(player.current_level)

        return {
            "exit_found": True,
            "old_level_info": old_level_info,
            "new_level_info": new_level_info,
            "shortcut_desc": shortcut_desc,
            "from_level": from_level,
        }

    def _handle_exit_not_found(self, player: PlayerState) -> dict[str, Any]:
        player.exit_attempts += 1
        cfg = self._cfg

        event = random.choice(EXPLORE_EVENTS)
        event_text = event["text"]
        crate_result = None
        health_cost = None
        note_found = False

        if event.get("give_item"):
            crate_result = self._roll_crate(player)
            if crate_result:
                _, crate_items = crate_result
                for it in crate_items:
                    player.inventory.append(it)
            else:
                event_text += "……但里面已经空了。"
        if "health_cost" in event:
            health_cost = event["health_cost"]
            if self._has_item(player, "o2"):
                health_cost = max(0, health_cost - 5)
                self._use_item(player, "o2")
            player.health = max(0, player.health - health_cost)
        if event["type"] == "found_note":
            note_text = self._story_manager.get_random_story()
            if note_text:
                player.pending_note = note_text
                note_found = True

        return {
            "exit_found": False,
            "exit_attempts": player.exit_attempts,
            "event_text": event_text,
            "crate_result": crate_result,
            "health_cost": health_cost,
            "note_found": note_found,
            "death": player.health <= 0,
        }

    def try_exit_to_level(self, player: PlayerState, target_level: int) -> dict[str, Any]:
        """尝试回溯到已访问过的楼层。

        Returns:
            包含 success, from_level, new_level_info, old_level_info 的字典。
        """
        cfg = self._cfg
        player.sanity = max(0, player.sanity - 10)
        from_level = player.current_level

        distance = abs(target_level - from_level)
        base_chance = 0.50
        familiarity_bonus = max(0, (10 - target_level) * 0.02)
        attempt_bonus = player.exit_attempts * 0.10
        total_chance = min(0.95, base_chance + familiarity_bonus + attempt_bonus)

        if random.random() < total_chance:
            old_level_info = self._data.get_level_info(from_level)
            player.current_level = target_level
            player.exit_attempts = 0
            player.visited_levels.add(target_level)
            new_level_info = self._data.get_level_info(target_level)
            return {
                "success": True,
                "from_level": from_level,
                "old_level_info": old_level_info,
                "new_level_info": new_level_info,
            }

        player.exit_attempts += 1
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        return {
            "success": False,
            "from_level": from_level,
            "target_level": target_level,
            "level_info": self._data.get_level_info(player.current_level),
            "death": player.health <= 0,
        }

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
