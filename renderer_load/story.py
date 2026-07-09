"""后室:逃出生天 — 故事/纸条模块

在探索过程中，玩家有概率捡到带有后室背景故事的纸条。
纸条内容从 level_story/ 目录下的 l1_story.txt ~ l11_story.txt 文件中读取。
"""

from __future__ import annotations

import random
import json
import re
from pathlib import Path
from typing import Optional


class QuestManager:
    """任务管理器。

    从 br_story/people_story/people_quests.json 加载任务定义。
    """

    def __init__(self, items_pool: list[dict]) -> None:
        self._quests: dict[str, dict] = {}
        self._items_pool = items_pool
        self._load()

    def _load(self) -> None:
        base_dir = Path(__file__).parent.parent / "br_story" / "people_story"
        fp = base_dir / "people_quests.json"
        if not fp.is_file():
            return
        try:
            self._quests = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._quests = {}

    @property
    def quest_ids(self) -> list[str]:
        return list(self._quests.keys())

    def get_quest(self, quest_id: str) -> dict | None:
        return self._quests.get(quest_id)

    def get_available_quests(self, active: set[str], completed: set[str]) -> list[str]:
        """返回当前可接受的任务 ID 列表（未接且未完成）。"""
        available: list[str] = []
        for qid in self._quests:
            if qid in active or qid in completed:
                continue
            available.append(qid)
        return available

    def check_quest_complete(self, quest_id: str, player_state) -> bool:
        """检查任务目标是否达成。"""
        quest = self._quests.get(quest_id)
        if not quest:
            return False
        ot = quest.get("objective_type", "")
        if ot == "reach_level":
            return player_state.current_level >= quest.get("objective_target", 999)
        if ot == "collect_item":
            return any(i["name"] == quest.get("objective_item", "") for i in player_state.inventory)
        if ot == "use_item":
            item_name = quest.get("objective_item", "")
            required_count = quest.get("objective_count", 1)
            return sum(1 for i in player_state.inventory if i.get("name") == item_name) >= required_count
        return False

    def apply_rewards(self, quest_id: str, player_state) -> str:
        """发放任务奖励，返回奖励文本。"""
        quest = self._quests.get(quest_id)
        if not quest:
            return ""
        player_state.currency += quest.get("reward_currency", 0)
        for item_name in quest.get("reward_items", []):
            for template in self._items_pool:
                if template["name"] == item_name:
                    player_state.inventory.append(dict(template))
                    break
        player_state.completed_quests.add(quest_id)
        player_state.active_quests.discard(quest_id)
        return quest.get("reward_text", f"获得 {quest.get('reward_currency', 0)} 贡献点。")


class WorkManager:
    """基地工作管理器。

    从 br_story/base_story/base_work.json 加载解谜工作任务。
    """

    def __init__(self) -> None:
        self._works: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        base_dir = Path(__file__).parent.parent / "br_story" / "base_story"
        fp = base_dir / "base_work.json"
        if not fp.is_file():
            return
        try:
            self._works = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._works = {}

    @property
    def work_ids(self) -> list[str]:
        return list(self._works.keys())

    def get_work(self, work_id: str) -> dict | None:
        return self._works.get(work_id)

    def check_answer(self, work_id: str, answer: str) -> bool:
        """验证解答是否正确。"""
        work = self._works.get(work_id)
        if not work:
            return False
        expected = work.get("answer", "")
        # 不区分大小写、去首尾空格
        return re.sub(r"\s+", "", answer.strip().lower()) == re.sub(r"\s+", "", expected.strip().lower())

    def get_available_works(self, completed: set[str]) -> list[str]:
        """返回可用但未完成的工作 ID 列表。"""
        return [wid for wid in self._works if wid not in completed]


