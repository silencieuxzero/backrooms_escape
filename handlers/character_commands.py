"""后室:逃出生天 — 角色交互命令混入

处理角色相关命令：人物关系图、LLM 对话模式。
同伴邀请/解散/赠礼已移至 ``companion_commands.py``。
"""

from __future__ import annotations

from .base import HandlerBase
from ..rendering import CHARACTERS, build_system_prompt, build_message_list, trim_history, is_end_dialog, strip_cot
from ..core.state_machine import GameEvent
from ..core.player_state import PlayerState


class CharacterCommandMixin(HandlerBase):
    """角色交互命令处理器混入。

    提供人物关系图、LLM 对话模式（开始/选择/自动结束）等 ``_do_*`` 方法。
    """

    async def _do_people_net(self, stream_id: str) -> None:
        """显示人物关系图。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        unlocked: set[str] = set()
        if player and player.fsm.is_playable():
            unlocked = player.unlocked_chars
        await self._send(
            stream_id,
            self._renderer.render_people_net(self._people_net_text, unlocked, player.favorability if player else None),
        )

    # ── 对话模式（LLM 驱动）──

    async def _do_said(self, stream_id: str, char_input: str) -> None:
        """与指定角色进入 LLM 驱动的自由对话模式。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_alive():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        # 将中文名映射为角色 ID
        name_to_id = {meta["name"]: cid for cid, meta in CHARACTERS.items()}
        if char_input in CHARACTERS:
            char_id = char_input
        elif char_input in name_to_id:
            char_id = name_to_id[char_input]
        else:
            available = "、".join(
                CHARACTERS[cid]["name"]
                for cid in player.unlocked_chars
                if cid in CHARACTERS
            ) or "无"
            await self._send(stream_id, f"❌ 不认识「{char_input}」，可对话的角色：{available}")
            return

        char_meta = CHARACTERS.get(char_id)
        if not char_meta:
            await self._send(stream_id, f"❌ 角色 [{char_id}] 不存在。")
            return

        if char_id not in player.unlocked_chars:
            await self._send(stream_id, f"❌ 你还没有遇到过 {char_meta['name']}，先去对应的楼层探索吧。")
            return

        # 检查是否已经在对话模式中
        if player.fsm.is_dialog():
            await self._send(stream_id, "❌ 你已经在对话模式中了。输入「结束对话」或「0」结束当前对话。")
            return

        # 进入对话模式
        player.fsm.apply(GameEvent.ENTER_DIALOG)
        player.dialog_char_id = char_id
        player.dialog_history = []
        self._save_player(user_id)

        # 用 LLM 生成角色开场白
        char_name = char_meta.get("name", char_id)
        await self._send(
            stream_id,
            f"══ 与 {char_name} 的对话 ══\n"
            f"(你可以自由输入想说的话，输入「结束对话」或「0」结束对话)\n",
        )

        system_prompt = build_system_prompt(char_id, self._people_relationship_data)
        messages = build_message_list(system_prompt, [], f"{char_name}遇到了玩家，打一声招呼开始对话吧。")

        try:
            result = await self.ctx.llm.generate(prompt=messages, model=self.config.game.dialog_model or "replyer")
            if result.get("success"):
                reply = strip_cot(result.get("response", ""))
                if reply:
                    player.dialog_history.append({"role": "assistant", "content": reply})
                    self._save_player(user_id)
                    await self._send(stream_id, f"—— {char_name} ——\n\n{reply}")
                    return
        except Exception as exc:
            self.ctx.logger.error("LLM 生成开场白失败: %s", exc)

        # LLM 调用失败的 fallback
        await self._send(stream_id, f"—— {char_name} ——\n\n「……你来了。」")

    async def _auto_end_dialog(self, stream_id: str, player: PlayerState) -> None:
        """自动结束对话模式，让角色进行自然告别。"""
        if not player.fsm.is_dialog():
            return

        char_id = player.dialog_char_id
        if not char_id:
            player.fsm.apply(GameEvent.END_DIALOG)
            player.dialog_char_id = None
            player.dialog_history = []
            self._save_player(str(stream_id))
            return

        char_meta = CHARACTERS.get(char_id, {})
        char_name = char_meta.get("name", char_id)

        farewell_text = ""
        try:
            system_prompt = build_system_prompt(char_id, self._people_relationship_data)
            farewell_history = player.dialog_history + [
                {"role": "user", "content": f"{char_name}，我有事要先走了。"}
            ]
            farewell_messages = build_message_list(system_prompt, farewell_history, f"{char_name}突然有急事要离开，自然地告别。")
            result = await self.ctx.llm.generate(prompt=farewell_messages, model=self.config.game.dialog_model or "replyer")
            if result.get("success"):
                farewell_text = strip_cot(result.get("response", ""))
        except Exception as exc:
            self.ctx.logger.error("自动告别 LLM 生成失败: %s", exc)

        player.fsm.apply(GameEvent.END_DIALOG)
        player.dialog_char_id = None
        player.dialog_history = []
        self._save_player(str(stream_id))

        if farewell_text:
            await self._send(stream_id, f"—— {char_name} ——\n\n{farewell_text}\n")
        else:
            await self._send(stream_id, f"「{char_name}」点了点头，向你告别。\n")

    async def _do_dialog_choice(self, stream_id: str, user_input: str) -> None:
        """处理对话模式中的玩家输入，调用 LLM 生成角色回复。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_dialog():
            return

        char_id = player.dialog_char_id
        if not char_id:
            player.fsm.apply(GameEvent.END_DIALOG)
            player.dialog_char_id = None
            self._save_player(user_id)
            return

        char_meta = CHARACTERS.get(char_id, {})
        char_name = char_meta.get("name", char_id)
        user_input = user_input.strip()

        # 检查是否要结束对话
        if is_end_dialog(user_input):
            system_prompt = build_system_prompt(char_id, self._people_relationship_data)
            farewell_history = player.dialog_history + [
                {"role": "user", "content": f"{char_name}，我要走了。"}
            ]
            farewell_messages = build_message_list(system_prompt, farewell_history, f"{char_name}要离开了，自然地告别。")

            player.fsm.apply(GameEvent.END_DIALOG)
            player.dialog_char_id = None
            player.dialog_history = []
            self._save_player(user_id)

            farewell_text = ""
            try:
                result = await self.ctx.llm.generate(prompt=farewell_messages, model=self.config.game.dialog_model or "replyer")
                if result.get("success"):
                    farewell_text = strip_cot(result.get("response", ""))
            except Exception:
                pass

            if farewell_text:
                await self._send(stream_id, f"—— {char_name} ——\n\n{farewell_text}\n\n══ 对话结束 ══\n\n使用 /br said <角色名> 可以再次开始对话。")
            else:
                await self._send(stream_id, f"══ 对话结束 ══\n\n你结束了与 {char_name} 的对话。\n\n使用 /br said <角色名> 可以再次开始对话。")
            return

        # 正常对话：调用 LLM 生成回复
        system_prompt = build_system_prompt(char_id, self._people_relationship_data)
        history = trim_history(player.dialog_history)
        messages = build_message_list(system_prompt, history, user_input)

        player.dialog_history.append({"role": "user", "content": user_input})
        self._save_player(user_id)

        try:
            result = await self.ctx.llm.generate(prompt=messages, model=self.config.game.dialog_model or "replyer")
            if result.get("success"):
                reply = strip_cot(result.get("response", ""))
                if reply:
                    player.dialog_history.append({"role": "assistant", "content": reply})
                    player.dialog_history = trim_history(player.dialog_history)
                    self._save_player(user_id)
                    await self._send(stream_id, f"—— {char_name} ——\n\n{reply}")
                    return
        except Exception as exc:
            self.ctx.logger.error("LLM 对话生成失败: %s", exc)

        await self._send(stream_id, f"—— {char_name} ——\n\n（{char_name}似乎走神了，没有听清你在说什么。）")

    # _do_invite / _do_dismiss / _do_gift 已移至 handlers/companion_commands.py
