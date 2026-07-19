"""后室:逃出生天 — 命令处理器包

将 ``BackroomsGamePlugin`` 中的 ``_do_*`` 命令实现方法拆分为多个混入类，
每个混入类专注于一类游戏功能，遵循单一职责原则。

所有混入类最终通过 ``plugin.py`` 中的 ``BackroomsGamePlugin`` 组合使用。

目录结构::

    handlers/
    ├── base.py              # HandlerBase — 共享工具方法（消息解析、发送、物品管理）
    ├── game_commands.py     # GameCommandMixin — 核心游戏循环（开始/探索/使用物品）
    ├── exit_commands.py     # ExitCommandMixin — 出口搜索与楼层回溯
    ├── player_commands.py   # PlayerCommandMixin — 玩家状态（查看状态/背包/帮助）
    ├── story_commands.py    # StoryCommandMixin — 故事档案
    ├── quest_commands.py    # QuestCommandMixin — 任务系统
    ├── work_commands.py     # WorkCommandMixin — 基地工作
    ├── character_commands.py # CharacterCommandMixin — 角色交互（关系图/LLM对话）
    ├── companion_commands.py # CompanionCommandMixin — 同伴同行与赠礼
    └── admin_commands.py    # AdminCommandMixin — 管理员命令

依赖关系::

    所有混入类 → HandlerBase（基础工具方法）
    GameCommandMixin / ExitCommandMixin / QuestCommandMixin / WorkCommandMixin
        → CharacterCommandMixin._auto_end_dialog
    CompanionCommandMixin → CharacterCommandMixin._auto_end_dialog
"""

from __future__ import annotations

from .base import HandlerBase
from .game_commands import GameCommandMixin
from .exit_commands import ExitCommandMixin
from .player_commands import PlayerCommandMixin
from .story_commands import StoryCommandMixin
from .quest_commands import QuestCommandMixin
from .work_commands import WorkCommandMixin
from .character_commands import CharacterCommandMixin
from .companion_commands import CompanionCommandMixin
from .admin_commands import AdminCommandMixin

__all__ = [
    "HandlerBase",
    "GameCommandMixin",
    "ExitCommandMixin",
    "PlayerCommandMixin",
    "StoryCommandMixin",
    "QuestCommandMixin",
    "WorkCommandMixin",
    "CharacterCommandMixin",
    "CompanionCommandMixin",
    "AdminCommandMixin",
]
