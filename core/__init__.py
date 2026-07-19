"""后室:逃出生天 — 核心游戏逻辑层

本包提供所有游戏业务逻辑基础设施：
- 状态机 (GameState / GameEvent / GameStateMachine)
- 玩家状态 (PlayerState)
- 游戏数据 (GameDataService + 静态数据常量)
- 探索服务 (ExplorationService)
- 出口服务 (ExitService)
"""

from __future__ import annotations

from .state_machine import GameState, GameEvent, GameStateMachine
from .player_state import PlayerState
from .game_data import (
    GameDataService,
    load_items_pool,
    ITEMS_POOL,
    ENTITIES,
    ICONIC_LEVELS,
    EXPLORE_EVENTS,
    BASE_EXPLORE_EVENTS,
    SHORTCUT_POOL,
)
from .exploration import ExplorationService
from .exit_handler import ExitService

__all__ = [
    # 状态机
    "GameState",
    "GameEvent",
    "GameStateMachine",
    # 玩家状态
    "PlayerState",
    # 游戏数据
    "GameDataService",
    "load_items_pool",
    "ITEMS_POOL",
    "ENTITIES",
    "ICONIC_LEVELS",
    "EXPLORE_EVENTS",
    "BASE_EXPLORE_EVENTS",
    "SHORTCUT_POOL",
    # 游戏服务
    "ExplorationService",
    "ExitService",
]
