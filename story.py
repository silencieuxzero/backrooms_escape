"""后室:逃出生天 — 故事/纸条模块

在探索过程中，玩家有概率捡到带有后室背景故事的纸条。
纸条内容从 level_story/ 目录下的 l1_story.txt ~ l11_story.txt 文件中读取。
"""

from __future__ import annotations

import glob
import os
import random
from typing import Optional


class PeopleStoryManager:
    """人物剧情管理器。

    自动加载 people_story/ 目录下的所有 .txt 文件，
    每个文件代表一个角色，以文件名（不含扩展名）为角色 ID。
    """

    SEPARATOR = "===CHARACTER_"

    def __init__(self) -> None:
        """初始化人物剧情管理器，自动发现并加载所有剧情文件。"""
        self._stories: dict[str, list[str]] = {}
        self._load_all()

    def _load_all(self) -> None:
        """自动发现并加载 people_story/ 下所有 .txt 文件。"""
        base_dir = os.path.join(os.path.dirname(__file__), "people_story")
        if not os.path.isdir(base_dir):
            return
        pattern = os.path.join(base_dir, "*.txt")
        story_files = sorted(glob.glob(pattern))

        for file_path in story_files:
            char_id = os.path.splitext(os.path.basename(file_path))[0]
            self._load_file(char_id, file_path)

    def _load_file(self, char_id: str, file_path: str) -> None:
        """加载单个角色剧情文件。

        Args:
            char_id: 角色 ID（文件名不含扩展名）。
            file_path: 剧情文件的完整路径。
        """
        if not os.path.isfile(file_path):
            return

        with open(file_path, encoding="utf-8") as f:
            raw = f.read()

        parts = raw.split(self.SEPARATOR)
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
            self._stories[char_id] = stories

    @property
    def character_ids(self) -> list[str]:
        """返回所有已加载的角色 ID 列表。"""
        return list(self._stories.keys())

    def get_story_count(self, char_id: str) -> int:
        """获取指定角色的剧情数量。"""
        return len(self._stories.get(char_id, []))

    def get_random_story(self, char_id: str) -> Optional[str]:
        """随机获取指定角色的一个剧情片段。

        Args:
            char_id: 角色 ID。

        Returns:
            随机剧情文本；角色不存在或无剧情时返回 None。
        """
        stories = self._stories.get(char_id)
        if not stories:
            return None
        return random.choice(stories)


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
        base_dir = os.path.join(os.path.dirname(__file__), "level_story")
        pattern = os.path.join(base_dir, "l*_story.txt")
        story_files = sorted(glob.glob(pattern))

        for file_path in story_files:
            self._load_file(file_path)

    def _load_file(self, file_path: str) -> None:
        """加载单个故事文本文件。

        Args:
            file_path: 故事文件的完整路径。
        """
        if not os.path.isfile(file_path):
            return

        with open(file_path, encoding="utf-8") as f:
            raw = f.read()

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
