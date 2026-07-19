"""后室:逃出生天 — 基地工作命令混入

处理基地工作系统相关命令：工作面板、开始工作、提交答案。
"""

from __future__ import annotations

from .base import HandlerBase
from ..core.game_data import ITEMS_POOL


class WorkCommandMixin(HandlerBase):
    """基地工作命令处理器混入。

    提供 Alpha 基地工作面板的查看与交互功能。
    """

    async def _do_work_list(self, stream_id: str) -> None:
        """显示基地工作面板。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        await self._send(
            stream_id,
            self._renderer.render_work_list(player, self._work_manager),
        )

    async def _do_work_start(self, stream_id: str, work_id: str) -> None:
        """开始工作。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if player.current_level != 1:
            await self._send(stream_id, "⚠️ 基地工作仅在 Level 1 的 M.E.G.CN Alpha 基地进行。")
            return

        work = self._work_manager.get_work(work_id)
        if not work:
            await self._send(stream_id, f"❌ 工作 [{work_id}] 不存在。使用 /br work 查看可接工作。")
            return
        if work_id in player.completed_works:
            await self._send(stream_id, f"⚠️ 工作「{work['title']}」已经完成了。")
            return

        await self._send(
            stream_id,
            self._renderer.render_work_start(work, work_id),
        )

    async def _do_work_answer(self, stream_id: str, work_id: str, answer: str) -> None:
        """提交工作答案。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        work = self._work_manager.get_work(work_id)
        if not work:
            await self._send(stream_id, f"❌ 工作 [{work_id}] 不存在。")
            return
        if work_id in player.completed_works:
            await self._send(stream_id, f"⚠️ 工作「{work['title']}」已经完成。")
            return

        if self._work_manager.check_answer(work_id, answer):
            # 正确：发放奖励
            player.currency += work.get("reward_currency", 0)
            for item_name in work.get("reward_items", []):
                for template in ITEMS_POOL:
                    if template["name"] == item_name:
                        player.inventory.append(dict(template))
                        break
            player.completed_works.add(work_id)
            story_id = work.get("unlock_story", "")
            story_text = None
            if story_id:
                player.work_stories.add(story_id)
                story_text = self._work_story_manager.get_story(story_id)
            self._save_player(user_id)
            await self._send(
                stream_id,
                self._renderer.render_work_success(work, player, story_text, ITEMS_POOL),
            )
        else:
            await self._send(
                stream_id,
                self._renderer.render_work_failure(work),
            )
