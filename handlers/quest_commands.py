"""后室:逃出生天 — 任务系统命令混入

处理任务系统相关命令：任务面板、接受任务、提交任务。
"""

from __future__ import annotations

from .base import HandlerBase
from ..core.game_data import ITEMS_POOL


class QuestCommandMixin(HandlerBase):
    """任务系统命令处理器混入。

    提供任务面板查看、任务接受、任务提交等 ``_do_*`` 方法。
    """

    async def _do_quest_list(self, stream_id: str) -> None:
        """显示任务面板。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        await self._send(
            stream_id,
            self._renderer.render_quest_list(player, self._quest_manager, ITEMS_POOL),
        )

    async def _do_quest_accept(self, stream_id: str, quest_id: str) -> None:
        """接受任务。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        quest = self._quest_manager.get_quest(quest_id)
        if not quest:
            await self._send(stream_id, f"❌ 任务 [{quest_id}] 不存在。使用 /br quest 查看可用任务。")
            return
        if quest_id in player.active_quests:
            await self._send(stream_id, f"⚠️ 任务「{quest['title']}」已经在进行中了。")
            return
        if quest_id in player.completed_quests:
            await self._send(stream_id, f"⚠️ 任务「{quest['title']}」已经完成了。")
            return

        player.active_quests.add(quest_id)
        player.pending_quest_offer = None
        self._save_player(user_id)
        await self._send(
            stream_id,
            self._renderer.render_quest_accept(quest, ITEMS_POOL),
        )

    async def _do_quest_submit(self, stream_id: str, quest_id: str) -> None:
        """提交任务。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        quest = self._quest_manager.get_quest(quest_id)
        if not quest:
            await self._send(stream_id, f"❌ 任务 [{quest_id}] 不存在。")
            return
        if quest_id not in player.active_quests:
            await self._send(stream_id, f"⚠️ 你没有接受任务「{quest['title']}」。使用 /br quest 查看进行中的任务。")
            return

        if not self._quest_manager.check_quest_complete(quest_id, player):
            await self._send(
                stream_id,
                self._renderer.render_quest_not_complete(quest, player, ITEMS_POOL),
            )
            return

        # 消耗物品类任务：从背包扣除物品
        if quest.get("objective_type") == "use_item":
            item_name = quest.get("objective_item", "")
            count = quest.get("objective_count", 1)

            actual_count = sum(1 for inv in player.inventory if inv.get("name") == item_name)
            if actual_count < count:
                await self._send(
                    stream_id,
                    f"❌ 提交任务需要 {count} 个 {self._item_display_name(item_name)}，但背包中只有 {actual_count} 个。",
                )
                return

            for _ in range(count):
                for idx, inv_item in enumerate(player.inventory):
                    if inv_item.get("name") == item_name:
                        player.inventory.pop(idx)
                        break

        reward_text = self._quest_manager.apply_rewards(quest_id, player)
        self._save_player(user_id)
        await self._send(
            stream_id,
            self._renderer.render_quest_submit(quest, player, reward_text),
        )
