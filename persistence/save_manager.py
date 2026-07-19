"""后室:逃出生天 — 存档管理器

封装玩家存档的完整生命周期管理：
- 加载/保存 JSON 存档文件
- 自动迁移旧版存档到当前格式
- 批量操作与安全文件名处理
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

SAVE_VERSION = "1.2.1"
"""存档数据格式版本号，与 plugin.py 中的 SAVE_VERSION 保持同步。"""

if TYPE_CHECKING:
    from ..core.player_state import PlayerState
    from ..core.state_machine import GameStateMachine


def _load_companions(data: dict) -> list[str]:
    """从存档字典加载同行列表，兼容旧版单个 ``companion`` 字段。

    - 新版（v1.1.3+）：``"companions": ["ankexin", "xiazhong"]``
    - 旧版（v1.1.2-）：``"companion": "ankexin"``
    """
    raw = data.get("companions")
    if isinstance(raw, list):
        return list(raw)
    raw = data.get("companion")
    if isinstance(raw, str) and raw:
        return [raw]
    return []


class SaveManager:
    """玩家存档管理器。

    通过 ``plugin_ref`` 获取插件实例以访问日志和数据目录。
    存档以 JSON 格式存储在 br_data/ 目录下，
    每个玩家一个文件，文件名基于 user_id 做安全处理。
    """

    def __init__(self, plugin_ref: Any) -> None:
        self._plugin = plugin_ref

    @property
    def _data_dir(self) -> Path:
        return self._plugin._data_dir

    @property
    def _logger(self) -> Any:
        return self._plugin.ctx.logger

    # ── 文件路径 ──

    def _file_path(self, user_id: str) -> Path:
        """获取指定用户的存档文件路径（安全文件名）。"""
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "_-")
        return self._data_dir / f"{safe_id}.json"

    # ── 保存 ──

    def save(self, player: PlayerState) -> None:
        """将单个玩家状态保存为 JSON 文件。"""
        from ..core.state_machine import GameStateMachine
        data = {
            "save_version": SAVE_VERSION,
            "user_id": player.user_id,
            "current_level": player.current_level,
            "health": player.health,
            "sanity": player.sanity,
            "inventory": player.inventory,
            "state": player.fsm.state.value,
            "exit_attempts": player.exit_attempts,
            "pending_note": player.pending_note,
            "unlocked_chars": sorted(player.unlocked_chars),
            "currency": player.currency,
            "active_quests": sorted(player.active_quests),
            "completed_quests": sorted(player.completed_quests),
            "pending_quest_offer": player.pending_quest_offer,
            "available_works": sorted(player.available_works),
            "completed_works": sorted(player.completed_works),
            "work_stories": sorted(player.work_stories),
            "l1_explore_count": player.l1_explore_count,
            "favorability": player.favorability,
            "companions": list(player.companions),
            "consecutive_misses": player.consecutive_misses,
            "visited_levels": sorted(player.visited_levels),
            "dialog_char_id": player.dialog_char_id,
            "dialog_node_id": player.dialog_node_id,
            "dialog_history": player.dialog_history,
        }
        filepath = self._file_path(player.user_id)
        try:
            filepath.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            self._logger.error("保存玩家存档失败 user_id=%s: %s", player.user_id, exc)

    def delete(self, user_id: str) -> None:
        """删除玩家存档文件（游戏结束/通关时调用）。"""
        filepath = self._file_path(user_id)
        try:
            filepath.unlink(missing_ok=True)
        except OSError as exc:
            self._logger.error("删除玩家存档失败 user_id=%s: %s", user_id, exc)

    # ── 加载 ──

    def load(self, user_id: str) -> PlayerState | None:
        """从 JSON 文件加载单个玩家状态；文件不存在则返回 None。"""
        from ..core.player_state import PlayerState
        from ..core.state_machine import GameStateMachine

        filepath = self._file_path(user_id)
        if not filepath.is_file():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self._logger.error("读取玩家存档失败 user_id=%s: %s", user_id, exc)
            return None

        data = self._migrate(data)

        return PlayerState(
            user_id=data.get("user_id", user_id),
            current_level=data.get("current_level", 0),
            health=data.get("health", 100),
            sanity=data.get("sanity", 100),
            inventory=data.get("inventory", []),
            fsm=GameStateMachine.from_dict(data),
            exit_attempts=data.get("exit_attempts", 0),
            pending_note=data.get("pending_note"),
            unlocked_chars=set(data.get("unlocked_chars", [])),
            currency=data.get("currency", 0),
            active_quests=set(data.get("active_quests", [])),
            completed_quests=set(data.get("completed_quests", [])),
            pending_quest_offer=data.get("pending_quest_offer"),
            available_works=set(data.get("available_works", [])),
            completed_works=set(data.get("completed_works", [])),
            work_stories=set(data.get("work_stories", [])),
            l1_explore_count=data.get("l1_explore_count", 0),
            favorability=data.get("favorability", {}),
            companions=_load_companions(data),
            consecutive_misses=data.get("consecutive_misses", 0),
            visited_levels=set(data.get("visited_levels", [])),
            dialog_char_id=data.get("dialog_char_id"),
            dialog_node_id=data.get("dialog_node_id", "start"),
            dialog_history=data.get("dialog_history", []),
        )

    def load_all(self, players: dict[str, Any]) -> None:
        """批量加载 br_data 目录下所有存档文件到 players 字典。"""
        for filepath in self._data_dir.glob("*.json"):
            user_id = filepath.stem
            player = self.load(user_id)
            if player is not None:
                players[user_id] = player

    # ── 迁移 ──

    @staticmethod
    def _migrate(data: dict) -> dict:
        """将旧版存档数据迁移至当前存档格式。

        旧版存档（v1.0.1 / v1.0.2）没有 ``save_version`` 字段。
        后续版本如有存档格式变更，在此处添加对应版本的分支迁移逻辑。
        """
        save_version = data.get("save_version", "0.0.0")
        if save_version == "0.0.0":
            pass  # 当前格式与旧版兼容
        return data
