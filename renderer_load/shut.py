"""后室:逃出生天 — 群聊静默管理器

管理被 /br shut 命令静默的群组。
被静默的群组中，除 /br 命令外的所有消息都不会触发 Planner/LLM 处理。
"""

from __future__ import annotations

import json
from pathlib import Path


class ShutManager:
    """群聊静默管理器。

    将静默群组 ID 持久化到 br_data/shut_groups.json，
    提供增删查改操作。
    """

    def __init__(self, data_dir: Path) -> None:
        self._shut_groups: set[str] = set()
        self._file_path = data_dir / "shut_groups.json"
        self._load()

    # ---- 持久化 ----

    def _load(self) -> None:
        """从磁盘加载静默群组列表。"""
        if not self._file_path.is_file():
            return
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            self._shut_groups = set(data.get("shut_groups", []))
        except (json.JSONDecodeError, OSError):
            self._shut_groups = set()

    def save(self) -> None:
        """将静默群组列表写入磁盘。"""
        try:
            self._file_path.write_text(
                json.dumps(
                    {"shut_groups": sorted(self._shut_groups)},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    # ---- 接口 ----

    def add_shut(self, group_id: str) -> bool:
        """将群组加入静默列表。返回 True 表示状态改变。"""
        if group_id in self._shut_groups:
            return False
        self._shut_groups.add(group_id)
        self.save()
        return True

    def remove_shut(self, group_id: str) -> bool:
        """将群组移出静默列表。返回 True 表示状态改变。"""
        if group_id not in self._shut_groups:
            return False
        self._shut_groups.discard(group_id)
        self.save()
        return True

    def is_shut(self, group_id: str) -> bool:
        """检查群组是否被静默。"""
        return group_id in self._shut_groups

    def list_shut(self) -> list[str]:
        """返回所有被静默的群组 ID。"""
        return sorted(self._shut_groups)