class PeopleStoryManager:
    """人物剧情管理器。

    自动加载 people_story/ 目录下的所有 .txt 文件，
    每个文件代表一个角色，以文件名（不含扩展名）为角色 ID。

    文件格式约定：
      - CHARACTER_001 = 初见剧情（每个角色有且仅有一条）
      - CHARACTER_002 及以后 = 常规剧情（打招呼等日常对话，可多条）
    """

    SEPARATOR = "===CHARACTER_"

    def __init__(self) -> None:
        """初始化人物剧情管理器，自动发现并加载所有剧情文件。"""
        self._first_stories: dict[str, str] = {}        # char_id → 初见剧情
        self._routine_stories: dict[str, list[str]] = {}  # char_id → [常规剧情…]
        self._load_all()

    def _load_all(self) -> None:
        """自动发现并加载 people_story/ 下所有 .txt 文件。"""
        base_dir = Path(__file__).parent.parent / "br_story" / "people_story"
        if not base_dir.is_dir():
            return
        story_files = sorted(base_dir.glob("*.txt"))

        for file_path in story_files:
            char_id = file_path.stem
            self._load_file(char_id, str(file_path))

    def _load_file(self, char_id: str, file_path: str) -> None:
        """加载单个角色剧情文件。

        将 CHARACTER_001 作为初见剧情，后续编号作为常规剧情。

        Args:
            char_id: 角色 ID（文件名不含扩展名）。
            file_path: 剧情文件的完整路径。
        """
        fp = Path(file_path)
        if not fp.is_file():
            return

        raw = fp.read_text(encoding="utf-8")

        parts = raw.split(self.SEPARATOR)
        first_story: str | None = None
        routine_stories: list[str] = []

        for part in parts:
            cleaned = part.strip()
            if not cleaned:
                continue
            idx = cleaned.find("===\n")
            if idx != -1:
                cleaned = cleaned[idx + 4:].strip()
            if cleaned:
                if first_story is None:
                    first_story = cleaned
                else:
                    routine_stories.append(cleaned)

        if first_story:
            self._first_stories[char_id] = first_story
        if routine_stories:
            self._routine_stories[char_id] = routine_stories

    @property
    def character_ids(self) -> list[str]:
        """返回所有已加载的角色 ID 列表。"""
        return list(self._first_stories.keys())

    def get_first_story(self, char_id: str) -> Optional[str]:
        """获取指定角色的初见剧情。"""
        return self._first_stories.get(char_id)

    def has_routine(self, char_id: str) -> bool:
        """检查指定角色是否有常规剧情。"""
        return char_id in self._routine_stories and bool(self._routine_stories[char_id])

    def get_random_routine(self, char_id: str) -> Optional[str]:
        """随机获取指定角色的一条常规剧情（如打招呼）。

        Args:
            char_id: 角色 ID。

        Returns:
            随机常规剧情文本；不存在时返回 None。
        """
        stories = self._routine_stories.get(char_id)
        if not stories:
            return None
        return random.choice(stories)

    def get_story_count(self, char_id: str) -> int:
        """获取指定角色的剧情总数（含初见和常规）。"""
        count = 1 if char_id in self._first_stories else 0
        count += len(self._routine_stories.get(char_id, []))
        return count


class StoryManager:
    """故事纸条管理器。

    自动加载插件目录下所有 l*_story.txt 文件中的故事文本，
    在探索时随机提供纸条内容。
    """

    SEPARATOR = "===STORY_"

    def __init__(self) -> None:
        """初始化故事管理器，自动发现并加载所有故事文件。"""
        self._stories: list[str] = []
        self._load_all()

    def _load_all(self) -> None:
        """自动发现并加载所有 l*_story.txt 文件。"""
        base_dir = Path(__file__).parent.parent / "level_story"
        if not base_dir.is_dir():
            return
        story_files = sorted(base_dir.glob("l*_story.txt"))

        for file_path in story_files:
            self._load_file(str(file_path))

    def _load_file(self, file_path: str) -> None:
        """加载单个故事文本文件。

        Args:
            file_path: 故事文件的完整路径。
        """
        fp = Path(file_path)
        if not fp.is_file():
            return

        raw = fp.read_text(encoding="utf-8")

        parts = raw.split(self.SEPARATOR)
        for part in parts:
            cleaned = part.strip()
            if not cleaned:
                continue
            # 去掉开头的编号 "NNN===\n"
            idx = cleaned.find("===\n")
            if idx != -1:
                cleaned = cleaned[idx + 4:].strip()
            if cleaned:
                self._stories.append(cleaned)

    @property
    def story_count(self) -> int:
        """已加载的故事数量。"""
        return len(self._stories)

    def get_random_story(self) -> Optional[str]:
        """随机获取一个故事纸条内容。

        Returns:
            随机故事文本；没有故事时返回 None。
        """
        if not self._stories:
            return None
        return random.choice(self._stories)


class BaseWorkStoryManager:
    """基地工作故事管理器。

    自动加载 base_story/ 目录下的所有 .txt 文件，
    以文件名（不含扩展名）为故事 ID 存储。
    """

    def __init__(self) -> None:
        self._stories: dict[str, list[str]] = {}
        self._load_all()

    def _load_all(self) -> None:
        base_dir = Path(__file__).parent.parent / "br_story" / "base_story"
        if not base_dir.is_dir():
            return
        for file_path in sorted(base_dir.glob("*.txt")):
            story_id = file_path.stem
            raw = file_path.read_text(encoding="utf-8")
            parts = raw.split("===STORY_")
            stories: list[str] = []
            for part in parts:
                cleaned = part.strip()
                if not cleaned:
                    continue
                idx = cleaned.find("===\n")
                if idx != -1:
                    cleaned = cleaned[idx + 4:].strip()
                if cleaned:
                    stories.append(cleaned)
            if stories:
                self._stories[story_id] = stories

    @property
    def story_ids(self) -> list[str]:
        return list(self._stories.keys())

    def get_story(self, story_id: str) -> str | None:
        """获取指定工作故事的随机一段。"""
        stories = self._stories.get(story_id)
        if not stories:
            return None
        return random.choice(stories)
