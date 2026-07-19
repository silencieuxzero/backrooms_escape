"""后室:逃出生天 — 消息处理 Hook

处理命令后跳过 Planner、对话模式消息拦截、群聊静默检查。
"""

from __future__ import annotations

import asyncio
from typing import Any


async def skip_planner_after_command(plugin: Any, **kwargs: Any) -> dict:
    """命令执行后标记消息已被消费，避免进入 Planner。"""
    command_name = str(kwargs.get("command_name", "") or kwargs.get("name", ""))
    if not command_name.startswith("br_"):
        return {"action": "continue"}
    plugin.ctx.logger.debug("skip_planner: 标记命令 %s 已处理", command_name)
    return {"result": (True, "命令已处理", 1)}


async def handle_dialog_message(plugin: Any, **kwargs: Any) -> dict:
    """在消息处理前检查用户是否处于对话模式。

    若玩家处于 ``DIALOG`` 状态，将非 ``/br`` 消息直接路由至
    ``_do_dialog_choice`` 并由 LLM 生成角色回复，同时阻止消息
    进入 MaiBot 的 Planner/LLM 处理链。
    """
    message = kwargs.get("message", {})
    if not message:
        return {"action": "continue"}

    raw_text = str(message.get("raw_message", "") or "")
    if not raw_text or raw_text.startswith("/br"):
        return {"action": "continue"}

    stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))
    user_id = str(stream_id)
    if not user_id:
        return {"action": "continue"}

    player = plugin._get_or_load_player(user_id)
    if not player or not player.fsm.is_dialog():
        return {"action": "continue"}

    plugin.ctx.logger.info("对话模式: 拦截玩家 %s 的输入 → LLM 角色回复", user_id)
    asyncio.ensure_future(plugin._do_dialog_choice(stream_id, raw_text.strip()))
    return {"action": "abort"}


async def check_shut_before_process(plugin: Any, **kwargs: Any) -> dict:
    """在消息处理前检查群组是否被静默。

    被静默的群组中，只有 /br 命令可以继续处理，
    其余消息全部终止在本 hook，不进入 Planner/LLM 处理链。
    """
    message = kwargs.get("message", {})
    if not message:
        return {"action": "continue"}

    raw_text = str(message.get("raw_message", "") or "")

    # /br 命令放行
    if raw_text.startswith("/br"):
        return {"action": "continue"}

    stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))
    resolved = plugin._resolve_access_id(message, stream_id)
    if resolved is None:
        return {"action": "continue"}

    chat_type, chat_id = resolved

    if chat_type != "group":
        return {"action": "continue"}

    if plugin._shut_manager.is_shut(chat_id):
        plugin.ctx.logger.debug("shut: 拦截群 %s 的非 /br 消息", chat_id)
        return {"action": "abort"}

    return {"action": "continue"}
