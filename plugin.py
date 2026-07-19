"""后室:逃出生天 — 游戏插件

扮演 M.E.G.CN 工作人员，从 Level 0 出发，在后室中寻找出口不断切入下一个楼层，
直至找到最终出口 Level 399。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from pathlib import Path
from typing import Any

from maibot_sdk import Command, HookHandler, MaiBotPlugin
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy

from .config import BackroomsGameConfig

# ── 核心层 ──
from .core import (
    GameState,
    GameEvent,
    GameStateMachine,
    PlayerState,
    GameDataService,
    ExplorationService,
    ExitService,
    load_items_pool,
    ITEMS_POOL,
    ENTITIES,
    EXPLORE_EVENTS,
    BASE_EXPLORE_EVENTS,
    SHORTCUT_POOL,
)

# ── 渲染层 ──
from .rendering import BackroomsRenderer, RenderContext
from .rendering import (  # story_load re-exports
    CHARACTERS,
    CharacterEncounterService,
    build_system_prompt,
    build_message_list,
    trim_history,
    is_end_dialog,
    strip_cot,
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
    ShutManager,
)

# ── 持久化层 ──
from .persistence import SaveManager

# 模块导入时加载物品/实体数据
load_items_pool()


# ==================== 版本常量 ====================

PLUGIN_VERSION = "1.2.0"
"""插件版本号（与 _manifest.json 同步）。"""

SAVE_VERSION = "1.2.0"
"""存档数据格式版本号，用于存档迁移兼容。"""


# ==================== 插件主体 ====================

class BackroomsGamePlugin(MaiBotPlugin):
    """后室:逃出生天游戏插件"""

    config_model = BackroomsGameConfig

    async def on_load(self) -> None:
        """插件加载时初始化玩家数据存储，并恢复已有存档。"""
        self._players: dict[str, PlayerState] = {}
        self._story_manager = StoryManager()
        self._people_manager = PeopleStoryManager()
        self._quest_manager = QuestManager(ITEMS_POOL)
        self._work_manager = WorkManager()
        self._work_story_manager = BaseWorkStoryManager()
        self._char_encounter_service = CharacterEncounterService(ITEMS_POOL)
        self._people_relationship_data = self._load_people_net()
        self._people_net_text = self._people_relationship_data  # 指向同一份数据，避免重复加载
        self._renderer = BackroomsRenderer()
        self._plugin_disabled: bool = False
        self._admin_ids: set[str] = set()

        # 创建持久化数据目录
        self._data_dir = Path(__file__).parent / "br_data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.logger.info("br_data 目录已就绪: %s", self._data_dir)

        # 初始化新模块服务
        self._save_manager = SaveManager(self)
        self._game_data = GameDataService()
        self._exploration_service = ExplorationService(self)
        self._exit_service = ExitService(self)

        # 初始化群聊静默管理器
        self._shut_manager = ShutManager(self._data_dir)
        self.ctx.logger.info(
            "已加载 %d 个静默群组: %s",
            len(self._shut_manager.list_shut()),
            self._shut_manager.list_shut() or "无",
        )

        # 从配置读取管理员 ID 列表（只能通过修改配置文件来增减）
        self._admin_ids = set(
            uid.strip() for uid in self.config.plugin.admin_ids if uid.strip()
        )
        if self._admin_ids:
            self.ctx.logger.info("管理员已配置: %s", sorted(self._admin_ids))
        else:
            self.ctx.logger.info("未配置管理员，无用户可执行管理操作")

        # ---- 版本迁移检查 ----

        # 检测配置版本并自动迁移
        await self._migrate_config_if_needed()

        # 恢复已有玩家存档（含自动迁移）
        self._load_all_players()
        self.ctx.logger.info(
            "已从 br_data 恢复 %d 位玩家存档 (存档格式版本: %s)",
            len(self._players), SAVE_VERSION,
        )

        # 输出故事加载状态
        self.ctx.logger.info(
            "故事纸条已加载 %d 条, 人物剧情: %s",
            self._story_manager.story_count,
            {cid: self._people_manager.get_story_count(cid) for cid in self._people_manager.character_ids},
        )

        # 输出访问控制状态，便于排查私聊不可用问题
        wl = self.config.whitelist
        bl = self.config.blacklist
        self.ctx.logger.info(
            "访问控制状态: whitelist.enabled=%s group_ids=%s user_ids=%s | "
            "blacklist.enabled=%s group_ids=%s user_ids=%s",
            wl.enabled, wl.group_ids, wl.user_ids,
            bl.enabled, bl.group_ids, bl.user_ids,
        )

    async def on_unload(self) -> None:
        """插件卸载时保存玩家数据并清理。"""
        self._save_all_players()
        self.ctx.logger.info("已将 %d 位玩家存档保存至 br_data", len(self._players))
        self._players.clear()

    async def on_config_update(self, scope: str, config_data: dict[str, object], version: str) -> None:
        """处理配置热重载，检测版本变更并执行配置迁移。"""
        del config_data
        del version
        self.ctx.logger.info("配置已更新 (scope=%s)", scope)

        # 热重载后重新读取管理员列表
        self._admin_ids = set(
            uid.strip() for uid in self.config.plugin.admin_ids if uid.strip()
        )
        self.ctx.logger.info("管理员列表已刷新: %s", sorted(self._admin_ids) if self._admin_ids else "空")

        # 检测热重载后的配置版本，必要时迁移
        current_ver = self.config.plugin.config_version
        if current_ver != PLUGIN_VERSION:
            self.ctx.logger.info(
                "配置热重载检测到旧版配置 (config_version=%s)，正在迁移至 %s……",
                current_ver, PLUGIN_VERSION,
            )
            self.config.plugin.config_version = PLUGIN_VERSION
            self.ctx.logger.info("配置已迁移至 %s", PLUGIN_VERSION)

    # ==================== 游戏命令（@Command 组件） ====================

    @Command(
        "br_test",
        description="测试插件连通性 — 验证插件是否能正常接收和处理消息",
        pattern=r"^/br\s+test$",
    )
    async def handle_test(self, **kwargs: Any):
        """测试命令：回显确认插件正常接收消息。"""
        # 兼容不同 SDK/Host 版本的 stream_id 传递方式
        stream_id = str(
            kwargs.get("stream_id", "")
            or kwargs.get("message", {}).get("stream_id", "")
        )
        self.ctx.logger.info(
            "br_test 被调用 stream_id=%r kwargs_keys=%s",
            stream_id,
            list(kwargs.keys()),
        )
        if not stream_id:
            self.ctx.logger.error("br_test: stream_id 为空，无法回复消息。kwargs=%s", kwargs)
        success = await self._send(
            stream_id,
            self._renderer.render_test(),
        )
        self.ctx.logger.info("br_test: send.text 结果=%s", success)
        return True, "插件连通性测试通过", 1

    @Command(
        "br_story",
        description="故事档案 — 查看已解锁的工作故事",
        pattern=r"^/br\s+story",
    )
    async def handle_story(self, **kwargs: Any):
        """查看工作故事面板。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+story\s+(\w+)", raw_text)
        if m:
            story_id = m.group(1)
            await self._do_story_view(stream_id, story_id)
        else:
            await self._do_story_list(stream_id)
        return True, "故事面板处理完成", 1

    # ==================== 转发消息工具方法 ====================

    @staticmethod
    def _forward_node(user_id: str, user_nickname: str, content: str) -> dict:
        """构建 send.forward() 兼容的转发节点。"""
        return {
            "user_id": user_id,
            "user_nickname": user_nickname,
            "content": [{"type": "text", "data": content}],
        }

    @staticmethod
    def _load_people_net() -> dict[str, dict]:
        """从 br_story/people_story/people_relationship.json 加载人物数据。"""
        file_path = Path(__file__).parent / "br_story" / "people_story" / "people_relationship.json"
        if not file_path.is_file():
            return {}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    @Command(
        "br_start",
        description="开始新游戏 — 从 Level 0 出发",
        pattern=r"^/br\s+start$",
    )
    async def handle_start(self, **kwargs: Any):
        """开始新游戏。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_start(stream_id)
        return True, "新游戏已开始", 1

    @Command(
        "br_explore_base",
        description="在 Alpha 基地内探索 — 发现基地场景并遇到不同人物",
        pattern=r"^/br\s+explore\s+base$",
    )
    async def handle_explore_base(self, **kwargs: Any):
        """在 Alpha 基地内探索。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_explore_base(stream_id)
        return True, "基地探索完成", 1

    @Command(
        "br_explore",
        description="探索当前楼层 — 可能发现物品或遭遇实体",
        pattern=r"^/br\s+explore$",
    )
    async def handle_explore(self, **kwargs: Any):
        """探索当前楼层。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_explore(stream_id)
        return True, "探索完成", 1

    @Command(
        "br_read",
        description="阅读捡到的纸条 — 通过合并转发消息展示内容",
        pattern=r"^/br\s+read$",
    )
    async def handle_read(self, **kwargs: Any):
        """阅读捡到的纸条。"""
        stream_id = kwargs.get("stream_id", "")
        user_id = str(stream_id)
        player = self._get_player(user_id)

        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return True, "未开始游戏", 1

        if not player.pending_note:
            await self._send(stream_id, self._renderer.render_no_note())
            return True, "无纸条", 1

        note_text = player.pending_note
        player.pending_note = None

        self.ctx.logger.info("发送纸条: note_len=%d", len(note_text))
        await self._send(
            stream_id,
            note_text,
            nodes=[self._forward_node("M.E.G.CN-档案部", "M.E.G.CN 档案部 | 回收纸条", note_text)],
        )

        return True, "纸条已阅读", 1

    @Command(
        "br_exit",
        description="尝试寻找出口 — 概率进入下一楼层",
        pattern=r"^/br\s+exit$",
    )
    async def handle_exit(self, **kwargs: Any):
        """尝试寻找出口。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_exit(stream_id)
        return True, "出口搜索完成", 1

    @Command(
        "br_exit_to",
        description="回溯楼层 — 尝试回到已访问过的指定楼层，如 /br exit l1 回到 Level 1",
        pattern=r"^/br\s+exit\s+l(\d+)$",
    )
    async def handle_exit_to(self, **kwargs: Any):
        """回溯到已访问过的指定楼层。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+exit\s+l(\d+)", raw_text)
        if m:
            target = int(m.group(1))
            await self._do_exit_to_level(stream_id, target)
        return True, "回溯处理完成", 1

    @Command(
        "br_status",
        description="查看探员状态 — 生命值、理智值、当前楼层",
        pattern=r"^/br\s+status$",
    )
    async def handle_status(self, **kwargs: Any):
        """查看当前状态。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_status(stream_id)
        return True, "状态已显示", 1

    @Command(
        "br_inventory",
        description="查看背包 — 显示携带的物品",
        pattern=r"^/br\s+inventory$",
    )
    async def handle_inventory(self, **kwargs: Any):
        """查看背包。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_show_inventory(stream_id)
        return True, "背包已显示", 1

    @Command(
        "br_use",
        description="使用物品 — 按背包编号消耗物品",
        pattern=r"^/br\s+use\s+(?P<index>\d+)$",
    )
    async def handle_use(self, **kwargs: Any):
        """使用背包物品。"""
        stream_id = kwargs.get("stream_id", "")
        matched = kwargs.get("matched_groups", {})
        index_str = matched.get("index", "")
        if not index_str:
            await self._send(stream_id, self._renderer.render_no_item_specified())
            return True, "未指定物品", 1

        item_index = int(index_str)
        await self._do_use_item(stream_id, item_index)
        return True, f"物品 {item_index} 已使用", 1

    @Command(
        "br_help",
        description="游戏帮助 — 显示所有命令和游戏机制",
        pattern=r"^/br\s+help$",
    )
    async def handle_help(self, **kwargs: Any):
        """游戏帮助。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_help(stream_id)
        return True, "帮助已显示", 1

    @Command(
        "br_people_net",
        description="人物关系图 — 显示已解锁角色的背景与关系",
        pattern=r"^/br\s+people_net$",
    )
    async def handle_people_net(self, **kwargs: Any):
        """人物关系图。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_people_net(stream_id)
        return True, "人物关系已显示", 1

    @Command(
        "br_say",
        description="对话 — 在对话模式下输入想说的话",
        pattern=r"^/br\s+say\s+(.+)",
    )
    async def handle_say(self, **kwargs: Any):
        """对话模式下，将玩家输入传给 LLM 生成角色回复。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+say\s+(.+)", raw_text)
        if m:
            content = m.group(1).strip()
            if content:
                user_id = str(stream_id)
                player = self._get_player(user_id)
                if not player or not player.fsm.is_dialog():
                    await self._send(stream_id, "❌ 当前不在对话模式中。请先使用 /br said <角色名> 开始对话。")
                    return True, "未处于对话模式", 1

                asyncio.ensure_future(self._do_dialog_choice(stream_id, content))
                return True, "对话回复已发送", 1

        await self._send(stream_id, "❌ 请输入想说的话，例如：/br say 你好")
        return True, "未输入对话内容", 1

    @Command(
        "br_off",
        description="管理员关闭插件 — 拒绝除管理员外的所有用户使用",
        pattern=r"^/br\s+off$",
    )
    async def handle_off(self, **kwargs: Any):
        """管理员关闭插件。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        await self._do_off(stream_id, message)
        return True, "插件关闭处理完成", 1

    @Command(
        "br_on",
        description="管理员重新启用插件",
        pattern=r"^/br\s+on$",
    )
    async def handle_on(self, **kwargs: Any):
        """管理员重新启用插件。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        await self._do_on(stream_id, message)
        return True, "插件启用处理完成", 1

    @Command(
        "br_shut",
        description="管理员开关群聊静默 — 静默后群内非 /br 消息不会触发 Planner",
        pattern=r"^/br\s+shut(\s+\S+)?$",
    )
    async def handle_shut(self, **kwargs: Any):
        """管理员切换群聊静默状态。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        await self._do_shut(stream_id, message)
        return True, "群聊静默处理完成", 1

    @Command(
        "br_quest",
        description="任务系统 — 查看任务 / 接受任务 / 提交任务",
        pattern=r"^/br\s+quest",
    )
    async def handle_quest(self, **kwargs: Any):
        """任务面板。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+quest\s+accept\s+(\w+)", raw_text)
        if m:
            await self._do_quest_accept(stream_id, m.group(1))
            return True, "任务接受处理完成", 1
        m = re.search(r"/br\s+quest\s+submit\s+(\w+)", raw_text)
        if m:
            await self._do_quest_submit(stream_id, m.group(1))
            return True, "任务提交处理完成", 1
        await self._do_quest_list(stream_id)
        return True, "任务面板已显示", 1

    @Command(
        "br_work",
        description="基地工作 — 在 Level 1 Alpha 基地参与日常工作（解谜）",
        pattern=r"^/br\s+work",
    )
    async def handle_work(self, **kwargs: Any):
        """基地工作系统。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+work\s+start\s+(\w+)", raw_text)
        if m:
            await self._do_work_start(stream_id, m.group(1))
            return True, "工作开始处理完成", 1
        m = re.search(r"/br\s+work\s+answer\s+(\w+)\s+(.+)", raw_text)
        if m:
            await self._do_work_answer(stream_id, m.group(1), m.group(2).strip())
            return True, "工作答案处理完成", 1
        await self._do_work_list(stream_id)
        return True, "工作面板已显示", 1

    @Command(
        "br_invite",
        description="邀请角色同行 — 好感度达标后可邀请角色一起探索后室",
        pattern=r"^/br\s+invite\s+([\u4e00-\u9fffA-Za-z]+)",
    )
    async def handle_invite(self, **kwargs: Any):
        """邀请角色一起探索。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+invite\s+([\u4e00-\u9fffA-Za-z]+)", raw_text)
        if m:
            await self._do_invite(stream_id, m.group(1).lower())
        return True, "邀请处理完成", 1

    @Command(
        "br_dismiss",
        description="解散同行 — 让同行的角色返回基地",
        pattern=r"^/br\s+dismiss$",
    )
    async def handle_dismiss(self, **kwargs: Any):
        """解散同行角色。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_dismiss(stream_id)
        return True, "解散处理完成", 1

    @Command(
        "br_gift",
        description="赠送礼物 — 将背包物品赠送给角色提升好感度",
        pattern=r"^/br\s+gift\s+([\u4e00-\u9fffA-Za-z]+)\s+(\d+)",
    )
    async def handle_gift(self, **kwargs: Any):
        """赠送礼物给角色。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+gift\s+([\u4e00-\u9fffA-Za-z]+)\s+(\d+)", raw_text)
        if m:
            char_name = m.group(1).lower()
            item_index = int(m.group(2))
            await self._do_gift(stream_id, char_name, item_index)
        return True, "赠礼处理完成", 1

    # ==================== 对话模式 ====================

    @Command(
        "br_said",
        description="对话 — 与指定角色进入对话模式",
        pattern=r"^/br\s+said\s+([\u4e00-\u9fffA-Za-z]+)",
    )
    async def handle_said(self, **kwargs: Any):
        """与指定角色进入对话模式。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+said\s+([\u4e00-\u9fffA-Za-z]+)", raw_text)
        if m:
            await self._do_said(stream_id, m.group(1))
        return True, "对话模式处理完成", 1

    # ==================== 访问控制拦截 ====================

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
                # 同时有 group_info 就是群聊，否则私聊
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

    def _check_blacklist(self, chat_type: str, chat_id: str, user_id: str | None) -> tuple[bool, str]:
        """黑名单检查。返回 (是否允许, 拒绝原因)。黑名单优先级高于白名单。"""
        bl = self.config.blacklist
        if not bl.enabled:
            return True, ""

        # 群聊：检查群号是否在黑名单中
        if chat_type == "group" and chat_id in bl.group_ids:
            return False, bl.group_deny_message

        # 私聊/用户：检查用户 QQ 号是否在黑名单中
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
            # 白名单启用但对应类型的列表为空 → 该类型全部拒绝
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

    @HookHandler(
        "chat.command.before_execute",
        name="br_access_check",
        description="在执行 /br 命令前检查黑名单和白名单权限",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def check_access_before_command(self, **kwargs: Any):
        """命令执行前检查黑名单和白名单。"""
        command_name = str(kwargs.get("command_name", "") or kwargs.get("name", ""))

        # 只有 /br 命令需要检查
        if not command_name.startswith("br_"):
            return {"action": "continue"}

        message = kwargs.get("message", {})
        if not message:
            self.ctx.logger.warning("access_check: message 为空，跳过检查 command_name=%s", command_name)
            return {"action": "continue"}

        # 提前提取 stream_id，供后续解析使用
        stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))

        resolved = self._resolve_access_id(message, stream_id)
        if resolved is None:
            mi = message.get("message_info") or {}
            self.ctx.logger.warning(
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
        user_id = self._resolve_user_id(message, stream_id)

        self.ctx.logger.info(
            "access_check: 解析成功 command_name=%s chat_type=%s chat_id=%s user_id=%s",
            command_name, chat_type, chat_id, user_id,
        )

        # 黑名单优先于白名单
        allowed, reason = self._check_blacklist(chat_type, chat_id, user_id)
        if not allowed:
            self.ctx.logger.info(
                "access_check: 黑名单拦截 chat_type=%s chat_id=%s user_id=%s reason=%s",
                chat_type, chat_id, user_id, reason,
            )
            if stream_id:
                await self.ctx.send.text(f"🚫 {reason}", stream_id)
            return {"action": "abort"}

        allowed, reason = self._check_whitelist(chat_type, chat_id)
        if not allowed:
            self.ctx.logger.info(
                "access_check: 白名单拦截 chat_type=%s chat_id=%s reason=%s",
                chat_type, chat_id, reason,
            )
            if stream_id:
                await self.ctx.send.text(f"🚫 {reason}", stream_id)
            return {"action": "abort"}

        # 插件禁用检查：禁用状态下仅管理员可继续使用
        if self._plugin_disabled:
            if command_name not in ("br_off", "br_on") and user_id not in self._admin_ids:
                self.ctx.logger.info(
                    "access_check: 插件已禁用，拒绝非管理员 user_id=%s command_name=%s",
                    user_id, command_name,
                )
                if stream_id:
                    await self.ctx.send.text("🚫 插件已由管理员关闭。", stream_id)
                return {"action": "abort"}

        return {"action": "continue"}

    @HookHandler(
        "chat.command.after_execute",
        name="br_skip_planner",
        description="确保 /br 命令处理后不进入 Planner/LLM 处理链",
        mode=HookMode.BLOCKING,
        order=HookOrder.LATE,
        error_policy=ErrorPolicy.LOG,
    )
    async def skip_planner_after_command(self, **kwargs: Any):
        """命令执行后标记消息已被消费，避免进入 Planner。"""
        command_name = str(kwargs.get("command_name", "") or kwargs.get("name", ""))
        if not command_name.startswith("br_"):
            return {"action": "continue"}
        self.ctx.logger.debug("skip_planner: 标记命令 %s 已处理", command_name)
        # 修改返回结果阻止进一步处理
        return {"result": (True, "命令已处理", 1)}

    @HookHandler(
        "chat.receive.before_process",
        name="br_dialog_handler",
        description="拦截对话模式下玩家的非命令消息，路由至 LLM 对话处理器",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def handle_dialog_message(self, **kwargs: Any):
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

        # 从多个来源提取用户标识，尽可能匹配玩家
        stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))
        user_id = str(stream_id)
        if not user_id:
            return {"action": "continue"}

        # 尝试从内存或存档加载玩家
        player = self._get_or_load_player(user_id)
        if not player or not player.fsm.is_dialog():
            return {"action": "continue"}

        self.ctx.logger.info("对话模式: 拦截玩家 %s 的输入 → LLM 角色回复", user_id)
        asyncio.ensure_future(self._do_dialog_choice(stream_id, raw_text.strip()))
        return {"action": "abort"}

    @HookHandler(
        "chat.receive.before_process",
        name="br_shut_check",
        description="检查消息所在群组是否被 shut，阻止非 /br 消息进入 Planner",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def check_shut_before_process(self, **kwargs: Any):
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

        # 解析访问 ID
        stream_id = str(kwargs.get("stream_id", "") or message.get("stream_id", ""))
        resolved = self._resolve_access_id(message, stream_id)
        if resolved is None:
            return {"action": "continue"}

        chat_type, chat_id = resolved

        if chat_type != "group":
            return {"action": "continue"}

        # 检查是否被静默
        if self._shut_manager.is_shut(chat_id):
            self.ctx.logger.debug("shut: 拦截群 %s 的非 /br 消息", chat_id)
            return {"action": "abort"}

        return {"action": "continue"}

    # ==================== 辅助方法 ====================

    def _save_player(self, user_id: str) -> None:
        """将单个玩家状态保存为 JSON 文件。"""
        player = self._players.get(user_id)
        if player is not None:
            self._save_manager.save(player)

    def _load_player(self, user_id: str) -> PlayerState | None:
        """从 JSON 文件加载单个玩家状态；文件不存在则返回 None。"""
        return self._save_manager.load(user_id)

    def _delete_player_save(self, user_id: str) -> None:
        """删除玩家存档文件（游戏结束/通关时调用）。"""
        self._save_manager.delete(user_id)

    def _save_all_players(self) -> None:
        """批量保存所有玩家状态。"""
        for player in self._players.values():
            self._save_manager.save(player)

    def _load_all_players(self) -> None:
        """批量加载所有玩家存档恢复至内存。"""
        self._save_manager.load_all(self._players)

    # ==================== 存档迁移 ====================

    @staticmethod
    def _migrate_save_data(data: dict) -> dict:
        """将旧版存档数据迁移至当前存档格式。

        旧版存档（v1.0.1 / v1.0.2）没有 ``save_version`` 字段。
        该方法作为扩展点，后续版本如有存档格式变更，
        在此处添加对应版本的分支迁移逻辑即可。

        Args:
            data: 从 JSON 加载的原始存档字典。

        Returns:
            迁移后的存档字典（当前格式）。
        """
        from .persistence.save_manager import SaveManager as _SM
        data = _SM._migrate(data)
        data["save_version"] = SAVE_VERSION
        return data

    async def _migrate_config_if_needed(self) -> None:
        """检测配置文件版本，必要时执行配置迁移。

        当 ``config.toml`` 中的 ``config_version`` 低于当前插件版本时，
        记录日志并执行已知的配置字段迁移。
        此方法仅在 ``on_load`` 中调用一次。
        """
        current_ver = self.config.plugin.config_version
        if current_ver != PLUGIN_VERSION:
            self.ctx.logger.info(
                "检测到旧版配置文件 (config_version=%s)，正在迁移至 %s……",
                current_ver, PLUGIN_VERSION,
            )
            # 在此处添加未来版本的配置迁移逻辑：
            # 例如字段重命名、默认值变更后的补偿处理等
            self.config.plugin.config_version = PLUGIN_VERSION
            self.ctx.logger.info("配置文件已迁移至 %s", PLUGIN_VERSION)
        else:
            self.ctx.logger.info("配置文件版本为最新 (%s)", PLUGIN_VERSION)

    def _get_player(self, user_id: str) -> PlayerState | None:
        """获取玩家状态。"""
        return self._players.get(user_id)

    def _get_or_load_player(self, user_id: str) -> PlayerState | None:
        """获取玩家状态，内存中不存在则尝试从存档文件加载。"""
        player = self._players.get(user_id)
        if player is not None:
            return player
        player = self._load_player(user_id)
        if player is not None:
            self._players[user_id] = player
        return player

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
            # 将多节点拼接为单条消息
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

    def _get_level_info(self, level: int) -> dict[str, Any]:
        """获取楼层信息。"""
        return self._game_data.get_level_info(level)

    def _has_item(self, player: PlayerState, item_name: str) -> bool:
        """检查玩家是否拥有某物品。"""
        return any(item["name"] == item_name for item in player.inventory)

    def _item_display_name(self, item_name: str) -> str:
        """获取物品的显示名称。"""
        for i in ITEMS_POOL:
            if i["name"] == item_name:
                return i.get("display_name", item_name)
        return item_name

    def _use_item(self, player: PlayerState, item_name: str) -> dict | None:
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

    def _roll_crate(self, player: PlayerState) -> tuple[str, list[dict]] | None:
        """物资箱系统：根据配置概率和当前楼层生成物资箱。

        Args:
            player: 玩家状态（用于判断是否在 Level 0）。

        Returns:
            (箱型名称, 物品列表) 或 None（无物资箱）。
            箱型名称: "大型物资箱" / "中型物资箱" / "小型物资箱"
        """
        if player.current_level == 0:
            return None

        cfg = self.config.game

        # 确定箱型
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

        # 额外随机物品（使用权重系统）
        extra = self._random_item()
        items.append(dict(extra))

        return crate_size, items

    def _format_inventory(self, player: PlayerState) -> str:
        """格式化背包内容。"""
        if not player.inventory:
            return "背包是空的。"
        lines = []
        for idx, item in enumerate(player.inventory, 1):
            display = item.get("display_name", item["name"])
            lines.append(f"  [{idx}] {display} — {item['description']}")
        return "\n".join(lines)

    # ==================== 游戏命令处理方法 ====================

    async def _do_start(self, stream_id: str) -> None:
        """开始新游戏。"""
        user_id = str(stream_id)
        player = PlayerState(
            user_id=user_id,
            current_level=0,
            health=self.config.game.initial_health,
            sanity=self.config.game.initial_sanity,
            inventory=[],
        )
        player.fsm.apply(GameEvent.START)
        self._players[user_id] = player
        self._save_player(user_id)
        player.visited_levels.add(0)

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_start(ctx)
        await self._send_game_event(stream_id, event_text, player)

    async def _do_use_item(self, stream_id: str, item_index: int) -> None:
        """使用背包物品（按编号）。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if item_index < 1 or item_index > len(player.inventory):
            await self._send(
                stream_id,
                self._renderer.render_item_not_found(str(item_index)),
            )
            return

        # 按编号取出物品（1-based → 0-based）
        item = player.inventory.pop(item_index - 1)

        cfg = self.config.game
        effect = item.get("effect", "")
        value = item.get("value", 0)

        # 记录使用前数值，用于计算实际恢复量
        old_health = player.health
        old_sanity = player.sanity

        if effect == "health_restore":
            player.health = min(cfg.initial_health, player.health + value)
        elif effect == "sanity_restore":
            player.sanity = min(cfg.initial_sanity, player.sanity + value)

        ctx = self._make_ctx(player)
        remaining = [i.get("display_name", i["name"]) for i in player.inventory]

        event_text = self._renderer.render_use_item(item, ctx, remaining, old_health, old_sanity)
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    async def _do_explore(self, stream_id: str) -> None:
        """探索当前楼层。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if player.current_level == 399:
            await self._send(stream_id, self._renderer.render_already_at_399())
            return

        cfg = self.config.game
        player.sanity = max(0, player.sanity - cfg.explore_sanity_cost)

        level_info = self._get_level_info(player.current_level)

        # 随机事件
        event = random.choice(EXPLORE_EVENTS)
        event_text = event["text"]
        crate_result: tuple[str, list[dict]] | None = None
        health_cost: int | None = None
        note_found = False

        if event["type"] == "discovery":
            if event.get("give_item"):
                crate_result = self._roll_crate(player)
                if crate_result:
                    _, crate_items = crate_result
                    for it in crate_items:
                        player.inventory.append(it)
                else:
                    event_text += "……但里面已经空了。"
        elif event["type"] == "danger":
            if "health_cost" in event:
                health_cost = event["health_cost"]
                if self._has_item(player, "o2"):
                    health_cost = max(0, health_cost - 5)
                    self._use_item(player, "o2")
                player.health = max(0, player.health - health_cost)
        elif event["type"] == "found_note":
            note_text = self._story_manager.get_random_story()
            if note_text:
                player.pending_note = note_text
                note_found = True

        # 随机遭遇实体
        danger_modifier = {"低": 0.5, "中": 1.0, "高": 1.5, "极高": 2.0}
        encounter_chance = cfg.entity_encounter_chance * danger_modifier.get(level_info["danger"], 1.0)
        entity_encounter: tuple | None = None

        if random.random() < encounter_chance and level_info.get("entities"):
            entity_name = random.choice(level_info["entities"])
            entity_data = ENTITIES.get(entity_name)
            if entity_data:
                edamage = entity_data["damage"]
                if self._has_item(player, "o3"):
                    if entity_name in ("笑魇", "猎犬"):
                        edamage = 0
                    else:
                        edamage = max(0, edamage - 10)
                if edamage > 0:
                    if self._has_item(player, "o2"):
                        edamage = max(0, edamage - 5)
                        self._use_item(player, "o2")
                    player.health = max(0, player.health - edamage)
                entity_encounter = (entity_name, entity_data, edamage)

        # Level 1 特殊：在 M.E.G.CN Alpha 基地遇到角色
        # 由 CharacterEncounterService 统一处理角色选择、初见/常规判断、
        # 礼品发放和任务发放。新增角色只需在 CHARACTERS 注册表中添加。
        char_encounter: tuple[str, str, str | None, str | None, int, int] | None = None
        result = self._char_encounter_service.roll_encounter(
            level=player.current_level,
            unlocked_chars=player.unlocked_chars,
            player_state=player,
            people_story_manager=self._people_manager,
            quest_manager=self._quest_manager,
            ankexin_task_chance=cfg.ankexin_task_chance,
            favorability_per_encounter=cfg.favorability_per_encounter,
            consecutive_misses=player.consecutive_misses,
        )
        if result is not None:
            char_encounter = (
                result.char_id, result.story_text,
                result.gift_text, result.quest_offer,
                result.favorability_increase, result.current_favorability,
            )
            player.consecutive_misses = 0  # 触发后重置保底计数
        else:
            player.consecutive_misses += 1  # 未触发则累计

        # 理智值过低效果
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        # Level 1 基地工作：每探索 work_trigger_interval 次触发安可欣日常任务
        work_triggered = False
        work_assigned: tuple[str, str] | None = None
        if player.current_level == 1:
            player.l1_explore_count += 1
            interval = cfg.work_trigger_interval
            if player.l1_explore_count >= interval:
                player.l1_explore_count = 0
                work_triggered = True
                # 找一个未完成的工作派发给玩家
                available = self._work_manager.get_available_works(player.completed_works)
                if available:
                    wid = random.choice(available)
                    w = self._work_manager.get_work(wid)
                    if w:
                        player.available_works.add(wid)
                        work_assigned = (wid, w.get("title", wid))

        # 死亡处理
        if player.health <= 0:
            player.fsm.apply(GameEvent.DIE)
            del self._players[user_id]
            self._delete_player_save(user_id)
            ctx = self._make_ctx(player)
            event_text = self._renderer.render_explore(
                ctx, event_text, crate_result, health_cost,
                note_found, entity_encounter, char_encounter,
                work_triggered, work_assigned, companions=player.companions,
            )
            await self._send_game_event(stream_id, event_text, player)
            return

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_explore(
            ctx, event_text, crate_result, health_cost,
            note_found, entity_encounter, char_encounter,
            work_triggered, work_assigned, companions=player.companions,
        )
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    async def _do_explore_base(self, stream_id: str) -> None:
        """在 Alpha 基地内探索，遇见不同人物与场景。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return

        if not player.unlocked_chars:
            await self._send(stream_id, "⚠️ 你还不认识基地里的人，先使用 /br explore 探索楼层认识角色吧。")
            return

        await self._auto_end_dialog(stream_id, player)

        if player.current_level != 1:
            await self._send(stream_id, "⚠️ 你不在 Alpha 基地，无法使用基地探索命令。")
            return

        # 注：此处不需要检查 current_level == 399，因为 399 ≠ 1，前面的守卫已经拦截了所有非 Level 1 的情况
        cfg = self.config.game
        # 基地探索只消耗 1 点理智（比常规探索安全）
        player.sanity = max(0, player.sanity - 1)

        # 随机基地事件
        event = random.choice(BASE_EXPLORE_EVENTS)
        event_area = event["area"]
        event_text = event["text"]
        item_gained: dict | None = None

        if event.get("give_item"):
            # 给予随机物品
            item = self._random_item()
            player.inventory.append(dict(item))
            item_gained = item

        # 角色遭遇（使用现有系统）
        char_encounter: tuple[str, str, str | None, str | None, int, int] | None = None
        result = self._char_encounter_service.roll_encounter(
            level=player.current_level,
            unlocked_chars=player.unlocked_chars,
            player_state=player,
            people_story_manager=self._people_manager,
            quest_manager=self._quest_manager,
            ankexin_task_chance=cfg.ankexin_task_chance,
            favorability_per_encounter=cfg.favorability_per_encounter,
            consecutive_misses=player.consecutive_misses,
        )
        if result is not None:
            char_encounter = (
                result.char_id, result.story_text,
                result.gift_text, result.quest_offer,
                result.favorability_increase, result.current_favorability,
            )
            player.consecutive_misses = 0
        else:
            player.consecutive_misses += 1

        # 理智值过低效果
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        ctx = self._make_ctx(player)
        event_text = self._renderer.render_explore_base(
            ctx, event_area, event_text, item_gained, char_encounter,
        )
        await self._send_game_event(stream_id, event_text, player)
        self._save_player(user_id)

    async def _do_exit(self, stream_id: str) -> None:
        """尝试寻找出口。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        cfg = self.config.game

        # Level 399 特殊处理
        if player.current_level == 399:
            await self._send(
                stream_id,
                self._renderer.render_level399_escape(player.current_level, player.companions),
            )
            del self._players[user_id]
            self._delete_player_save(user_id)
            return

        player.sanity = max(0, player.sanity - cfg.exit_search_sanity_cost)

        # 计算出口概率
        exit_chance = cfg.base_exit_chance + player.exit_attempts * cfg.exit_chance_increment
        if self._has_item(player, "o4"):
            exit_chance = 1.0
            self._use_item(player, "o4")
        if self._has_item(player, "o3"):
            exit_chance += 0.05
        if self._has_item(player, "o5"):
            exit_chance += 0.05
        if player.companions:
            exit_chance += 0.05  # 同伴帮助搜索，+5% 出口率
        exit_chance = min(exit_chance, 1.0)

        if random.random() < exit_chance:
            # 找到出口
            player.exit_attempts = 0
            from_level = player.current_level

            # Level 11 特殊：找到出口直接前往 Level 399
            if from_level == 11:
                player.current_level = 399
                ctx = self._make_ctx(player)
                await self._send(
                    stream_id,
                    self._renderer.render_level399_escape(399, player.companions),
                )
                del self._players[user_id]
                self._delete_player_save(user_id)
                return

            shortcut_desc: str | None = None

            # 保存旧楼层信息（用于渲染出口搜索消息）
            old_level_info = self._get_level_info(from_level)

            level_info = self._get_level_info(player.current_level)
            shortcut = level_info.get("shortcut_to")
            if not shortcut and random.random() < 0.12 and player.current_level < 380:
                sd = random.choice(SHORTCUT_POOL)
                skip = random.randint(*sd["levels_skip"])
                shortcut = min(player.current_level + skip, 398)
                shortcut_desc = sd["description"]
            elif shortcut:
                shortcut_desc = random.choice(SHORTCUT_POOL)["description"]

            if shortcut:
                player.current_level = shortcut
                if not shortcut_desc:
                    shortcut_desc = f"你从 Level {from_level} 直接跳到了 Level {shortcut}！"
                else:
                    shortcut_desc += f"\n你从 Level {from_level} 直接跳到了 Level {shortcut}！"
            else:
                player.current_level += 1

            player.visited_levels.add(player.current_level)
            new_level_info = self._get_level_info(player.current_level)
            ctx = self._make_ctx(player)
            event_text = self._renderer.render_exit_found(
                old_level_info, ctx, new_level_info, shortcut_desc, from_level, player.companions,
            )
            await self._send_game_event(stream_id, event_text, player)

            # 检测任务进度：到达目标楼层
            for qid in list(player.active_quests):
                q = self._quest_manager.get_quest(qid)
                if q and q.get("objective_type") == "reach_level" and q.get("objective_target", 999) <= player.current_level:
                    await self._send(
                        stream_id,
                        f"📋 任务「{q['title']}」目标已达成！使用 /br quest submit {qid} 提交任务领取奖励。",
                    )
        else:
            # 没找到出口
            player.exit_attempts += 1

            event = random.choice(EXPLORE_EVENTS)
            event_text = event["text"]
            ex_crate_result: tuple[str, list[dict]] | None = None
            ex_health_cost: int | None = None
            ex_note_found = False

            if event.get("give_item"):
                ex_crate_result = self._roll_crate(player)
                if ex_crate_result:
                    _, ex_crate_items = ex_crate_result
                    for it in ex_crate_items:
                        player.inventory.append(it)
                else:
                    event_text += "……但里面已经空了。"
            if "health_cost" in event:
                ex_health_cost = event["health_cost"]
                if self._has_item(player, "o2"):
                    ex_health_cost = max(0, ex_health_cost - 5)
                    self._use_item(player, "o2")
                player.health = max(0, player.health - ex_health_cost)
            if event["type"] == "found_note":
                note_text = self._story_manager.get_random_story()
                if note_text:
                    player.pending_note = note_text
                    ex_note_found = True

            # 死亡处理
            if player.health <= 0:
                player.fsm.apply(GameEvent.DIE)
                del self._players[user_id]
                self._delete_player_save(user_id)
                ctx = self._make_ctx(player)
                event_text = self._renderer.render_exit_not_found(
                    ctx, player.exit_attempts, event_text,
                    ex_crate_result, ex_health_cost, ex_note_found,
                )
                await self._send_game_event(stream_id, event_text, player)
                return

            ctx = self._make_ctx(player)
            event_text = self._renderer.render_exit_not_found(
                ctx, player.exit_attempts, event_text,
                ex_crate_result, ex_health_cost, ex_note_found,
            )
            await self._send_game_event(stream_id, event_text, player)

        self._save_player(user_id)

    async def _do_exit_to_level(self, stream_id: str, target_level: int) -> None:
        """尝试回溯到已访问过的指定楼层。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        if target_level == player.current_level:
            await self._send(stream_id, "❌ 你现在就在这个楼层，不需要回溯。")
            return

        if target_level not in player.visited_levels:
            await self._send(stream_id, f"❌ 你还没有访问过 Level {target_level}，无法回溯到那里。")
            return

        if target_level == 399:
            await self._send(stream_id, "❌ 不能直接回溯到最终出口 Level 399。")
            return

        cfg = self.config.game
        player.sanity = max(0, player.sanity - 10)

        from_level = player.current_level
        # 回溯成功率：基础 50%，目地楼层越低越熟悉（+5%），累计偏移+10%
        distance = abs(target_level - from_level)
        base_chance = 0.50
        familiarity_bonus = max(0, (10 - target_level) * 0.02)  # 低楼层更熟悉
        attempt_bonus = player.exit_attempts * 0.10
        total_chance = min(0.95, base_chance + familiarity_bonus + attempt_bonus)

        if random.random() < total_chance:
            # 成功
            old_level_info = self._get_level_info(from_level)
            player.current_level = target_level
            player.exit_attempts = 0
            player.visited_levels.add(target_level)
            new_level_info = self._get_level_info(target_level)
            ctx = self._make_ctx(player)
            event_text = (
                f"🔙 你努力回忆着来时的路，在错综复杂的后室走廊中摸索前行……\n\n"
                f"✨ 你成功了！你找到了回到 {new_level_info['title']} 的道路。\n\n"
                f"{new_level_info['description']}"
            )
            await self._send_game_event(stream_id, event_text, player)
        else:
            # 失败
            player.exit_attempts += 1
            if player.sanity <= 0:
                player.health = max(0, player.health - 10)
            ctx = self._make_ctx(player)
            event_text = (
                f"🔙 你努力寻找着回到 Level {target_level} 的道路……\n\n"
                f"❌ 但后室的空间太过混乱，你迷失了方向。理智值 -10\n"
                f"当前楼层：{ctx.level_info['title']}"
            )
            if player.health <= 0:
                player.fsm.apply(GameEvent.DIE)
                del self._players[user_id]
                self._delete_player_save(user_id)
                await self._send_game_event(stream_id, event_text, player)
                return
            await self._send_game_event(stream_id, event_text, player)

        self._save_player(user_id)

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

    # ==================== 任务系统 ====================

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

            # 先验证数量足够再扣减，避免部分消耗导致物品丢失
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

    # ==================== 工作故事面板 ====================

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

    # ==================== 基地工作系统 ====================

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

    # ==================== 好感度 & 同伴系统 ====================

    async def _do_invite(self, stream_id: str, char_name: str) -> None:
        """邀请角色一起探索后室。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        # 将中文名映射为角色 ID
        name_to_id = {
            meta["name"]: cid
            for cid, meta in CHARACTERS.items()
        }
        # 也支持直接输入角色 ID
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
            # 已有同行者：普通角色禁止重复邀请，夏终可依赖洛疏律加入
            if char_id == "xiazhong":
                if "luo_shulv" not in player.companions:
                    await self._send(
                        stream_id,
                        f"❌ 夏终不太信任陌生人，只有在 {CHARACTERS['luo_shulv']['name']} 同行时，她才愿意一起出发。",
                    )
                    return
                # 夏终已在同行中则跳过
                if "xiazhong" in player.companions:
                    await self._send(stream_id, f"ℹ️ 夏终已经在队伍中了。")
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
            # 解散洛疏律时，夏终也一并离开
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

        # 构建 system prompt 并调用 LLM 生成开场白
        system_prompt = build_system_prompt(char_id, self._people_relationship_data)
        messages = build_message_list(system_prompt, [], f"{char_name}遇到了玩家，打一声招呼开始对话吧。")

        try:
            result = await self.ctx.llm.generate(prompt=messages, model=self.config.game.dialog_model or "replyer")
            if result.get("success"):
                reply = strip_cot(result.get("response", ""))
                if reply:
                    # 保存到对话历史
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

        # 尝试用 LLM 生成告别语
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

        # 状态转移
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
            # 用 LLM 生成告别语
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

        # 先保存用户消息到历史
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

        # LLM 调用失败的 fallback
        await self._send(stream_id, f"—— {char_name} ——\n\n（{char_name}似乎走神了，没有听清你在说什么。）")

    async def _do_gift(self, stream_id: str, char_name: str, item_index: int) -> None:
        """赠送背包物品给角色以提升好感度。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.fsm.is_playable():
            await self._send(stream_id, self._renderer.render_not_started())
            return
        await self._auto_end_dialog(stream_id, player)

        # 将中文名映射为角色 ID
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

        # 验证物品编号（1-based）
        if item_index < 1 or item_index > len(player.inventory):
            await self._send(stream_id, self._renderer.render_item_not_found(str(item_index)))
            return

        # 取出物品
        item = player.inventory.pop(item_index - 1)
        item_name = item.get("name", "")
        item_display = item.get("display_name", item_name)

        # 计算好感度增加值
        gift_values = self.config.game.gift_favorability_values
        fav_increase = gift_values.get(item_name, 1)  # 未配置的物品默认 +1
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

    async def _do_off(self, stream_id: str, message: dict) -> None:
        """关闭插件：仅管理员可用，禁用后仅管理员可继续使用。

        管理员只能通过修改配置文件来增减，无法通过命令自任命。
        """
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权关闭插件。")
            return

        self._plugin_disabled = True
        self.ctx.logger.info("插件已由管理员关闭 user_id=%s", user_id)
        await self._send(stream_id, "🔒 插件已关闭。")

    async def _do_on(self, stream_id: str, message: dict) -> None:
        """重新启用插件：仅管理员可用。"""
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权启用插件。")
            return

        self._plugin_disabled = False
        self.ctx.logger.info("插件已由管理员重新启用 user_id=%s", user_id)
        await self._send(stream_id, "🔓 插件已重新启用，所有用户均可使用。")

    async def _do_shut(self, stream_id: str, message: dict) -> None:
        """管理员切换当前群聊的静默状态。

        静默后，群内非 /br 消息不会触发 Planner/LLM 处理。
        """
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id not in self._admin_ids:
            await self._send(stream_id, "❌ 你不是管理员，无权执行此操作。")
            return

        # 解析当前群组 ID
        resolved = self._resolve_access_id(message, stream_id)
        if resolved is None:
            await self._send(stream_id, "❌ 无法识别当前会话，请确认在群聊中使用此命令。")
            return
        chat_type, chat_id = resolved
        if chat_type != "group":
            await self._send(stream_id, "❌ /br shut 仅限群聊使用。")
            return

        # 切换静默状态
        if self._shut_manager.is_shut(chat_id):
            self._shut_manager.remove_shut(chat_id)
            await self._send(stream_id, f"🔊 群 {chat_id} 已取消静默。所有消息恢复正常处理。")
            self.ctx.logger.info("shut: 管理员 %s 已取消群 %s 静默", user_id, chat_id)
        else:
            self._shut_manager.add_shut(chat_id)
            await self._send(stream_id, f"🔇 群 {chat_id} 已开启静默。非 /br 消息将不再触发 Planner。")
            self.ctx.logger.info("shut: 管理员 %s 已静默群 %s", user_id, chat_id)


def create_plugin() -> BackroomsGamePlugin:
    """创建后室:逃出生天游戏插件实例。"""
    return BackroomsGamePlugin()
