"""后室:逃出生天 — 消息回复渲染器

将所有消息文本的格式化逻辑从 plugin.py 中抽离，保持游戏逻辑与呈现分离。
同时作为拓展功能模块的加载入口 —— 所有 ``renderer_load/`` 下的模块
均由本模块导入并显式透出，上层 (plugin.py) 只需 import 本模块即可。
"""

from __future__ import annotations

from typing import Any

from .config import GameConfig

# ── 透出 renderer_load 中的拓展功能模块 ──
# 所有 renderer_load/*.py 中的公开类均在此处导入并重新导出，
# 上层（plugin.py）通过 from .renderer import ... 即可获得全部能力。
from .renderer_load import (
    ShutManager,
    GameState,
    GameEvent,
    GameStateMachine,
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
)

__all__ = [
    "RenderContext",
    "BackroomsRenderer",
    "ShutManager",
    "GameState",
    "GameEvent",
    "GameStateMachine",
    "StoryManager",
    "PeopleStoryManager",
    "QuestManager",
    "WorkManager",
    "BaseWorkStoryManager",
]


# ==================== 渲染上下文 ====================

class RenderContext:
    """封装渲染所需的全部状态快照。"""

    def __init__(
        self,
        health: int,
        sanity: int,
        current_level: int,
        initial_health: int,
        initial_sanity: int,
        inventory_count: int,
        game_config: GameConfig,
        level_info: dict[str, Any],
        exit_attempts: int = 0,
    ) -> None:
        self.health = health
        self.sanity = sanity
        self.current_level = current_level
        self.initial_health = initial_health
        self.initial_sanity = initial_sanity
        self.inventory_count = inventory_count
        self.cfg = game_config
        self.level_info = level_info
        self.exit_attempts = exit_attempts


# ==================== 渲染器 ====================

