"""后室:逃出生天 — 渲染层

将所有消息文本格式化逻辑集中于此，严格遵循「纯函数」原则：
接收数据 → 返回字符串，不依赖 SDK、无副作用、不访问网络。

本包也是 ``plugin.py`` 的唯一导入入口，
``story_load/`` 下的业务模块通过本包透出给上层。
"""

from __future__ import annotations

# ── 透出 story_load 中的业务模块 ──
# 保持向后兼容：plugin.py 通过 rendering/ 访问所有 story_load 子模块
from ..story_load import (
    CharacterEncounterService,
    EncounterResult,
    CHARACTERS,
    build_system_prompt,
    build_message_list,
    trim_history,
    is_end_dialog,
    strip_cot,
    MAX_HISTORY_ROUNDS,
    END_DIALOG_KEYWORDS,
    ShutManager,
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
)

# ── 状态机 ──
from ..core.state_machine import GameState, GameEvent, GameStateMachine

# ── 渲染器 ──
from .context import RenderContext
from .renderer import BackroomsRenderer
from .companion_script import companion_lines, companion_exit_lines

__all__ = [
    "RenderContext",
    "BackroomsRenderer",
    "companion_lines",
    "companion_exit_lines",
    # story_load 透出
    "CharacterEncounterService",
    "EncounterResult",
    "CHARACTERS",
    "build_system_prompt",
    "build_message_list",
    "trim_history",
    "is_end_dialog",
    "strip_cot",
    "MAX_HISTORY_ROUNDS",
    "END_DIALOG_KEYWORDS",
    "ShutManager",
    "StoryManager",
    "PeopleStoryManager",
    "QuestManager",
    "WorkManager",
    "BaseWorkStoryManager",
    # 状态机
    "GameState",
    "GameEvent",
    "GameStateMachine",
]
