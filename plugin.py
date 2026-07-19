"""后室:逃出生天 — 游戏插件

扮演 M.E.G.CN 工作人员，从 Level 0 出发，在后室中寻找出口不断切入下一个楼层，
直至找到最终出口 Level 399。

本文件作为插件入口，负责：
- 定义版本常量
- 注册 ``@Command`` 和 ``@HookHandler`` 到 MaiBot SDK
- 管理插件生命周期（on_load / on_unload / on_config_update）
- 组合 ``handlers/`` 和 ``hooks/`` 中的混入类与处理函数

命令实现逻辑已拆分至以下包：
- ``handlers/``   — 游戏命令的 _do_* 方法（按功能领域拆分为多个混入类）
- ``hooks/``      — Hook 处理逻辑（访问控制、消息拦截、Planner 跳过）
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
)

# ── 渲染层 ──
from .rendering import BackroomsRenderer, RenderContext
from .rendering import (  # story_load re-exports
    CHARACTERS,
    CharacterEncounterService,
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
    ShutManager,
)

# ── 持久化层 ──
from .persistence import SaveManager

# ── 命令处理器混入 ──
from .handlers import (
    GameCommandMixin,
    ExitCommandMixin,
    PlayerCommandMixin,
    StoryCommandMixin,
    QuestCommandMixin,
    WorkCommandMixin,
    CharacterCommandMixin,
    CompanionCommandMixin,
    AdminCommandMixin,
)

# ── Hook 处理函数 ──
from .hooks import (
    check_access_before_command as _check_access_hook,
    skip_planner_after_command as _skip_planner_hook,
    handle_dialog_message as _handle_dialog_hook,
    check_shut_before_process as _check_shut_hook,
)

# 模块导入时加载物品/实体数据
load_items_pool()


# ==================== 版本常量 ====================

PLUGIN_VERSION = "1.2.1"
"""插件版本号（与 _manifest.json 同步）。"""

SAVE_VERSION = "1.2.1"
"""存档数据格式版本号，用于存档迁移兼容。"""


# ==================== 插件主体 ====================

class BackroomsGamePlugin(
    GameCommandMixin,
    ExitCommandMixin,
    PlayerCommandMixin,
    StoryCommandMixin,
    QuestCommandMixin,
    WorkCommandMixin,
    CharacterCommandMixin,
    CompanionCommandMixin,
    AdminCommandMixin,
    MaiBotPlugin,
):
    """后室:逃出生天游戏插件

    通过多重继承组合所有命令处理器混入类，
    每个混入类专注于一类游戏功能的 ``_do_*`` 实现。
    """

    config_model = BackroomsGameConfig

    # ==================== 生命周期 ====================

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
        self._people_net_text = self._people_relationship_data
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

        # ── 版本迁移检查 ──
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

        self._admin_ids = set(
            uid.strip() for uid in self.config.plugin.admin_ids if uid.strip()
        )
        self.ctx.logger.info("管理员列表已刷新: %s", sorted(self._admin_ids) if self._admin_ids else "空")

        current_ver = self.config.plugin.config_version
        if current_ver != PLUGIN_VERSION:
            self.ctx.logger.info(
                "配置热重载检测到旧版配置 (config_version=%s)，正在迁移至 %s……",
                current_ver, PLUGIN_VERSION,
            )
            self.config.plugin.config_version = PLUGIN_VERSION
            self.ctx.logger.info("配置已迁移至 %s", PLUGIN_VERSION)

    # ==================== 存档操作 ====================

    def _save_all_players(self) -> None:
        """批量保存所有玩家状态。"""
        for player in self._players.values():
            self._save_manager.save(player)

    def _load_all_players(self) -> None:
        """批量加载所有玩家存档恢复至内存。"""
        self._save_manager.load_all(self._players)

    # ==================== 配置迁移 ====================

    @staticmethod
    def _migrate_save_data(data: dict) -> dict:
        """将旧版存档数据迁移至当前存档格式。

        旧版存档（v1.0.1 / v1.0.2）没有 ``save_version`` 字段。
        该方法作为扩展点，后续版本如有存档格式变更，
        在此处添加对应版本的分支迁移逻辑即可。
        """
        from .persistence.save_manager import SaveManager as _SM
        data = _SM._migrate(data)
        data["save_version"] = SAVE_VERSION
        return data

    async def _migrate_config_if_needed(self) -> None:
        """检测配置文件版本，必要时执行配置迁移。"""
        current_ver = self.config.plugin.config_version
        if current_ver != PLUGIN_VERSION:
            self.ctx.logger.info(
                "检测到旧版配置文件 (config_version=%s)，正在迁移至 %s……",
                current_ver, PLUGIN_VERSION,
            )
            self.config.plugin.config_version = PLUGIN_VERSION
            self.ctx.logger.info("配置文件已迁移至 %s", PLUGIN_VERSION)
        else:
            self.ctx.logger.info("配置文件版本为最新 (%s)", PLUGIN_VERSION)

    # ==================== 游戏命令（@Command 组件） ====================
    # 每个命令方法为薄封装层，实际逻辑委托给 handlers/ 包中的混入方法。

    @Command(
        "br_test",
        description="测试插件连通性 — 验证插件是否能正常接收和处理消息",
        pattern=r"^/br\s+test$",
    )
    async def handle_test(self, **kwargs: Any):
        """测试命令：回显确认插件正常接收消息。"""
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
        success = await self._send(stream_id, self._renderer.render_test())
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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
        )
        m = re.search(r"/br\s+story\s+(\w+)", raw_text)
        if m:
            await self._do_story_view(stream_id, m.group(1))
        else:
            await self._do_story_list(stream_id)
        return True, "故事面板处理完成", 1

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
        await self._do_read(stream_id)
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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
        )
        m = re.search(r"/br\s+exit\s+l(\d+)", raw_text)
        if m:
            await self._do_exit_to_level(stream_id, int(m.group(1)))
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

        await self._do_use_item(stream_id, int(index_str))
        return True, f"物品 {index_str} 已使用", 1

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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
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
        "br_said",
        description="对话 — 与指定角色进入对话模式",
        pattern=r"^/br\s+said\s+([\u4e00-\u9fffA-Za-z]+)",
    )
    async def handle_said(self, **kwargs: Any):
        """与指定角色进入对话模式。"""
        stream_id = kwargs.get("stream_id", "")
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message") or message.get("text") or message.get("message") or ""
        )
        m = re.search(r"/br\s+said\s+([\u4e00-\u9fffA-Za-z]+)", raw_text)
        if m:
            await self._do_said(stream_id, m.group(1))
        return True, "对话模式处理完成", 1

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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
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
            message.get("raw_message") or message.get("text") or message.get("message") or ""
        )
        m = re.search(r"/br\s+gift\s+([\u4e00-\u9fffA-Za-z]+)\s+(\d+)", raw_text)
        if m:
            char_name = m.group(1).lower()
            item_index = int(m.group(2))
            await self._do_gift(stream_id, char_name, item_index)
        return True, "赠礼处理完成", 1

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

    # ==================== Hook 处理器 ====================
    # 每个 Hook 方法为薄封装层，实际逻辑委托给 hooks/ 包中的独立函数。

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
        return await _check_access_hook(self, **kwargs)

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
        return await _skip_planner_hook(self, **kwargs)

    @HookHandler(
        "chat.receive.before_process",
        name="br_dialog_handler",
        description="拦截对话模式下玩家的非命令消息，路由至 LLM 对话处理器",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def handle_dialog_message(self, **kwargs: Any):
        """在消息处理前检查用户是否处于对话模式。"""
        return await _handle_dialog_hook(self, **kwargs)

    @HookHandler(
        "chat.receive.before_process",
        name="br_shut_check",
        description="检查消息所在群组是否被 shut，阻止非 /br 消息进入 Planner",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.LOG,
    )
    async def check_shut_before_process(self, **kwargs: Any):
        """在消息处理前检查群组是否被静默。"""
        return await _check_shut_hook(self, **kwargs)


def create_plugin() -> BackroomsGamePlugin:
    """创建后室:逃出生天游戏插件实例。"""
    return BackroomsGamePlugin()
