"""后室:逃出生天 — 管理命令混入

处理管理员命令：关闭插件、启用插件、群聊静默切换。
"""

from __future__ import annotations

from .base import HandlerBase


class AdminCommandMixin(HandlerBase):
    """管理命令处理器混入。

    提供插件开关和群聊静默等管理员专用 ``_do_*`` 方法。
    """

    _plugin_disabled: bool
    _admin_ids: set[str]
    _shut_manager: Any

    async def _do_off(self, stream_id: str, message: dict) -> None:
        """关闭插件：仅管理员可用，禁用后仅管理员可继续使用。"""
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权关闭插件。")
            return

        self._plugin_disabled = True
        self.ctx.logger.info("插件已由管理员关闭 user_id=%s", user_id)
        await self._send(stream_id, "🔒 插件已关闭。")

    async def _do_on(self, stream_id: str, message: dict) -> None:
        """重新启用插件：仅管理员可用。"""
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权启用插件。")
            return

        self._plugin_disabled = False
        self.ctx.logger.info("插件已由管理员重新启用 user_id=%s", user_id)
        await self._send(stream_id, "🔓 插件已重新启用，所有用户均可使用。")

    async def _do_shut(self, stream_id: str, message: dict) -> None:
        """管理员切换当前群聊的静默状态。

        静默后，群内非 /br 消息不会触发 Planner/LLM 处理。
        """
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权执行此操作。")
            return

        resolved = self._resolve_access_id(message, stream_id)
        if resolved is None:
            await self._send(stream_id, "❌ 无法识别当前会话，请确认在群聊中使用此命令。")
            return
        chat_type, chat_id = resolved
        if chat_type != "group":
            await self._send(stream_id, "❌ /br shut 仅限群聊使用。")
            return

        if self._shut_manager.is_shut(chat_id):
            self._shut_manager.remove_shut(chat_id)
            await self._send(stream_id, f"🔊 群 {chat_id} 已取消静默。所有消息恢复正常处理。")
            self.ctx.logger.info("shut: 管理员 %s 已取消群 %s 静默", user_id, chat_id)
        else:
            self._shut_manager.add_shut(chat_id)
            await self._send(stream_id, f"🔇 群 {chat_id} 已开启静默。非 /br 消息将不再触发 Planner。")
            self.ctx.logger.info("shut: 管理员 %s 已静默群 %s", user_id, chat_id)
