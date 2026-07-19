"""后室:逃出生天 — HandlerBase 基础混入类

提供所有命令处理器共用的工具方法，包括：
- 消息解析（解析 stream_id、access_id、user_id）
- 玩家状态管理（获取、加载、保存）
- 消息发送（文本、转发、三段式游戏事件）
- 物品管理（查找、使用、格式化）
- 渲染上下文构建
- 配置文件迁移

作为抽象混入类，依赖 ``self._players``、``self.config``、``self.ctx`` 等
插件实例属性，不直接继承 ``MaiBotPlugin``。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from ..core.game_data import ITEMS_POOL
from ..core.player_state import PlayerState
from ..rendering.context import RenderContext


class HandlerBase:
    """命令处理器基础混入。

    提供所有 ``_do_*`` 命令处理方法所需的共享工具函数。
    不包含任何 ``@Command`` 或 ``@HookHandler`` 装饰器，
    仅作为工具方法的集合被混入 ``BackroomsGamePlugin``。
    """

    # ── 声明类型提示（实际属性由 BackroomsGamePlugin 提供）──

    _players: dict[str, PlayerState]
    _renderer: Any
    config: Any
    ctx: Any
    _save_manager: Any
    _game_data: Any
    _exploration_service: Any
    _exit_service: Any
    _story_manager: Any
    _people_manager: Any
    _quest_manager: Any
    _work_manager: Any
    _work_story_manager: Any
    _char_encounter_service: Any
    _people_relationship_data: dict[str, dict]
    _people_net_text: dict[str, dict]

    # ── 消息节点构建 ──

    @staticmethod
    def _forward_node(user_id: str, user_nickname: str, content: str) -> dict:
        """构建 send.forward() 兼容的转发节点。"""
        return {
            "user_id": user_id,
            "user_nickname": user_nickname,
            "content": [{"type": "text", "data": content}],
        }

    # ── 人物数据加载 ──

    @staticmethod
    def _load_people_net() -> dict[str, dict]:
        """从 br_story/people_story/people_relationship.json 加载人物数据。"""
        file_path = Path(__file__).parent.parent / "br_story" / "people_story" / "people_relationship.json"
        if not file_path.is_file():
            return {}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    # ── 访问 ID 解析 ──

    @staticmethod
    def _resolve_access_id(message: dict, stream_id: str = "") -> tuple[str, str] | None:
        """从消息中解析出 (聊天类型, ID) — 'group'/'private' + 群号/QQ号。

        兼容多种 SDK/Host 版本的消息格式：
        - OneBot v11: message_type + group_id / user_id
        - 新版 SDK (A): message_info.type/chat_type + group_id / user_id
        - 新版 SDK (B): message_info.user_info / group_info 子对象
        - 新版 SDK (C): session_id / stream_id 前缀 group_ / private_
        """
        message_info = message.get("message_info") or {}

        # ── 方案1：OneBot v11 标准字段 ──
        msg_type = message.get("message_type", "")
        if msg_type == "group":
            gid = str(message.get("group_id", ""))
            if gid:
                return ("group", gid)
        elif msg_type == "private":
            uid = str(message.get("user_id", "") or (message.get("sender") or {}).get("user_id", ""))
            if uid:
                return ("private", uid)

        # ── 方案2：message_info 含 user_info / group_info 子对象（当前 SDK 格式）──
        user_info = message_info.get("user_info") or {}
        group_info = message_info.get("group_info") or {}
        if group_info:
            gid = str(group_info.get("group_id", ""))
            if gid:
                return ("group", gid)
        if user_info:
            uid = str(user_info.get("user_id", "") or user_info.get("qq", "") or user_info.get("uin", ""))
            if uid:
                if group_info and group_info.get("group_id"):
                    return ("group", str(group_info["group_id"]))
                return ("private", uid)

        # ── 方案3：message_info 扁平含 type/chat_type ──
        if message_info:
            info_type = str(
                message_info.get("type", "")
                or message_info.get("chat_type", "")
                or message_info.get("sub_type", "")
            )
            if info_type in ("group", "discuss"):
                gid = str(message_info.get("group_id", ""))
                if gid:
                    return ("group", gid)
            elif info_type in ("private", "friend", "guild"):
                uid = str(message_info.get("user_id", "") or message_info.get("sender_id", ""))
                if uid:
                    return ("private", uid)

        # ── 方案4：session_id / stream_id 前缀 group_ / private_ ──
        sid = str(message.get("session_id", "") or stream_id or message.get("stream_id", ""))
        if sid.startswith("group_"):
            return ("group", sid[6:])
        if sid.startswith("private_"):
            return ("private", sid[8:])

        # ── 方案5：通过 platform + message_info 兜底 ──
        platform = str(message.get("platform", ""))
        if platform == "qq":
            gid = str(message_info.get("group_id", ""))
            if gid:
                return ("group", gid)
            uid = str(message_info.get("user_id", "") or message_info.get("sender_id", "")
                   or (message.get("sender") or {}).get("user_id", ""))
            if uid:
                return ("private", uid)

        # ── 方案6：message_info 中直接有 user_id / group_id ──
        gid = str(message_info.get("group_id", ""))
        if gid:
            return ("group", gid)
        uid = str(message_info.get("user_id", "") or message_info.get("sender_id", ""))
        if uid:
            return ("private", uid)

        return None

    @staticmethod
    def _resolve_user_id(message: dict, stream_id: str = "") -> str | None:
        """从消息中解析出发送者的用户 QQ 号。"""
        # OneBot v11
        uid = str(message.get("user_id", "") or (message.get("sender") or {}).get("user_id", ""))
        if uid:
            return uid
        # 新版 SDK: message_info.user_info 子对象
        info = message.get("message_info") or {}
        user_info = info.get("user_info") or {}
        uid = str(user_info.get("user_id", "") or user_info.get("qq", "") or user_info.get("uin", ""))
        if uid:
            return uid
        # 新版 SDK: message_info 扁平字段
        uid = str(info.get("user_id", "") or info.get("sender_id", ""))
        if uid:
            return uid
        # session_id / stream_id 前缀
        sid = str(message.get("session_id", "") or stream_id or message.get("stream_id", ""))
        if sid.startswith("private_"):
            return sid[8:]
        if sid.startswith("group_"):
            uid = str(info.get("user_id", "") or info.get("sender_id", ""))
            if uid:
                return uid
        # 兜底
        if info:
            info_type = str(info.get("type", "") or info.get("chat_type", ""))
            if info_type in ("private", "friend", "guild"):
                uid = str(info.get("user_id", "") or info.get("sender_id", ""))
                if uid:
                    return uid
        return None

    # ── 访问控制 ──

    def _check_blacklist(self, chat_type: str, chat_id: str, user_id: str | None) -> tuple[bool, str]:
        """黑名单检查。返回 (是否允许, 拒绝原因)。黑名单优先级高于白名单。"""
        bl = self.config.blacklist
        if not bl.enabled:
            return True, ""

        if chat_type == "group" and chat_id in bl.group_ids:
            return False, bl.group_deny_message

        target_uid = user_id or chat_id
        if target_uid in bl.user_ids:
            return False, bl.private_deny_message

        return True, ""

    def _check_whitelist(self, chat_type: str, chat_id: str) -> tuple[bool, str]:
        """白名单检查。返回 (是否允许, 拒绝原因)。"""
        wl = self.config.whitelist
        if not wl.enabled:
            return True, ""
        target_ids = wl.group_ids if chat_type == "group" else wl.user_ids
        if not target_ids:
            if chat_type == "group":
                return False, wl.empty_group_list_message
            else:
                return False, wl.empty_private_list_message
        if chat_id not in target_ids:
            if chat_type == "group":
                return False, wl.group_deny_message
            else:
                return False, wl.private_deny_message
        return True, ""

    # ── 玩家管理 ──

    def _get_player(self, user_id: str) -> PlayerState | None:
        """获取玩家状态。"""
        return self._players.get(user_id)

    def _get_or_load_player(self, user_id: str) -> PlayerState | None:
        """获取玩家状态，内存中不存在则尝试从存档文件加载。"""
        player = self._players.get(user_id)
        if player is not None:
            return player
        player = self._save_manager.load(user_id)
        if player is not None:
            self._players[user_id] = player
        return player

    def _save_player(self, user_id: str) -> None:
        """将单个玩家状态保存为 JSON 文件。"""
        player = self._players.get(user_id)
        if player is not None:
            self._save_manager.save(player)

    def _delete_player_save(self, user_id: str) -> None:
        """删除玩家存档文件（游戏结束/通关时调用）。"""
        self._save_manager.delete(user_id)

    # ── 渲染上下文 ──

    def _make_ctx(self, player: PlayerState) -> RenderContext:
        """构建渲染上下文。"""
        return RenderContext(
            health=player.health,
            sanity=player.sanity,
            current_level=player.current_level,
            initial_health=self.config.game.initial_health,
            initial_sanity=self.config.game.initial_sanity,
            inventory_count=len(player.inventory),
            game_config=self.config.game,
            level_info=self._get_level_info(player.current_level),
            exit_attempts=player.exit_attempts,
        )

    # ── 消息发送 ──

    async def _send(self, stream_id: str, text: str, *, nodes: list[dict] | None = None) -> bool:
        """根据配置的消息输出模式发送消息。

        Args:
            stream_id: 消息会话 ID。
            text: 消息文本（nodes 为 None 时发送此文本）。
            nodes: 合并转发节点列表。当提供时，forward 模式使用此列表；
                   text 模式将所有节点内容拼接为单条消息。

        Returns:
            发送是否成功。
        """
        mode = self.config.plugin.output_mode
        if mode == "forward":
            if nodes:
                return await self.ctx.send.forward(nodes, stream_id)
            node = self._forward_node("M.E.G.CN-操作终端", "M.E.G.CN 系统", text)
            return await self.ctx.send.forward([node], stream_id)
        # text 模式
        if nodes:
            combined = "\n\n══════════════════════════\n\n".join(
                n["content"][0]["data"] for n in nodes
            )
            return await self.ctx.send.text(combined, stream_id)
        return await self.ctx.send.text(text, stream_id)

    async def _send_game_event(
        self, stream_id: str, event_text: str, player: PlayerState,
    ) -> bool:
        """发送三段式游戏事件消息（合并转发模式）。

        将消息拆分为三段：
          1. 当前事件 — 游戏核心事件描述
          2. 人物状态 — 生命/理智/物品/进度等
          3. 可用命令 — 根据当前状态显示不同命令列表

        Args:
            stream_id: 消息会话 ID。
            event_text: 核心事件文本。
            player: 玩家状态对象。
        """
        ctx = self._make_ctx(player)

        status_text = self._renderer.render_status_panel(
            ctx,
            currency=player.currency,
            companions=player.companions,
            favorability=player.favorability if player.favorability else None,
        )
        commands_text = self._renderer.render_commands_panel(
            is_at_399=player.fsm.is_at_399(),
            is_dialog=player.fsm.is_dialog(),
        )

        nodes = [
            self._forward_node("M.E.G.CN-操作终端", "M.E.G.CN 系统", event_text),
            self._forward_node("M.E.G.CN-状态面板", "M.E.G.CN 终端", status_text),
            self._forward_node("M.E.G.CN-指令面板", "M.E.G.CN 指令", commands_text),
        ]

        mode = self.config.plugin.output_mode
        if mode == "forward":
            return await self.ctx.send.forward(nodes, stream_id)
        # text 模式：三段拼接为一条消息
        combined = f"{event_text}\n\n{status_text}\n\n{commands_text}"
        return await self.ctx.send.text(combined, stream_id)

    # ── 游戏数据查询 ──

    def _get_level_info(self, level: int) -> dict[str, Any]:
        """获取楼层信息。"""
        return self._game_data.get_level_info(level)

    # ── 物品管理 ──

    @staticmethod
    def _has_item(player: PlayerState, item_name: str) -> bool:
        """检查玩家是否拥有某物品。"""
        return any(item["name"] == item_name for item in player.inventory)

    @staticmethod
    def _item_display_name(item_name: str) -> str:
        """获取物品的显示名称。"""
        for i in ITEMS_POOL:
            if i["name"] == item_name:
                return i.get("display_name", item_name)
        return item_name

    @staticmethod
    def _use_item(player: PlayerState, item_name: str) -> dict | None:
        """使用一个物品，返回物品数据；找不到返回 None。"""
        for i, item in enumerate(player.inventory):
            if item["name"] == item_name:
                return player.inventory.pop(i)
        return None

    def _random_item(self) -> dict:
        """根据配置权重随机选择一个物品。

        Returns:
            dict: 随机选中的物品数据。
        """
        cfg = self.config.game
        weights = {
            "o1": cfg.item_weight_o1,
            "o2": cfg.item_weight_o2,
            "o3": cfg.item_weight_o3,
            "o4": cfg.item_weight_o4,
            "o5": cfg.item_weight_o5,
            "o6": cfg.item_weight_o6,
            "o7": cfg.item_weight_o7,
        }
        return self._game_data.random_item(weights)

    # ── 物资箱 ──

    def _roll_crate(self, player: PlayerState) -> tuple[str, list[dict]] | None:
        """物资箱系统：根据配置概率和当前楼层生成物资箱。

        Args:
            player: 玩家状态（用于判断是否在 Level 0）。

        Returns:
            (箱型名称, 物品列表) 或 None（无物资箱）。
        """
        if player.current_level == 0:
            return None

        cfg = self.config.game

        r = random.random()
        crate_size: str | None = None
        if r < cfg.crate_large_chance:
            crate_size = "大型物资箱"
        elif r < cfg.crate_large_chance + cfg.crate_medium_chance:
            crate_size = "中型物资箱"
        elif r < cfg.crate_large_chance + cfg.crate_medium_chance + cfg.crate_small_chance:
            crate_size = "小型物资箱"

        if crate_size is None:
            return None

        items: list[dict] = []
        almond_water = {"name": "o1", "type": "consumable", "effect": "sanity_restore", "value": 30,
                        "display_name": "杏仁水",
                        "description": "后室中最常见的补给品，喝下可以恢复理智，味道像融化的杏仁冰淇淋。"}
        items.append(dict(almond_water))

        extra = self._random_item()
        items.append(dict(extra))

        return crate_size, items

    # ── 背包格式化 ──

    @staticmethod
    def _format_inventory(player: PlayerState) -> str:
        """格式化背包内容。"""
        if not player.inventory:
            return "背包是空的。"
        lines = []
        for idx, item in enumerate(player.inventory, 1):
            display = item.get("display_name", item["name"])
            lines.append(f"  [{idx}] {display} — {item['description']}")
        return "\n".join(lines)
