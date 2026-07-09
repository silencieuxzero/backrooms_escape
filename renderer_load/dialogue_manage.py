"""后室:逃出生天 — 角色对话系统（LLM 驱动）

通过麦麦的 LLM 接口生成角色对话，角色卡信息作为 system prompt。
维护对话历史以提供上下文连贯的对话体验。
"""

from __future__ import annotations

from typing import Any

from .people_manage import CHARACTERS

# 对话历史保留的最大轮数（1 轮 = 1 问 + 1 答）
MAX_HISTORY_ROUNDS = 6

# 对话结束指令
END_DIALOG_KEYWORDS = ["0", "结束对话", "结束", "退出对话", "退出", "end"]


# ==================== 提示词构建 ====================


def build_system_prompt(char_id: str, relationship_data: dict[str, Any] | None = None) -> str:
    """根据角色卡构建 LLM system prompt。

    Args:
        char_id: 角色 ID。
        relationship_data: ``people_relationship.json`` 中该角色的数据。

    Returns:
        system prompt 字符串。
    """
    char_meta = CHARACTERS.get(char_id, {})
    char_name = char_meta.get("name", char_id)

    # 从 relationship 数据获取详细设定
    rel = (relationship_data or {}).get(char_id, {})
    identity = rel.get("identity", "身份未知")
    personality = rel.get("personality", "性格未知")
    age = rel.get("age", "?")
    relationship = rel.get("relationship", "")
    description = rel.get("description", "")
    encounter = rel.get("first_encounter", "")

    lines = [
        f"你正在扮演后室（The Backrooms）世界中的角色「{char_name}」。",
        "",
        "=== 角色设定 ===",
        f"姓名：{char_name}",
        f"身份：{identity}",
        f"年龄：{age}",
        f"性格：{personality}",
        f"人际关系：{relationship}",
        f"首次出现：{encounter}",
        "",
        f"=== 角色背景 ===",
        description,
        "",
        "=== 扮演规则 ===",
        "1. 始终使用中文回复，语言风格符合角色性格设定。",
        "2. 完全代入角色，不要说「作为AI/模型」之类的话。",
        "3. 回复要符合后室（The Backrooms）的世界观——这是一个怪异、孤独、危险的空间。",
        "4. 回复长度控制在 2-5 句话，自然流畅。",
        "5. 可以主动反问玩家，推进对话。",
        "6. 不要重复玩家说过的话，不要评价玩家的发言。",
        "7. 如果玩家提到要离开或结束对话，自然地告别即可。",
        "",
        f"现在，你正在 {encounter} 与玩家相遇。{char_name}，开始对话吧。",
    ]
    return "\n".join(lines)


def build_message_list(
    system_prompt: str,
    history: list[dict[str, str]],
    user_message: str,
) -> list[dict[str, str]]:
    """构建 LLM 调用所需的消息列表。

    Args:
        system_prompt: system prompt。
        history: 对话历史列表，每项格式 ``{"role": "user"|"assistant", "content": str}``。
        user_message: 玩家当前输入。

    Returns:
        符合 LLM API 要求的消息列表。
    """
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


# ==================== 对话历史管理 ====================


def trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """裁剪对话历史，保留最近 N 轮。"""
    if len(history) > MAX_HISTORY_ROUNDS * 2:
        return history[-(MAX_HISTORY_ROUNDS * 2):]
    return history


def is_end_dialog(text: str) -> bool:
    """检查玩家是否输入了结束对话的指令。"""
    return text.strip() in END_DIALOG_KEYWORDS
