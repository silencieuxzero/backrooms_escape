"""后室:逃出生天 — 角色系统模块

集中管理角色元数据、角色遭遇、礼品发放、任务发放和好感度逻辑。
新增角色只需在 ``CHARACTERS`` 注册表中添加一条记录，
并在 ``br_story/people_story/`` 下创建对应的 ``.txt`` 剧情文件即可。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any


# ==================== 角色注册表 ====================

# 角色元数据定义。
# 键为角色 ID，必须与 br_story/people_story/<id>.txt 文件名（不含扩展名）一致。
# gift_item_ids: 首次见面赠送的物品 ID 列表，从 ITEMS_POOL 按 name 查找。
# can_offer_quest: 遇到该角色时是否可能发放任务。
CHARACTERS: dict[str, dict[str, Any]] = {
    "ankexin": {
        "name": "安可欣",
        "gift_item_ids": ["o1", "o1"],       # 2 瓶杏仁水
        "can_offer_quest": True,
        "level": 1,                          # 在 Level 1 出现
    },
    "anjinian": {
        "name": "安继年",
        "gift_item_ids": ["o1", "o1"],       # 2 瓶杏仁水
        "can_offer_quest": False,
        "level": 1,                          # 在 Level 1 出现
    },
    "baiyu": {
        "name": "白宇",
        "gift_item_ids": ["o3"],             # 1 个手电筒
        "can_offer_quest": False,
        "level": 2,                          # 在 Level 2 出现
    },
    "luna": {
        "name": "Luna",
        "gift_item_ids": ["o7"],             # 1 支镇定剂
        "can_offer_quest": False,
        "level": 1,                          # 在 Level 1 出现
    },
    "luo_shulv": {
        "name": "洛疏律",
        "gift_item_ids": ["o6"],             # 1 根能量棒
        "can_offer_quest": False,
        "level": 1,                          # 在 Level 1 出现
    },
}


# ==================== 遭遇结果 ====================

@dataclass
class EncounterResult:
    """角色遭遇结果，包含所有需要展示/处理的信息。"""

    char_id: str
    """遇到的角色 ID。"""

    story_text: str
    """触发并展示的剧情文本（初见/常规）。"""

    gift_text: str | None = None
    """礼品赠送文本，首次见面时有值。"""

    quest_offer: str | None = None
    """发放的任务 ID，角色可发放任务且概率命中时有值。"""

    unlocked: bool = False
    """是否为首次解锁（初见）。"""

    favorability_increase: int = 0
    """本次遭遇增加的好感度数值。"""

    current_favorability: int = 0
    """增加后的当前好感度。"""


# ==================== 遭遇服务 ====================

def _lookup_item(item_id: str, items_pool: list[dict]) -> dict | None:
    """从物品池中按 name 查找物品模板。"""
    for item in items_pool:
        if item["name"] == item_id:
            return item
    return None


class CharacterEncounterService:
    """角色遭遇一站式服务。

    将原来散落在 ``_do_explore`` 中的角色选择、礼品发放、
    任务发放逻辑集中管理，新增角色只需在 ``CHARACTERS`` 注册即可。
    """

    def __init__(self, items_pool: list[dict]) -> None:
        self._items_pool = items_pool

    # ── 公共入口 ──

    def roll_encounter(
        self,
        level: int,
        unlocked_chars: set[str],
        player_state: Any,
        people_story_manager: Any,
        quest_manager: Any,
        ankexin_task_chance: float,
        favorability_per_encounter: int = 10,
    ) -> EncounterResult | None:
        """掷骰判定当前楼层是否发生角色遭遇。

        Args:
            level: 当前楼层。
            unlocked_chars: 玩家已解锁的角色 ID 集合。
            player_state: 玩家状态对象（用于发放礼品/任务）。
            people_story_manager: ``PeopleStoryManager`` 实例。
            quest_manager: ``QuestManager`` 实例。
            ankexin_task_chance: 安可欣发放任务的概率 (0.0~1.0)。
            favorability_per_encounter: 每次遭遇增加的好感度。

        Returns:
            遭遇结果；未触发时返回 ``None``。
        """
        # 筛选在当前楼层有初见剧情的可遇角色
        available = [
            cid for cid, meta in CHARACTERS.items()
            if meta.get("level") == level
            and people_story_manager.get_first_story(cid) is not None
        ]
        if not available:
            return None

        # 40% 基础遭遇概率
        if random.random() >= 0.40:
            return None

        char_id = random.choice(available)
        char_meta = CHARACTERS.get(char_id, {})

        if char_id not in unlocked_chars:
            return self._first_encounter(
                char_id, char_meta, player_state, people_story_manager,
                quest_manager, ankexin_task_chance, favorability_per_encounter,
            )
        else:
            return self._routine_encounter(
                char_id, char_meta, player_state, people_story_manager,
                quest_manager, ankexin_task_chance, favorability_per_encounter,
            )

    # ── 初见遭遇 ──

    def _first_encounter(
        self,
        char_id: str,
        char_meta: dict[str, Any],
        player_state: Any,
        people_story_manager: Any,
        quest_manager: Any,
        ankexin_task_chance: float,
        favorability_per_encounter: int = 10,
    ) -> EncounterResult | None:
        story_text = people_story_manager.get_first_story(char_id)
        if not story_text:
            return None

        # 发放见面礼
        gift_text = self._apply_gift(char_meta, player_state)

        # 任务发放
        quest_offer = self._maybe_offer_quest(
            char_meta, player_state, quest_manager, ankexin_task_chance,
        )

        # 标记解锁
        player_state.unlocked_chars.add(char_id)
        player_state.pending_quest_offer = quest_offer  # None 时清除旧值

        # 好感度增加
        old_fav = player_state.favorability.get(char_id, 0)
        new_fav = old_fav + favorability_per_encounter
        player_state.favorability[char_id] = new_fav

        return EncounterResult(
            char_id=char_id,
            story_text=story_text,
            gift_text=gift_text,
            quest_offer=quest_offer,
            unlocked=True,
            favorability_increase=favorability_per_encounter,
            current_favorability=new_fav,
        )

    # ── 常规遭遇 ──

    def _routine_encounter(
        self,
        char_id: str,
        char_meta: dict[str, Any],
        player_state: Any,
        people_story_manager: Any,
        quest_manager: Any,
        ankexin_task_chance: float,
        favorability_per_encounter: int = 10,
    ) -> EncounterResult | None:
        story_text = people_story_manager.get_random_routine(char_id)
        if not story_text:
            return None

        quest_offer = self._maybe_offer_quest(
            char_meta, player_state, quest_manager, ankexin_task_chance,
        )
        player_state.pending_quest_offer = quest_offer  # None 时清除旧值

        # 好感度增加
        old_fav = player_state.favorability.get(char_id, 0)
        new_fav = old_fav + favorability_per_encounter
        player_state.favorability[char_id] = new_fav

        return EncounterResult(
            char_id=char_id,
            story_text=story_text,
            quest_offer=quest_offer,
            favorability_increase=favorability_per_encounter,
            current_favorability=new_fav,
        )

    # ── 礼品发放 ──

    def _apply_gift(self, char_meta: dict[str, Any], player_state: Any) -> str | None:
        gift_ids = char_meta.get("gift_item_ids", [])
        if not gift_ids:
            return None

        item_names: list[str] = []
        for item_id in gift_ids:
            template = _lookup_item(item_id, self._items_pool)
            if template:
                player_state.inventory.append(dict(template))
                item_names.append(template.get("display_name", item_id))
            else:
                item_names.append(item_id)

        if not item_names:
            return None

        return f"🎁 对方给了你{'、'.join(item_names)}作为见面礼。"

    # ── 任务发放 ──

    def _maybe_offer_quest(
        self,
        char_meta: dict[str, Any],
        player_state: Any,
        quest_manager: Any,
        ankexin_task_chance: float,
    ) -> str | None:
        if not char_meta.get("can_offer_quest", False):
            return None
        if random.random() >= ankexin_task_chance:
            return None
        available = quest_manager.get_available_quests(
            player_state.active_quests, player_state.completed_quests,
        )
        if not available:
            return None
        return random.choice(available)
