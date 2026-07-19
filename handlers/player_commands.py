"""后室:逃出生天 — 玩家状态命令混入

处理玩家状态相关命令：查看状态、背包、使用物品、帮助、阅读纸条。
"""

from __future__ import annotations

from .base import HandlerBase
from ..core.game_data import ITEMS_POOL


class PlayerCommandMixin(HandlerBase):
    """玩家状态命令处理器混入。

    提供查看探员状态、背包管理、游戏帮助等 ``_do_*`` 方法。
    """

    async def _do_status(self, stream_id: str) -> None:
        """查看当前状态。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        ctx = self._make_ctx(player)
        inventory_text = self._format_inventory(player)
        await self._send(
            stream_id,
            self._renderer.render_status(ctx, inventory_text, player.currency, player.favorability, player.companions),
        )

    async def _do_show_inventory(self, stream_id: str) -> None:
        """查看背包。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        inventory_text = self._format_inventory(player)

        hints = []
        if self._has_item(player, "o4"):
            hints.append("🔑 你持有楼层钥匙！使用 /br exit 可以 100% 找到出口。")
        if self._has_item(player, "o1") and player.sanity < 50:
            hints.append("🧠 理智值偏低，使用 /br use <编号> 可以恢复。")
        if self._has_item(player, "o2") and player.health < 50:
            hints.append("❤️ 生命值偏低，使用 /br use <编号> 派得上用场。")
        if self._has_item(player, "o3"):
            hints.append("🔦 手电筒能驱散笑魇，+5% 出口发现率。")

        if not hints:
            hints.append("探索楼层时有几率找到更多物品。使用 /br explore 开始探索。")

        await self._send(
            stream_id,
            self._renderer.render_inventory(inventory_text, hints),
        )

    async def _do_help(self, stream_id: str) -> None:
        """游戏帮助。"""
        await self._send(stream_id, self._renderer.render_help())

    async def _do_read(self, stream_id: str) -> None:
        """阅读捡到的纸条（直接由 handle_read 调用）。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)

        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        if not player.pending_note:
            await self._send(stream_id, self._renderer.render_no_note())
            return

        note_text = player.pending_note
        player.pending_note = None

        self.ctx.logger.info("发送纸条: note_len=%d", len(note_text))
        await self._send(
            stream_id,
            note_text,
            nodes=[self._forward_node("M.E.G.CN-档案部", "M.E.G.CN 档案部 | 回收纸条", note_text)],
        )
