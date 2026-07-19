"""story_load — 故事与角色数据管理包

管理故事文本、角色剧情、任务定义、工作定义等静态内容数据。
状态机类型从 ``core.state_machine`` 统一获取，避免重复定义。
"""

from __future__ import annotations

from ..core.state_machine import GameState, GameEvent, GameStateMachine
from .dialogue_manage import (
    build_system_prompt,
    build_message_list,
    trim_history,
    is_end_dialog,
    strip_cot,
    MAX_HISTORY_ROUNDS,
    END_DIALOG_KEYWORDS,
)
from .people_manage import CharacterEncounterService, EncounterResult, CHARACTERS
from .shut import ShutManager
from .story_manage import (
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
)

__all__ = [
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
    "GameState",
    "GameEvent",
    "GameStateMachine",
    "StoryManager",
    "PeopleStoryManager",
    "QuestManager",
    "WorkManager",
    "BaseWorkStoryManager",
]
