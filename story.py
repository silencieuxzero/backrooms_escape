"""后室:逃出生天 — 故事/纸条模块

在探索过程中，玩家有概率捡到带有后室背景故事的纸条。
纸条内容从 l1_story.txt 文件中读取。
"""

from __future__ import annotations

import os
import random
from typing import Optional


class StoryManager:
    """故事纸条管理器。

    负责加载 l1_story.txt 中的故事文本，并在探索时随机提供纸条内容。
    """

    SEPARATOR = "===STORY_"

    def __init__(self, story_file: str = "l1_story.txt") -> None:
        """初始化故事管理器。

        Args:
            story_file: 故事文本文件名（相对于本文件所在目录）。
        """
        self._stories: list[str] = []
        self._load(story_file)

    def _load(self, story_file: str) -> None:
        """从文本文件加载故事条目。

        Args:
            story_file: 故事文本文件名。
        """
        file_path = os.path.join(os.path.dirname(__file__), story_file)
        if not os.path.isfile(file_path):
            self._stories = []
            return

        with open(file_path, encoding="utf-8") as f:
            raw = f.read()

        # 按 ===STORY_ 分隔符切分
        parts = raw.split(self.SEPARATOR)
        for part in parts:
            # 跳过编号头和空内容
            cleaned = part.strip()
            if not cleaned:
                continue
            # 去掉开头的数字编号 "001===\n"
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
