"""后室:逃出生天 — 玩家状态数据类

定义玩家游戏状态的完整数据结构，包括生命值、理智值、背包、
任务进度、好感度、同行角色、对话状态等所有运行时数据。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .state_machine import GameStateMachine


@dataclass
class PlayerState:
    """玩家游戏状态。

    所有玩家相关的运行时数据集中在此数据类中管理，
    便于序列化/反序列化以及各服务模块之间的数据传递。
    """

    user_id: str = ""
    """玩家唯一标识（QQ 号或 stream_id）。"""

    current_level: int = 0
    """当前所在楼层编号。"""

    health: int = 100
    """当前生命值。"""

    sanity: int = 100
    """当前理智值。"""

    inventory: list[dict] = field(default_factory=list)
    """背包物品列表，每项为物品数据字典。"""

    fsm: GameStateMachine = field(default_factory=GameStateMachine)
    """游戏状态机，控制玩家当前所处的游戏阶段。"""

    exit_attempts: int = 0
    """当前楼层尝试寻找出口的次数。"""

    pending_note: str | None = None
    """待阅读的纸条内容，None 表示无纸条。"""

    unlocked_chars: set[str] = field(default_factory=set)
    """已解锁（已初见）的角色 ID 集合。"""

    currency: int = 0
    """M.E.G.CN 内部贡献点数。"""

    active_quests: set[str] = field(default_factory=set)
    """进行中的任务 ID 集合。"""

    completed_quests: set[str] = field(default_factory=set)
    """已完成的任务 ID 集合。"""

    pending_quest_offer: str | None = None
    """待接受的任务 ID（角色给出但玩家尚未接受）。"""

    available_works: set[str] = field(default_factory=set)
    """基地当前可接的工作 ID 集合。"""

    completed_works: set[str] = field(default_factory=set)
    """已完成的工作 ID 集合。"""

    work_stories: set[str] = field(default_factory=set)
    """已解锁的工作故事 ID 集合。"""

    l1_explore_count: int = 0
    """Level 1 中已探索次数（达到阈值触发日常工作任务）。"""

    favorability: dict[str, int] = field(default_factory=dict)
    """角色好感度映射 {char_id: 数值}。"""

    companions: list[str] = field(default_factory=list)
    """当前同行的角色 ID 列表。"""

    consecutive_misses: int = 0
    """同楼层连续未触发角色遭遇的次数（保底计数）。"""

    visited_levels: set[int] = field(default_factory=set)
    """已访问过的楼层编号集合（用于回溯）。"""

    dialog_char_id: str | None = None
    """对话模式中的角色 ID，None 表示非对话模式。"""

    dialog_node_id: str = "start"
    """当前对话树节点 ID。"""

    dialog_history: list[dict[str, str]] = field(default_factory=list)
    """LLM 对话历史 [{role, content}, ...]。
    
    role 为 "user" 或 "assistant"。
    """
