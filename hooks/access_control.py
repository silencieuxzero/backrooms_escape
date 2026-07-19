"""后室:逃出生天 — 访问控制 Hook

在命令执行前检查黑名单和白名单，并根据插件禁用状态决定是否放行。
作为独立的处理函数，通过 ``@HookHandler`` 注册到插件生命周期中。
"""

from __future__ import annotations

from typing import Any


async def check_access_before_command(plugin: Any, **kwargs: Any) -> dict:
    """命令执行前检查黑名单和白名单。

    以独立函数形式实现，由 ``BackroomsGamePlugin`` 的 ``@HookHandler`` 装饰器方法调用。
    接收 ``plugin`` 实例以访问配置和工具方法。
    """
    command_name = str(kwargs.get("command_name", "") or kwargs.get("name", ""))

    # 只有 /br 命令需要检查
    if not command_name.startswith("br_"):
        return {"action": "continue"}

    message = kwargs.get("message", {})
    if not message:
        plugin.ctx.logger.warning("access_check: message 为空，跳过检查 command_name=%s", command_name)
        return {"action": "continue"}

    stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))

    resolved = plugin._resolve_access_id(message, stream_id)
    if resolved is None:
        mi = message.get("message_info") or {}
        plugin.ctx.logger.warning(
            "access_check: 无法解析访问ID command_name=%s stream_id=%s "
            "session_id=%s user_info=%r group_info=%r additional_config_keys=%s msg_keys=%s",
            command_name,
            stream_id,
            message.get("session_id", "N/A"),
            mi.get("user_info"),
            mi.get("group_info"),
            list((mi.get("additional_config") or {}).keys()),
            list(mi.keys()),
        )
        return {"action": "continue"}

    chat_type, chat_id = resolved
    user_id = plugin._resolve_user_id(message, stream_id)

    plugin.ctx.logger.info(
        "access_check: 解析成功 command_name=%s chat_type=%s chat_id=%s user_id=%s",
        command_name, chat_type, chat_id, user_id,
    )

    # 黑名单优先于白名单
    allowed, reason = plugin._check_blacklist(chat_type, chat_id, user_id)
    if not allowed:
        plugin.ctx.logger.info(
            "access_check: 黑名单拦截 chat_type=%s chat_id=%s user_id=%s reason=%s",
            chat_type, chat_id, user_id, reason,
        )
        if stream_id:
            await plugin.ctx.send.text(f"🚫 {reason}", stream_id)
        return {"action": "abort"}

    allowed, reason = plugin._check_whitelist(chat_type, chat_id)
    if not allowed:
        plugin.ctx.logger.info(
            "access_check: 白名单拦截 chat_type=%s chat_id=%s reason=%s",
            chat_type, chat_id, reason,
        )
        if stream_id:
            await plugin.ctx.send.text(f"🚫 {reason}", stream_id)
        return {"action": "abort"}

    # 插件禁用检查：禁用状态下仅管理员可继续使用
    if plugin._plugin_disabled:
        if command_name not in ("br_off", "br_on") and user_id not in plugin._admin_ids:
            plugin.ctx.logger.info(
                "access_check: 插件已禁用，拒绝非管理员 user_id=%s command_name=%s",
                user_id, command_name,
            )
            if stream_id:
                await plugin.ctx.send.text("🚫 插件已由管理员关闭。", stream_id)
            return {"action": "abort"}

    return {"action": "continue"}
