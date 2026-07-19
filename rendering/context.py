"""后室:逃出生天 — 渲染上下文

封装渲染所需的全部状态快照，作为渲染方法的参数传递。
"""

from __future__ import annotations

from typing import Any


class RenderContext:
    """封装渲染所需的全部状态快照。

    所有渲染方法接收 RenderContext 实例作为参数，
    避免方法签名过长且便于未来扩展上下文字段。
    """

    def __init__(
        self,
        health: int,
        sanity: int,
        current_level: int,
        initial_health: int,
        initial_sanity: int,
        inventory_count: int,
        game_config: Any,
        level_info: dict[str, Any],
        exit_attempts: int = 0,
    ) -> None:
        self.health = health
        self.sanity = sanity
        self.current_level = current_level
        self.initial_health = initial_health
        self.initial_sanity = initial_sanity
        self.inventory_count = inventory_count
        self.cfg = game_config  # GameConfig 实例
        self.level_info = level_info
        self.exit_attempts = exit_attempts
