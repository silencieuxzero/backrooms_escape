"""renderer_load — 拓展功能模块包

所有功能拓展 .py 文件应放置在此目录下，
由 :mod:`~backrooms_escape.renderer` 统一加载并透出。
"""

from __future__ import annotations

from .shut import ShutManager
from .state_machine import GameState, GameEvent, GameStateMachine
from .story import (
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
)

__all__ = [
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
