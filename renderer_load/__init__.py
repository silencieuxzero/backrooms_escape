"""renderer_load — 拓展功能模块包

所有功能拓展 .py 文件应放置在此目录下，
由 :mod:`~backrooms_escape.renderer` 统一加载并透出。
"""

from __future__ import annotations

from .dialogue_manage import (
    build_system_prompt,
    build_message_list,
    trim_history,
    is_end_dialog,
    MAX_HISTORY_ROUNDS,
    END_DIALOG_KEYWORDS,
)
from .people_manage import CharacterEncounterService, EncounterResult, CHARACTERS
from .shut import ShutManager
from .state_machine import GameState, GameEvent, GameStateMachine
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
