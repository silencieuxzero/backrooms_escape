"""后室:逃出生天 — 持久化层

负责玩家存档的加载、保存、迁移和文件管理。
所有持久化操作通过 SaveManager 统一管理。
"""

from __future__ import annotations

from .save_manager import SaveManager

__all__ = ["SaveManager"]
