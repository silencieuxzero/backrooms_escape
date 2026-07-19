"""后室:逃出生天 — 故事档案命令混入

处理故事档案相关命令：列出已解锁故事、查看具体故事。
"""

from __future__ import annotations

from .base import HandlerBase


class StoryCommandMixin(HandlerBase):
    """故事档案命令处理器混入。

    提供工作故事档案的查看功能。
    """

    async def _do_story_list(self, stream_id: str) -> None:
        """显示已解锁的工作故事列表。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        await self._send(
            stream_id,
            self._renderer.render_story_list(player.work_stories, self._work_story_manager),
        )

    async def _do_story_view(self, stream_id: str, story_id: str) -> None:
        """通过合并转发消息查看具体故事。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        if story_id not in player.work_stories:
            await self._send(stream_id, f"❌ 故事 [{story_id}] 尚未解锁。使用 /br story 查看已解锁的故事。")
            return

        story_text = self._work_story_manager.get_story(story_id)
        if not story_text:
            await self._send(stream_id, f"⚠️ 故事 [{story_id}] 内容为空。")
            return

        # 从 work_manager 查找对应标题
        title = story_id
        for wid in self._work_manager.work_ids:
            w = self._work_manager.get_work(wid)
            if w and w.get("unlock_story") == story_id:
                title = w.get("title", story_id)
                break

        nodes = [
            self._forward_node("Alpha基地档案室", f"📖 {title}", story_text),
        ]

        await self._send(stream_id, story_text, nodes=nodes)
