"""后室:逃出生天 — 有限状态机

定义游戏核心状态与状态转移规则。
所有命令处理器通过状态机判断当前操作是否合法，避免散落在各处的 if-else。
"""

from __future__ import annotations

from enum import Enum
from typing import Any


class GameState(str, Enum):
    """游戏状态枚举。"""

    NOT_STARTED = "NOT_STARTED"
    """未开始游戏。仅允许 ``start`` 事件。"""

    ALIVE = "ALIVE"
    """存活并处于 0-398 楼层。可进行探索、寻找出口、使用物品等所有操作。"""

    AT_399 = "AT_399"
    """已到达 Level 399（最终出口）。仅允许 ``exit`` 事件触发通关。"""

    DEAD = "DEAD"
    """死亡（生命值 ≤ 0）。仅允许 ``restart`` 重新开始。"""

    ESCAPED = "ESCAPED"
    """通关（从 Level 399 成功逃出）。仅允许 ``restart`` 重新开始。"""


class GameEvent(str, Enum):
    """触发状态转移的事件。"""

    START = "start"
    """开始新游戏。"""

    DIE = "die"
    """玩家死亡。"""

    REACH_399 = "reach_399"
    """到达 Level 399。"""

    EXIT_399 = "exit_399"
    """从 Level 399 成功逃出。"""

    RESTART = "restart"
    """死亡/通关后重新开始。"""

    EXPLORE = "explore"
    """探索（不改变 ALIVE 状态，但消耗理智/触发事件）。"""

    EXIT = "exit"
    """寻找出口（不改变 ALIVE 状态，但可能触发 DIE / REACH_399）。"""

    USE_ITEM = "use_item"
    """使用物品（不改变 ALIVE 状态）。"""


# ── 转移表：{当前状态: {事件: 目标状态}} ──
# 不在表中的 (状态, 事件) 组合视为非法操作。
_TRANSITIONS: dict[GameState, dict[GameEvent, GameState]] = {
    GameState.NOT_STARTED: {
        GameEvent.START: GameState.ALIVE,
    },
    GameState.ALIVE: {
        GameEvent.EXPLORE: GameState.ALIVE,
        GameEvent.EXIT: GameState.ALIVE,      # 可能升级楼层或失败
        GameEvent.USE_ITEM: GameState.ALIVE,
        GameEvent.DIE: GameState.DEAD,
        GameEvent.REACH_399: GameState.AT_399,
    },
    GameState.AT_399: {
        GameEvent.EXIT_399: GameState.ESCAPED,
        GameEvent.DIE: GameState.DEAD,
    },
    GameState.DEAD: {
        GameEvent.RESTART: GameState.ALIVE,
    },
    GameState.ESCAPED: {
        GameEvent.RESTART: GameState.ALIVE,
    },
}


class GameStateMachine:
    """游戏有限状态机。

    用法::

        fsm = GameStateMachine(GameState.NOT_STARTED)
        fsm.apply(GameEvent.START)   # → ALIVE
        fsm.can(GameEvent.EXPLORE)   # → True
        fsm.can(GameEvent.DIE)       # → True
        print(fsm.state)             # GameState.ALIVE
    """

    def __init__(self, initial_state: GameState = GameState.NOT_STARTED) -> None:
        self._state = initial_state

    # ── 属性 ──

    @property
    def state(self) -> GameState:
        return self._state

    # ── 查询 ──

    def can(self, event: GameEvent) -> bool:
        """检查当前状态下是否允许触发指定事件。"""
        allowed = _TRANSITIONS.get(self._state)
        return allowed is not None and event in allowed

    def is_alive(self) -> bool:
        """是否在可正常游戏的状态中。"""
        return self._state is GameState.ALIVE

    def is_not_started(self) -> bool:
        return self._state is GameState.NOT_STARTED

    def is_dead(self) -> bool:
        return self._state is GameState.DEAD

    def is_escaped(self) -> bool:
        return self._state is GameState.ESCAPED

    def is_at_399(self) -> bool:
        return self._state is GameState.AT_399

    def is_playable(self) -> bool:
        """返回是否处于可进行游戏操作的状态（非 NOT_STARTED / DEAD / ESCAPED）。"""
        return self._state in (GameState.ALIVE, GameState.AT_399)

    # ── 转移 ──

    def apply(self, event: GameEvent) -> GameState:
        """执行状态转移。

        Args:
            event: 触发事件。

        Returns:
            转移后的状态。

        Raises:
            ValueError: 当前状态下不允许该事件。
        """
        allowed = _TRANSITIONS.get(self._state)
        if allowed is None or event not in allowed:
            raise ValueError(
                f"非法转移: 当前状态 {self._state.value} 不允许事件 {event.value}"
            )
        self._state = allowed[event]
        return self._state

    # ── 序列化 ──

    def to_dict(self) -> dict[str, Any]:
        return {"state": self._state.value}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameStateMachine:
        state_str = data.get("state", "NOT_STARTED")
        try:
            state = GameState(state_str)
        except ValueError:
            state = GameState.NOT_STARTED
        return cls(state)
