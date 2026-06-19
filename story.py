"""后室:逃出生天 — 故事/纸条模块

在探索过程中，玩家有概率捡到带有后室背景故事的纸条。
纸条内容从 level_story/ 目录下的 l1_story.txt ~ l11_story.txt 文件中读取。
"""

from __future__ import annotations

import glob
import os
import random
from typing import Optional


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