class BackroomsRenderer:
    """后室:逃出生天消息渲染器。

    所有方法均为纯函数：接收数据，返回格式化字符串。
    不依赖 SDK、不产生副作用、不访问网络。
    """

    # ---------- 状态标签 ----------

    @staticmethod
    def health_label(health: int, initial_health: int) -> str:
        ratio = health / initial_health
        if ratio > 0.7:
            return "良好 ✅"
        if ratio > 0.3:
            return "中等 ⚠️"
        return "危险 🔴"

    @staticmethod
    def sanity_label(sanity: int, initial_sanity: int) -> str:
        ratio = sanity / initial_sanity
        if ratio > 0.7:
            return "清醒 ✅"
        if ratio > 0.3:
            return "焦虑 ⚠️"
        return "崩溃边缘 🔴"

    # ---------- 复用片段 ----------

    @staticmethod
    def status_bar(ctx: RenderContext) -> str:
        """生命/理智/物品 状态条。"""
        return (
            f"❤️ 生命：{ctx.health}/{ctx.initial_health}  |  "
            f"🧠 理智：{ctx.sanity}/{ctx.initial_sanity}  |  "
            f"📦 物品：{ctx.inventory_count}件"
        )

    @staticmethod
    def low_sanity_warning(sanity: int) -> str | None:
        if sanity <= 20:
            return "😰 你的理智值很低了！使用 /br use <编号> 使用背包中的恢复物品。"
        return None

    @staticmethod
    def low_health_warning(health: int, initial_health: int) -> str | None:
        if health <= 30:
            return "   提示：生命值危险，可使用 /br use <编号> 使用背包中的恢复物品。"
        return None

    @staticmethod
    def next_step_hint(level: int, sanity: int, health: int, initial_health: int) -> list[str]:
        """生成下一步操作引导。"""
        hints: list[str] = []
        if level < 399:
            hints.append("💡 下一步：使用 /br exit 寻找出口，或继续 /br explore 探索搜集物品。")
        warn = BackroomsRenderer.low_sanity_warning(sanity)
        if warn:
            hints.append(warn)
        warn = BackroomsRenderer.low_health_warning(health, initial_health)
        if warn:
            hints.append(warn)
        return hints

    @staticmethod
    def exit_search_hint(exit_attempts: int) -> str:
        """根据出口搜索次数生成引导。"""
        if exit_attempts >= 2:
            return "\n💡 找了多次都没找到出口？试试 /br explore 探索一下，也许能找到层级钥匙或其他帮助。"
        return "\n💡 继续 /br exit 再试试，每次失败都会提高后面的成功率！"

    # ---------- 完整消息 ----------

    def render_start(self, ctx: RenderContext) -> str:
        """游戏开始消息。"""
        info = ctx.level_info
        return (
            "══════════════════════════\n"
            "  🏢 后 室 逃 生 🏃\n"
            "══════════════════════════\n\n"
            f"{info['title']}\n"
            f"危险等级：{info['danger']}\n\n"
            f"{info['description']}\n\n"
            "你是 M.E.G.CN（探险者总署中文分部）的一名工作人员。\n"
            "你被困在了后室之中，必须找到通往 Level 399 的最终出口才能回到现实世界。\n\n"
            "📋 可用命令：\n"
            "  /br story     — 故事档案（查看已解锁的工作故事）\n"
            "  /br test      — 插件连通性测试\n"
            "  /br explore    — 探索当前楼层\n"
            "  /br exit     — 尝试寻找出口\n"
            "  /br read     — 阅读纸条\n"
            "  /br use <编号> — 使用背包中对应编号的物品\n"
            "  /br status   — 查看当前状态\n"
            "  /br inventory — 查看背包\n"
            "  /br quest    — 查看任务面板\n"
            "  /br work     — Alpha 基地工作（解谜）\n"
            "  /br help     — 游戏帮助\n\n"
            "祝你好运，探员。"
        )

    def render_start_nodes(self, ctx: RenderContext) -> list[str]:
        """游戏开始消息，拆分为多个转发节点。"""
        info = ctx.level_info
        return [
            # 节点 1：标题 + 楼层信息
            (
                "══════════════════════════\n"
                "  🏢 后 室 逃 生 🏃\n"
                "══════════════════════════\n\n"
                f"{info['title']}\n"
                f"危险等级：{info['danger']}\n\n"
                f"{info['description']}"
            ),
            # 节点 2：角色背景
            (
                "你是 M.E.G.CN（探险者总署中文分部）的探员。\n"
                "你被困在了一个叫做「后室」的异次元空间之中。\n"
                "这里没有日夜，没有出口的尽头。\n"
                "但你有经验、有装备、有信念。\n\n"
                "你的任务只有一个——\n"
                "找到通往 Level 399 的最终出口，回到现实世界。"
            ),
            # 节点 3：命令列表
            (
                "📋 可用命令：\n\n"
                "  /br story     — 故事档案（查看已解锁的工作故事）\n"
                "  /br test      — 插件连通性测试\n"
                "  /br explore   — 探索当前楼层\n"
                "  /br exit      — 尝试寻找出口\n"
                "  /br read      — 阅读纸条\n"
                "  /br use <编号> — 使用背包中对应编号的物品\n"
                "  /br status    — 查看当前状态\n"
                "  /br inventory — 查看背包\n"
                "  /br quest     — 查看任务面板\n"
                "  /br work      — Alpha 基地工作（解谜）\n"
                "  /br help      — 游戏帮助\n\n"
                "祝你好运，探员。"
            ),
        ]

    def render_use_item(
        self, item: dict, ctx: RenderContext, remaining_items: list[str],
        old_health: int = 0, old_sanity: int = 0,
    ) -> str:
        """物品使用结果。"""
        display = item.get("display_name", item["name"])
        effect = item.get("effect", "")
        lines = [f"你使用了【{display}】。"]

        if effect == "health_restore":
            restored = ctx.health - old_health
            lines.append(
                f"❤️ 生命值恢复了 {restored} 点（当前：{ctx.health}/{ctx.initial_health}）。"
            )
        elif effect == "sanity_restore":
            restored = ctx.sanity - old_sanity
            lines.append(
                f"🧠 理智值恢复了 {restored} 点（当前：{ctx.sanity}/{ctx.initial_sanity}）。"
            )
        elif effect == "light":
            lines.append("🔦 手电筒已装备，将在探索中自动生效（驱散笑魇、+5% 出口发现率）。")
        elif effect == "hint":
            lines.append("📻 M.E.G. 无线电已启用，将帮助你在楼层中导航（+5% 出口发现率）。")
        elif effect == "exit_guarantee":
            lines.append("🔑 层级钥匙已使用！下次 /br exit 必能找到出口。")
        else:
            lines.append("这个物品似乎没有明显的效果……但也许在关键时刻会派上用场。")

        if remaining_items:
            lines.append(f"\n📦 剩余物品：{', '.join(remaining_items)}")

        return "\n".join(lines)

    def render_explore(
        self,
        ctx: RenderContext,
        event_text: str,
        crate_result: tuple[str, list[dict]] | None,
        health_cost: int | None,
        note_found: bool,
        entity_encounter: tuple[str, dict, int] | None,
        char_encounter: tuple[str, str, str | None, str | None] | None = None,
        work_triggered: bool = False,
        work_assigned: tuple[str, str] | None = None,
    ) -> str:
        """探索结果消息。

        Args:
            ctx: 渲染上下文。
            event_text: 探索事件文本。
            crate_result: (箱型名称, 物品列表) 或 None。
            health_cost: 事件造成的生命值伤害（None 表示无伤害）。
            note_found: 是否发现了纸条。
            entity_encounter: (实体名, 实体数据, 实际伤害) 或 None。
            char_encounter: (角色ID, 剧情文本, 赠送文本, 任务ID) 或 None。
            work_triggered: 是否有新的基地工作可用。
            work_assigned: (工作ID, 工作标题) — 安可欣主动派发的日常工作任务。
        """
        lines = [f"🔍 你在 {ctx.level_info['title']} 中探索……"]

        if note_found:
            lines.append(event_text + " 使用 /br read 来阅读纸条。")
        else:
            lines.append(event_text)

        if crate_result:
            crate_size, crate_items = crate_result
            lines.append(f"📦 你发现了一个【{crate_size}】！")
            for it in crate_items:
                lines.append(
                    f"🎒 获得：【{it['display_name']}】— {it['description']}"
                )

        if health_cost is not None and health_cost > 0:
            lines.append(
                f"💔 生命值 -{health_cost}（当前：{ctx.health}/{ctx.initial_health}）"
            )

        # 实体遭遇
        if entity_encounter:
            ename, edata, edamage = entity_encounter
            msg = f"\n⚠️ 危险！你遭遇了【{ename}】——{edata['description']}"
            if edamage == 0:
                if ename == "笑魇":
                    msg += "\n你的手电筒驱散了笑魇！它消失在黑暗中。"
                elif ename == "猎犬":
                    msg += "\n手电筒的强光让猎犬退缩了，它夹着尾巴逃走了。"
                else:
                    msg += "\n手电筒的亮光暂时让它犹豫了一下，为你争取了一些时间。"
            lines.append(msg)
            if edamage > 0:
                lines.append(
                    f"💔 生命值 -{edamage}（当前：{ctx.health}/{ctx.initial_health}）"
                )

        # 角色遭遇
        if char_encounter:
            char_id, story_text, char_gift, quest_offer = char_encounter
            if char_id == "ankexin":
                lines.append("\n═════ 你在 Alpha 基地遇到了安可欣 ═════")
                lines.append("")
                lines.append(story_text)
                lines.append("")
                lines.append("═══════════════════════════════════")
            elif char_id == "anjinian":
                lines.append("\n═════ 你在维修区遇到了安继年 ═════")
                lines.append("")
                lines.append(story_text)
                lines.append("")
                lines.append("═══════════════════════════════════")
            if char_gift:
                lines.append(char_gift)
            if quest_offer:
                lines.append(f"\n📋 安可欣给你布置了一个新任务！")
                lines.append(f"使用 /br quest accept {quest_offer} 接受任务，或 /br quest 查看详情。")

        # 理智值过低
        warn = self.low_sanity_warning(ctx.sanity)
        if warn:
            lines.append(warn)

        if ctx.sanity <= 0:
            lines.append("💀 理智值耗尽，你的精神崩溃了！生命值额外减少了 10 点。")

        # 死亡
        if ctx.health <= 0:
            lines.append(self._death_message())

        lines.append(f"\n{self.status_bar(ctx)}")

        # 基地工作提示
        if work_triggered:
            lines.append("🏢 Alpha 基地有新工作可接！使用 /br work 查看工作面板。")

        # 安可欣主动派发日常工作任务
        if work_assigned:
            wid, wtitle = work_assigned
            lines.append("")
            lines.append("═══════════════════════════════════")
            lines.append("📋 安可欣找到了你，给你布置了一份基地工作！")
            lines.append("")
            lines.append(f"📝 工作：「{wtitle}」")
            lines.append(f"→ 使用 /br work start {wid} 查看详情并开始工作")
            lines.append("═══════════════════════════════════")

        # 引导
        if ctx.health > 0 and ctx.current_level < 399:
            lines.extend(self.next_step_hint(
                ctx.current_level, ctx.sanity, ctx.health, ctx.initial_health,
            ))

        return "\n".join(lines)

    def render_exit_found(
        self,
        old_level_info: dict[str, Any],
        ctx: RenderContext,
        new_level_info: dict[str, Any],
        shortcut_desc: str | None,
        from_level: int,
    ) -> str:
        """找到出口时的消息。"""
        lines = [f"🚪 你仔细搜索着 {old_level_info['title']} 的每一个角落……"]

        if shortcut_desc:
            lines.append(f"✨ {shortcut_desc}")
        else:
            lines.append("你找到了出口！四周的景象开始扭曲模糊……")

        nli = new_level_info
        lines.append(f"\n📍 你切入了 {nli['title']}")
        lines.append(f"危险等级：{nli['danger']}")
        lines.append(f"\n{nli['description']}")

        warn = self.low_sanity_warning(ctx.sanity)
        if warn:
            lines.append(f"\n{warn}")

        if ctx.current_level < 399:
            lines.append(f"\n{self.status_bar(ctx)}")
            lines.append("\n💡 指引：先 /br explore 探索新楼层，再 /br exit 寻找下一个出口。")

        return "\n".join(lines)

    def render_exit_not_found(
        self,
        ctx: RenderContext,
        exit_attempts: int,
        event_text: str,
        crate_result: tuple[str, list[dict]] | None,
        health_cost: int | None,
        note_found: bool,
    ) -> str:
        """未找到出口时的消息。"""
        info = ctx.level_info
        lines = [f"🚪 你仔细搜索着 {info['title']} 的每一个角落……"]
        lines.append("……但你没能找到出口。")

        if exit_attempts >= 3:
            lines.append("你已经搜索了很久，也许下次运气会好些。")

        if note_found:
            lines.append(f"\n{event_text} 使用 /br read 来阅读纸条。")
        else:
            lines.append(f"\n{event_text}")

        if crate_result:
            crate_size, crate_items = crate_result
            lines.append(f"\n📦 你发现了一个【{crate_size}】！")
            for it in crate_items:
                lines.append(
                    f"🎒 获得：【{it['display_name']}】"
                )

        if health_cost is not None and health_cost > 0:
            lines.append(f"💔 生命值 -{health_cost}")

        if ctx.health <= 0:
            lines.append(self._death_message())

        lines.append(f"\n{self.status_bar(ctx)}")
        lines.append(self.exit_search_hint(exit_attempts))

        return "\n".join(lines)

    def render_status(self, ctx: RenderContext, inventory_text: str, currency: int = 0) -> str:
        """探员状态面板。"""
        h_label = self.health_label(ctx.health, ctx.initial_health)
        s_label = self.sanity_label(ctx.sanity, ctx.initial_sanity)
        progress = min(100, int(ctx.current_level / 399 * 100))
        bar = "█" * (progress // 5) + "░" * (20 - progress // 5)

        lines = [
            "══════════════════\n"
            "  📊 探 员 状 态\n"
            "══════════════════\n\n"
            f"📍 {ctx.level_info['title']}\n"
            f"   危险等级：{ctx.level_info['danger']}\n\n"
            f"❤️ 生命值：{ctx.health}/{ctx.initial_health}  [{h_label}]\n"
            f"🧠 理智值：{ctx.sanity}/{ctx.initial_sanity}  [{s_label}]\n",
        ]
        if currency > 0:
            lines.append(f"💰 贡献点：{currency}\n")
        lines += [
            f"\n📦 背包物品：\n{inventory_text}\n\n"
            f"🏁 通关进度：{progress}%  [{bar}]\n\n"
            f"🔢 出口尝试次数（本层）：{ctx.exit_attempts} 次\n"
            "══════════════════",
        ]
        return "".join(lines)

    def render_inventory(self, inventory_text: str, hints: list[str]) -> str:
        """背包面板。"""
        hint_text = "\n".join(hints) if hints else "使用 /br status 查看完整状态。"
        return (
            "══════════════════\n"
            "  🎒 背包物品\n"
            "══════════════════\n\n"
            f"{inventory_text}\n\n"
            f"{hint_text}"
        )

    def render_help(self) -> str:
        """游戏帮助。"""
        return (
            "══════════════════════\n"
            "  📖 后室:逃出生天 — 游戏帮助\n"
            "══════════════════════\n\n"
            "🎯 游戏目标：从 Level 0 出发，一路寻找出口，到达 Level 399 逃出后室。\n\n"
            "📋 命令列表：\n"
            "  /br story    — 故事档案（/br story 查看列表 / <ID> 查看详情）\n"
            "  /br test      — 测试插件连通性（验证插件是否正常）\n"
            "  /br start     — 开始新游戏\n"
            "  /br explore    — 探索当前楼层（消耗5理智，可能遇敌/发现物品/捡到纸条）\n"
            "  /br exit       — 尝试寻找出口（消耗10理智，每次失败增加成功概率）\n"
            "  /br read       — 阅读捡到的纸条（通过合并转发消息展示）\n"
            "  /br status     — 查看探员状态\n"
            "  /br inventory  — 查看背包\n"
            "  /br use <编号> — 使用背包中的物品（如 /br use 1）\n"
            "  /br quest — 查看任务面板 /br quest accept <ID> / <ID> submit\n"
            "  /br work — Alpha 基地工作（/br work start <ID> / answer <ID> <答案>）\n"
            "  /br help       — 显示此帮助\n"
            "  /br people_net — 已解锁人物关系图\n\n"
            "⚙️ 游戏机制：\n"
            "  ❤️ 生命值 — 归零则游戏结束\n"
            "  🧠 理智值 — 消耗在探索和找出口中，可使用杏仁水恢复\n"
            "  🎒 物品 — 探索中有概率获得，每种物品有不同效果\n\n"
            "🏆 特殊机制：\n"
            "  · 部分楼层有捷径，可以跳过多个楼层\n"
            "  · 知名楼层（Level 0-11 等）有独特描述和特殊实体\n"
            "  · 黑暗楼层中手电筒能驱散笑魇\n"
            "  · 层级钥匙能确保一定找到出口\n\n"
            "祝你好运，M.E.G.CN 探员！后室等着你去征服。"
        )

    def render_people_net(self, people_data: dict[str, dict], unlocked_chars: set[str]) -> str:
        """人物关系图。

        Args:
            people_data: br_story/people_story/people_relationship.json 解析后的数据。
            unlocked_chars: 玩家已解锁的角色 ID 集合。

        Returns:
            格式化后的人物关系文本。
        """
        lines = ["══════════════════════\n  🕸️ 人物关系图\n══════════════════════\n"]
        if not people_data:
            lines.append("暂无人物数据。")
            return "\n".join(lines)

        # 显示每个角色
        for cid, info in people_data.items():
            cname = info.get("name", cid)
            if cid in unlocked_chars:
                lines.append(f"✅ {cname} —— 已解锁")
            else:
                lines.append(f"❓ ??? —— 尚未遇到")

        lines.append("")
        lines.append("人物背景与关系：")

        # 只显示已解锁角色的详细信息
        for cid, info in people_data.items():
            if cid not in unlocked_chars:
                continue
            cname = info.get("name", cid)
            lines.append(f"━━━━━━━━━━━━━━━━━━━━")
            lines.append(f"{cname}（{cid}）")
            lines.append(f"身份：{info.get('identity', '未知')}")
            lines.append(f"年龄：{info.get('age', '未知')} 岁")
            lines.append(f"关系：{info.get('relationship', '未知')}")
            lines.append(f"状态：{info.get('status', '未知')}")
            lines.append(f"首次发现：{info.get('first_encounter', '未知')}")
            lines.append("")
            lines.append(info.get("description", ""))

        # 关系连线
        if unlocked_chars:
            lines.append("")
            lines.append("人物关系：")
            for cid, info in people_data.items():
                if cid in unlocked_chars and info.get("relationship"):
                    lines.append(f"  · {info['name']} 与 {info['relationship']}")

        return "\n".join(lines)

    def render_test(self) -> str:
        """连通性测试回显。"""
        return (
            "✅ 后室:逃出生天插件已正常接收消息！\n"
            "插件工作正常，你可以使用以下命令开始游戏：\n\n"
            "  /br start     — 开始新游戏\n"
            "  /br help      — 游戏帮助"
        )

    def render_level399_escape(self, level_count: int) -> str:
        """通关消息。"""
        return (
            "🎉 你推开了 Level 399 那扇巨大的白色门……\n\n"
            "温暖的光芒吞没了你。当你再次睁开眼睛时，\n"
            "你发现自己躺在 M.E.G.CN 基地的医疗室里。\n\n"
            "══════════════════════════\n"
            "  🎊 恭 喜 通 关 ！ 🎊\n"
            "══════════════════════════\n\n"
            f"你成功地从后室中逃了出来！\n"
            f"经过了 {level_count} 个楼层，你终于找到了回家的路。\n\n"
            "使用 /br start 可以再次挑战。"
        )

    @staticmethod
    def _death_message() -> str:
        return (
            "\n💀 你的生命值降到了 0。你永远留在了后室之中……\n"
            "使用 /br start 重新开始吧。"
        )

    def render_not_started(self) -> str:
        return "你还没有开始游戏！请使用 /br start 开始冒险。"

    def render_no_note(self) -> str:
        return "你身上没有未读的纸条。继续探索可能会有发现。"

    def render_item_not_found(self, item_index: str) -> str:
        return f"背包中没有编号为 {item_index} 的物品。使用 /br inventory 查看背包中的物品编号。"

    def render_no_item_specified(self) -> str:
        return "请指定要使用的物品编号，如：/br use 1"

    def render_already_at_399(self) -> str:
        return "你已经到达 Level 399——最终出口！\n使用 /br exit 尝试推开那扇门吧。"

    # ==================== 基地工作系统 ====================

    def render_work_list(self, player, work_manager) -> str:
        """基地工作面板。"""
        lines = ["══════════════════════\n  🏢 Alpha 基地工作\n══════════════════════\n"]
        lines.append(f"💰 贡献点：{player.currency}")
        lines.append("")

        if player.current_level != 1:
            lines.append("⚠️ 你不在 Alpha 基地。请前往 Level 1 参与工作。")
            return "\n".join(lines)

        lines.append("📋 可接工作：")
        available = work_manager.get_available_works(player.completed_works)
        if available:
            for wid in sorted(available):
                w = work_manager.get_work(wid)
                if not w:
                    continue
                lines.append(f"  [{wid}] {w['title']}")
                lines.append(f"     部门：{w.get('department', '未知')}")
                lines.append(f"     类型：{w.get('puzzle_type', '未知')}")
                lines.append(f"     奖励：{w.get('reward_currency', 0)} 贡献点")
                if w.get("reward_items"):
                    lines.append(f"            + {', '.join(w['reward_items'])}")
        else:
            lines.append("  暂无新工作。")

        lines.append("")

        lines.append("🏆 已完成：")
        if player.completed_works:
            for wid in sorted(player.completed_works):
                w = work_manager.get_work(wid)
                if w:
                    lines.append(f"  ✅ {w['title']}")
        else:
            lines.append("  暂无。")

        lines.append("")
        lines.append("命令：/br work start <ID> 开始 | /br work answer <ID> <答案> 提交")
        return "\n".join(lines)

    def render_work_start(self, work: dict, work_id: str) -> str:
        """开始工作——显示谜题。"""
        lines = [
            f"══════════════════════\n  📝 {work['title']}  [{work_id}]\n══════════════════════\n",
            f"部门：{work.get('department', '未知')}",
            f"类型：{work.get('puzzle_type', '未知')}",
            "",
            work.get("description", ""),
            "",
        ]
        if work.get("hint"):
            lines.append(f"💡 提示：{work['hint']}")
            lines.append("")
        lines.append(f"提交答案：/br work answer {work_id} <你的答案>")
        return "\n".join(lines)

    def render_work_success(self, work: dict, player, story_text: str | None = None, items_pool: list[dict] | None = None) -> str:
        """工作完成。"""
        lines = [f"══════════════════════\n  ✅ 工作完成：{work['title']}\n══════════════════════\n"]
        lines.append(work.get("success_text", "你完成了工作！"))
        lines.append("")
        lines.append(f"🎁 获得 {work.get('reward_currency', 0)} 贡献点")
        if work.get("reward_items"):
            item_names = [BackroomsRenderer._lookup_item_name(item_id, items_pool) for item_id in work["reward_items"]]
            lines.append(f"🎒 获得物品：{', '.join(item_names)}")
        lines.append(f"💰 当前贡献点：{player.currency}")
        if story_text:
            lines.append("")
            lines.append("──────────────────")
            lines.append("📖 新故事解锁：")
            lines.append("")
            lines.append(story_text)
            lines.append("──────────────────")
        return "\n".join(lines)

    def render_work_failure(self, work: dict) -> str:
        """答案错误。"""
        lines = [f"❌ 答案错误！"]
        lines.append(work.get("failure_text", "请再试一次。"))
        lines.append("")
        if work.get("hint"):
            lines.append(f"💡 提示：{work['hint']}")
        return "\n".join(lines)

    # ==================== 工作故事面板 ====================

    def render_story_list(self, unlocked: set[str], work_story_manager) -> str:
        """已解锁的工作故事列表。"""
        lines = ["══════════════════════\n  📖 故事档案\n══════════════════════\n"]

        if not unlocked:
            lines.append("暂无已解锁的故事。完成 Alpha 基地的工作可解锁故事。")
            lines.append("")
            lines.append("使用 /br work 查看可接工作。")
            return "\n".join(lines)

        lines.append(f"已解锁 {len(unlocked)}/{len(work_story_manager.story_ids)} 个故事：")
        lines.append("")

        for story_id in sorted(work_story_manager.story_ids):
            if story_id in unlocked:
                # 尝试读取故事第一行作为标题
                story_text = work_story_manager.get_story(story_id) or ""
                first_line = story_text.split("\n")[0] if story_text else story_id
                lines.append(f"  ✅ [{story_id}] — {first_line}")
                lines.append(f"     → 使用 /br story {story_id} 查看")
            else:
                lines.append(f"  ❓ [{story_id}] — ???（未解锁）")

        lines.append("")
        lines.append("使用 /br story <ID> 以合并转发消息查看具体故事内容。")
        return "\n".join(lines)

    # ==================== 任务系统 ====================

    @staticmethod
    def _format_objective(quest: dict, items_pool: list[dict] | None = None) -> str:
        ot = quest.get("objective_type", "")
        if ot == "reach_level":
            return f"到达 Level {quest.get('objective_target', '?')}"
        if ot == "collect_item":
            item_id = quest.get("objective_item", "?")
            display = BackroomsRenderer._lookup_item_name(item_id, items_pool)
            return f"收集道具「{display}」"
        if ot == "use_item":
            item_id = quest.get("objective_item", "?")
            display = BackroomsRenderer._lookup_item_name(item_id, items_pool)
            return f"提交 {quest.get('objective_count', 1)} 个「{display}」"
        return "未知目标"

    @staticmethod
    def _lookup_item_name(item_id: str, items_pool: list[dict] | None = None) -> str:
        """查找物品的显示名称，找不到则返回原始 ID。"""
        if items_pool:
            for i in items_pool:
                if i["name"] == item_id:
                    return i.get("display_name", item_id)
        return item_id

    def render_quest_list(self, player, quest_manager, items_pool: list[dict] | None = None) -> str:
        """任务面板。"""
        lines = ["══════════════════════\n  📋 任 务 面 板\n══════════════════════\n"]
        lines.append(f"💰 M.E.G.CN 贡献点：{player.currency}\n")

        # 进行中的任务
        lines.append("📌 进行中的任务：")
        if player.active_quests:
            for qid in sorted(player.active_quests):
                q = quest_manager.get_quest(qid)
                if not q:
                    continue
                status = "✅ 可提交" if quest_manager.check_quest_complete(qid, player) else "⏳ 进行中"
                lines.append(f"  [{qid}] {q['title']} — {status}")
                lines.append(f"     目标：{self._format_objective(q, items_pool)}")
                if quest_manager.check_quest_complete(qid, player):
                    lines.append(f"     → 使用 /br quest submit {qid} 提交任务")
        else:
            lines.append("  暂无。在 Alpha 基地遇到安可欣有概率接到任务。")

        lines.append("")

        # 可接任务
        lines.append("📋 可接任务：")
        available = quest_manager.get_available_quests(player.active_quests, player.completed_quests)
        if available:
            for qid in sorted(available):
                q = quest_manager.get_quest(qid)
                if not q:
                    continue
                lines.append(f"  [{qid}] {q['title']}")
                lines.append(f"     目标：{self._format_objective(q, items_pool)}")
                lines.append(f"     奖励：{q.get('reward_text', '?')}")
                lines.append(f"     发布者：{q.get('giver_name', '?')}")
                if q.get("description"):
                    lines.append(f"     描述：{q['description']}")
        else:
            lines.append("  暂无新任务。")

        lines.append("")

        # 已完成
        lines.append("🏆 已完成：")
        if player.completed_quests:
            for qid in sorted(player.completed_quests):
                q = quest_manager.get_quest(qid)
                if q:
                    lines.append(f"  ✅ {q['title']}")
        else:
            lines.append("  暂无。")

        lines.append("\n命令：/br quest accept <ID> 接受 | /br quest submit <ID> 提交")
        return "\n".join(lines)

    def render_quest_accept(self, quest: dict, items_pool: list[dict] | None = None) -> str:
        return (
            f"📋 已接受任务「{quest['title']}」\n\n"
            f"目标：{self._format_objective(quest, items_pool)}\n"
            f"奖励：{quest.get('reward_text', '?')}\n\n"
            f"完成任务后使用 /br quest submit <ID> 提交。"
        )

    def render_quest_submit(self, quest: dict, player, reward_text: str) -> str:
        lines = [f"══════════════════════\n  🎉 任务完成！\n══════════════════════\n"]
        lines.append(f"任务「{quest['title']}」已完成！")
        lines.append("")
        if quest.get("submit_text"):
            lines.append(quest["submit_text"])
        lines.append("")
        lines.append(f"🎁 获得奖励：{reward_text}")
        lines.append(f"💰 当前贡献点：{player.currency}")
        return "\n".join(lines)

    def render_quest_not_complete(self, quest: dict, player, items_pool: list[dict] | None = None) -> str:
        ot = quest.get("objective_type", "")
        lines = [f"⚠️ 任务「{quest['title']}」尚未完成。"]
        lines.append(f"目标：{self._format_objective(quest, items_pool)}")
        if ot == "reach_level":
            lines.append(f"当前楼层：Level {player.current_level}，目标：Level {quest.get('objective_target', '?')}")
        return "\n".join(lines)
