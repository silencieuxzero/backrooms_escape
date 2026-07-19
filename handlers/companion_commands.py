"""后室:逃出生天 — 同行与礼物命令混入

处理同伴系统相关命令：邀请同行、解散同行、赠送礼物。
"""

from __future__ import annotations

from .base import HandlerBase
from ..rendering import CHARACTERS
from ..core.player_state import PlayerState


class CompanionCommandMixin(HandlerBase):
    """同伴与礼物命令处理器混入。

    提供角色邀请、解散同行和礼物赠送的 ``_do_*`` 方法。
    依赖 CharacterCommandMixin 提供 ``_auto_end_dialog``。
    """

    async def _do_invite(self, stream_id: str, char_name: str) -> None:
        """邀请角色一起探索后室。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        name_to_id = {meta["name"]: cid for cid, meta in CHARACTERS.items()}
        if char_name in CHARACTERS:
            char_id = char_name
        elif char_name in name_to_id:
            char_id = name_to_id[char_name]
        else:
            available = "、".join(
                CHARACTERS[cid]["name"]
                for cid in player.unlocked_chars
                if cid in CHARACTERS
            ) or "无"
            await self._send(stream_id, f"❌ 不认识「{char_name}」，可邀请的角色：{available}")
            return

        char_meta = CHARACTERS.get(char_id)
        if not char_meta:
            await self._send(stream_id, f"❌ 角色 [{char_id}] 不存在。")
            return

        if char_id not in player.unlocked_chars:
            await self._send(stream_id, f"❌ 你还没有遇到过 {char_meta['name']}，先去对应楼层探索吧。")
            return

        current_fav = player.favorability.get(char_id, 0)
        threshold = self.config.game.favorability_threshold
        if current_fav < threshold:
            char_level = char_meta.get("level", 1)
            await self._send(
                stream_id,
                f"❌ 与 {char_meta['name']} 的好感度还不够（当前 {current_fav}/{threshold}）。\n"
                f"多去 Level {char_level} 遇到她/他，提升好感度吧。",
            )
            return

        if len(player.companions) >= 1:
            if char_id == "xiazhong":
                if "luo_shulv" not in player.companions:
                    await self._send(
                        stream_id,
                        f"❌ 夏终不太信任陌生人，只有在 {CHARACTERS['luo_shulv']['name']} 同行时，她才愿意一起出发。",
                    )
                    return
                if "xiazhong" in player.companions:
                    await self._send(stream_id, "ℹ️ 夏终已经在队伍中了。")
                    return
            else:
                current_names = "、".join(
                    CHARACTERS.get(cid, {}).get("name", cid)
                    for cid in player.companions
                )
                await self._send(
                    stream_id,
                    f"⚠️ {current_names} 正在与你同行。先使用 /br dismiss 送她/他回去，再邀请其他人。",
                )
                return

        player.companions.append(char_id)
        self._save_player(user_id)

        names = "、".join(
            CHARACTERS.get(cid, {}).get("name", cid)
            for cid in player.companions
        )
        await self._send(
            stream_id,
            f"══════════════════════\n"
            f"  🤝 同行邀请\n"
            f"══════════════════════\n\n"
            f"「{char_meta['name']}，愿意和我一起探索后面的楼层吗？」\n\n"
            f"{char_meta['name']}微微一笑，点头答应了。\n\n"
            f"从现在起，{names} 会与你一同前行，\n"
            f"在探索时提供帮助（出口率 +5%），并分享沿途的见闻。\n\n"
            f"使用 /br dismiss 可以送同伴返回 Alpha 基地。",
        )

    async def _do_dismiss(self, stream_id: str) -> None:
        """解散同行角色。

        解散洛疏律时，若夏终也在同行中则一并解除。
        """
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if not player.companions:
            await self._send(stream_id, "ℹ️ 当前没有角色与你同行。")
            return

        dismissed_names = []
        for cid in list(player.companions):
            cname = CHARACTERS.get(cid, {}).get("name", cid)
            dismissed_names.append(cname)
            if cid == "luo_shulv" and "xiazhong" in player.companions:
                player.companions.remove("xiazhong")
                dismissed_names.append(CHARACTERS["xiazhong"]["name"])
            player.companions.remove(cid)

        self._save_player(user_id)
        names_text = "、".join(dismissed_names)
        await self._send(
            stream_id,
            f"══════════════════════\n"
            f"  👋 告别\n"
            f"══════════════════════\n\n"
            f"你送 {names_text} 回到了 Alpha 基地。\n"
            f"「下次需要我的时候，随时来找我。」\n"
            f"她们挥了挥手，转身消失在走廊尽头。",
        )

    async def _do_gift(self, stream_id: str, char_name: str, item_index: int) -> None:
        """赠送背包物品给角色以提升好感度。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        name_to_id = {meta["name"]: cid for cid, meta in CHARACTERS.items()}
        if char_name in CHARACTERS:
            char_id = char_name
        elif char_name in name_to_id:
            char_id = name_to_id[char_name]
        else:
            available = "、".join(
                CHARACTERS[cid]["name"]
                for cid in player.unlocked_chars
                if cid in CHARACTERS
            ) or "无"
            await self._send(stream_id, f"❌ 不认识「{char_name}」，可赠送的角色：{available}")
            return

        char_meta = CHARACTERS.get(char_id)
        if not char_meta:
            await self._send(stream_id, f"❌ 角色 [{char_id}] 不存在。")
            return

        if char_id not in player.unlocked_chars:
            await self._send(stream_id, f"❌ 你还没有遇到过 {char_meta['name']}，先去对应楼层探索吧。")
            return

        if item_index < 1 or item_index > len(player.inventory):
            await self._send(stream_id, self._renderer.render_item_not_found(str(item_index)))
            return

        item = player.inventory.pop(item_index - 1)
        item_name = item.get("name", "")
        item_display = item.get("display_name", item_name)

        gift_values = self.config.game.gift_favorability_values
        fav_increase = gift_values.get(item_name, 1)
        old_fav = player.favorability.get(char_id, 0)
        new_fav = old_fav + fav_increase
        player.favorability[char_id] = new_fav

        await self._send(
            stream_id,
            self._renderer.render_gift_result(
                char_meta["name"], item_display, fav_increase, new_fav,
            ),
        )
        self._save_player(user_id)
