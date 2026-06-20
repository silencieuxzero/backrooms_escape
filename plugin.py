"""后室:逃出生天 — 游戏插件

扮演 M.E.G.CN 工作人员，从 Level 0 出发，在后室中寻找出口不断切入下一个楼层，
直至找到最终出口 Level 399。
"""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maibot_sdk import Command, HookHandler, MaiBotPlugin
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy

from .config import BackroomsGameConfig
from .story import StoryManager, PeopleStoryManager
from .renderer import BackroomsRenderer, RenderContext

# ==================== 外部数据文件 ====================

_BACKROOMS_DATA_PATH = Path(__file__).parent / "backrooms_data.json"
"""插件目录下的物品/实体数据文件路径。"""

_backrooms_data: dict = {}
ITEMS_POOL: list[dict] = []
ENTITIES: dict[str, dict] = {}


def _load_backrooms_data() -> None:
    """加载 backrooms_data.json 到模块全局变量。"""
    global _backrooms_data, ITEMS_POOL, ENTITIES
    fp = _BACKROOMS_DATA_PATH
    if not fp.is_file():
        raise FileNotFoundError(f"缺少数据文件: {fp}，请确保 backrooms_data.json 存在于插件根目录。")
    try:
        _backrooms_data = json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"读取 backrooms_data.json 失败: {exc}") from exc

    ITEMS_POOL = _backrooms_data.get("items", [])
    ENTITIES = _backrooms_data.get("entities", {})
    if not ITEMS_POOL:
        raise RuntimeError("backrooms_data.json 中缺少 items 数据")
    if not ENTITIES:
        raise RuntimeError("backrooms_data.json 中缺少 entities 数据")


# 模块导入时加载数据
_load_backrooms_data()


# ==================== 版本常量 ====================

PLUGIN_VERSION = "1.0.6"
"""插件版本号（与 _manifest.json 同步）。"""

SAVE_VERSION = "1.0.6"
"""存档数据格式版本号，用于存档迁移兼容。"""


# ==================== 游戏数据 ====================

# 知名楼层的详细描述
ICONIC_LEVELS: dict[int, dict[str, Any]] = {
    0: {
        "name": "前厅",
        "title": "Level 0 — 「The Lobby / 前厅」",
        "description": (
            "你睁开眼，发现自己身处一个无限延伸的办公空间。\n"
            "泛黄的墙壁、嗡嗡作响的荧光灯、散发着潮湿气味的地毯……\n"
            "这里没有尽头，每个转角都通向另一个看起来完全相同的走廊。\n"
            "这就是后室的起点——Level 0。作为 M.E.G.CN 的探员，你知道自己必须找到出口。"
        ),
        "danger": "低",
        "entities": ["偶尔能听到远处有什么东西在爬行……"],
        "shortcut_to": None,
    },
    1: {
        "name": "宜居区",
        "title": "Level 1 — 「Habitable Zone / 宜居区」",
        "description": (
            "你切入了 Level 1。这里的走廊更加宽阔，天花板更高，偶尔能看到一些仓库式的房间。\n"
            "荧光灯的嗡嗡声小了，取而代之的是一种低沉的机械轰鸣。\n"
            "这里相对安全，是 M.E.G. 建立了 Alpha 基地的地方。"
        ),
        "danger": "低",
        "entities": ["偶尔有笑魇在远处游荡，但只要保持灯光就不会有事。"],
        "shortcut_to": None,
    },
    2: {
        "name": "管道梦魇",
        "title": "Level 2 — 「Pipe Dreams / 管道梦魇」",
        "description": (
            "Level 2 是一片由无数大型管道组成的迷宫。温度骤然升高，空气闷热潮湿。\n"
            "金属管道发出诡异的咔嗒声，蒸汽不时从破裂处喷出。\n"
            "黑暗中似乎有什么在爬行……你最好小心脚下。"
        ),
        "danger": "中",
        "entities": ["猎犬", "窃皮者"],
        "shortcut_to": None,
    },
    3: {
        "name": "电气站",
        "title": "Level 3 — 「Electrical Station / 电气站」",
        "description": (
            "Level 3 是一座由无数电气设备组成的迷宫。墙壁上布满电线和配电箱，\n"
            "电流的噼啪声此起彼伏。走廊狭窄曲折，时不时会有电火花闪过。\n"
            "这里的危险不仅来自实体，更要小心触电。"
        ),
        "danger": "中",
        "entities": ["笑魇", "电击实体"],
        "shortcut_to": None,
    },
    4: {
        "name": "废弃办公室",
        "title": "Level 4 — 「Abandoned Office / 废弃办公室」",
        "description": (
            "Level 4 看起来像是一座被遗弃的办公大楼。桌椅散落一地，\n"
            "电脑屏幕上闪烁着无意义的代码。窗户外面是一片纯白色的虚空。\n"
            "这里比 Level 0 更加压抑，因为你能看到人类文明的痕迹，却找不到任何一个人。"
        ),
        "danger": "中",
        "entities": ["猎犬", "死亡飞蛾"],
        "shortcut_to": None,
    },
    5: {
        "name": "恐怖旅馆",
        "title": "Level 5 — 「Terror Hotel / 恐怖旅馆」",
        "description": (
            "Level 5 是一座装饰华丽的旅馆，红色的地毯、金色的壁纸、水晶吊灯……\n"
            "但一切看起来都扭曲而诡异。走廊无限延伸，房门后的房间似乎不属于这个世界。\n"
            "不要相信镜子里的倒影，那不是你。"
        ),
        "danger": "高",
        "entities": ["镜像实体", "旅馆管理者"],
        "shortcut_to": None,
    },
    6: {
        "name": "熄灯",
        "title": "Level 6 — 「Lights Out / 熄灯」",
        "description": (
            "Level 6 完全被黑暗吞没。没有光源，没有任何参照物。\n"
            "你只能依靠触觉和听觉在这片虚无中摸索前行。\n"
            "黑暗中传来窸窸窣窣的声音……如果你有手电筒，现在就是用的时候了。"
        ),
        "danger": "高",
        "entities": ["笑魇（大量聚集）"],
        "shortcut_to": None,
    },
    7: {
        "name": "深海恐惧",
        "title": "Level 7 — 「Thalassophobia / 深海恐惧」",
        "description": (
            "Level 7 是一片无边无际的海洋。你发现自己站在海面上，脚下是深不见底的黑暗水域。\n"
            "水面上偶尔能看到漂浮的废墟和残骸。远处的海面下，似乎有巨大的阴影在缓缓移动……\n"
            "不要看水下太久。"
        ),
        "danger": "极高",
        "entities": ["深海之物", "不明巨兽"],
        "shortcut_to": None,
    },
    8: {
        "name": "洞穴系统",
        "title": "Level 8 — 「Cave System / 洞穴系统」",
        "description": (
            "Level 8 是一个巨大而复杂的天然洞穴网络。钟乳石从洞顶垂下，\n"
            "地面上布满了尖锐的岩石和深深的水潭。空气中弥漫着矿物质的味道。\n"
            "洞穴深处传来诡异的回声……"
        ),
        "danger": "中",
        "entities": ["洞穴爬行者", "笑魇"],
        "shortcut_to": None,
    },
    9: {
        "name": "暗黑郊区",
        "title": "Level 9 — 「Darkened Suburbs / 暗黑郊区」",
        "description": (
            "Level 9 是一片永夜的郊区。整齐排列的房屋、空无一人的街道、\n"
            "忽明忽暗的路灯……一切都笼罩在诡异的寂静之中。\n"
            "有些房子的窗户里透出微弱的光，但你不确定是否应该去敲门。"
        ),
        "danger": "中",
        "entities": ["邻里守望者", "猎犬"],
        "shortcut_to": None,
    },
    10: {
        "name": "丰收之景",
        "title": "Level 10 — 「The Bumper Crop / 丰收之景」",
        "description": (
            "Level 10 是一片无边无际的麦田。金黄的麦浪在微风中摇曳，\n"
            "天空中挂着永远不会落下的太阳。乍看之下宁静祥和，\n"
            "但麦田深处隐藏着某种不为人知的恐怖。不要走得太远。"
        ),
        "danger": "中",
        "entities": ["麦田守望者", "稻草人"],
        "shortcut_to": None,
    },
    11: {
        "name": "无尽城市",
        "title": "Level 11 — 「The Endless City / 无尽城市」",
        "description": (
            "Level 11 是一座无限蔓延的现代化城市。高楼大厦林立，\n"
            "街道整洁有序，但空无一人。这里是一个相对安全的层级，\n"
            "M.E.G. 在此设有多个前哨站。但你仍然需要保持警惕。"
        ),
        "danger": "低",
        "entities": ["偶尔有笑魇出没"],
        "shortcut_to": None,
    },
    399: {
        "name": "真正的结局",
        "title": "Level 399 — 「The True Ending / 真正的结局」",
        "description": (
            "⚡⚡⚡ 最终出口！ ⚡⚡⚡\n\n"
            "经过漫长的旅程，你终于找到了传说中的 Level 399。\n"
            "这是一扇巨大的白色门，门缝中透出温暖的光芒。\n"
            "门上刻着模糊的文字——「欢迎回家」。\n\n"
            "你深吸一口气，推开了这扇门……\n\n"
            "恭喜！你已经从后室中成功逃出！"
        ),
        "danger": "无",
        "entities": [],
        "shortcut_to": None,
    },
}

# 探索事件
EXPLORE_EVENTS = [
    {"type": "discovery", "text": "你在一堆杂物中发现了一些补给品。", "give_item": True},
    {"type": "discovery", "text": "墙壁上刻着模糊的涂鸦：「走这边！→」——看来之前有人来过。"},
    {"type": "discovery", "text": "你找到了一个 M.E.G. 遗弃的通讯设备，上面记录了一些关于附近出口的线索。"},
    {"type": "danger", "text": "地板突然塌陷了一小块，你差点摔下去！", "health_cost": 5},
    {"type": "danger", "text": "一股刺鼻的气体从通风口涌出，呛得你直咳嗽。", "health_cost": 5},
    {"type": "discovery", "text": "你在一间废弃的办公室里找到了一张手绘地图，标记了附近区域的概况。"},
    {"type": "discovery", "text": "地上散落着几页日记，上面的字迹潦草而绝望。其中一页写着出口的线索。"},
    {"type": "neutral", "text": "你听到了远处传来的脚步声……但走近后发现什么都没有。"},
    {"type": "neutral", "text": "荧光灯闪烁了几下，然后恢复了正常。空气变得更加凝重了。"},
    {"type": "danger", "text": "你的手不小心碰到了墙壁上的不明黏稠物，皮肤有些刺痛。", "health_cost": 3},
    {"type": "discovery", "text": "你在走廊拐角处发现了一个小型补给箱——运气不错！", "give_item": True},
    {"type": "discovery", "text": "一张贴在墙上的 M.E.G. 公告：「前方高危区域，请谨慎前行。」"},
    {"type": "neutral", "text": "你在一扇半开的门后面发现了一具已经干枯的遗骸，看来有人曾在这里绝望地等待。"},
    {"type": "discovery", "text": "墙上的涂鸦写着一条线索：「红色的门通向安全的地方。」"},
    {"type": "danger", "text": "一根断裂的管道从天花板上掉下来，险些砸到你！", "health_cost": 8},
    {"type": "found_note", "text": "你在墙角发现了一张泛黄的纸条，上面似乎写着什么……"},
]

# 捷径楼层
SHORTCUT_POOL = [
    {"levels_skip": (5, 15), "description": "你发现了一部还能运转的电梯，它带你穿过了多个楼层！"},
    {"levels_skip": (3, 10), "description": "地板突然裂开，你跌入了一个滑道，加速滑过了数个层级……"},
    {"levels_skip": (2, 8), "description": "你找到了一扇标注着「快速通道」的防火门，M.E.G. 真该多建几个这样的东西。"},
    {"levels_skip": (8, 20), "description": "一个神秘的传送门悬浮在半空中，你鼓起勇气走了进去——出来时已经跨越了多个层级。"},
]


# 名人名言池
FAMOUS_QUOTES = [
    "「世界上只有一种真正的英雄主义，那就是在认清生活的真相后依然热爱生活。」—— 罗曼·罗兰",
    "「知行合一。」—— 王阳明",
    "「为天地立心，为生民立命，为往圣继绝学，为万世开太平。」—— 张载",
    "「人生到处知何似，应似飞鸿踏雪泥。」—— 苏轼",
    "「黑夜给了我黑色的眼睛，我却用它寻找光明。」—— 顾城",
    "「血液的作用之一，是为信仰付出代价。」—— 某教科书",
    "「生活不可能像你想象得那么好，但也不会像你想象得那么糟。」—— 莫泊桑",
    "「路漫漫其修远兮，吾将上下而求索。」—— 屈原",
    "「人生如逆旅，我亦是行人。」—— 苏轼",
    "「我思故我在。」—— 笛卡尔",
    "「自由不是做你想做的事，而是不做你不想做的事。」—— 卢梭",
    "「认识你自己。」—— 苏格拉底",
    "「凡事预则立，不预则废。」——《礼记》",
    "「山重水复疑无路，柳暗花明又一村。」—— 陆游",
    "「竹杖芒鞋轻胜马，谁怕？一蓑烟雨任平生。」—— 苏轼",
    "「长风破浪会有时，直挂云帆济沧海。」—— 李白",
    "「沉舟侧畔千帆过，病树前头万木春。」—— 刘禹锡",
    "「天生我材必有用，千金散尽还复来。」—— 李白",
]


# ==================== 玩家状态 ====================

@dataclass
class PlayerState:
    """玩家游戏状态。"""
    user_id: str = ""
    current_level: int = 0
    health: int = 100
    sanity: int = 100
    inventory: list[dict] = field(default_factory=list)
    game_started: bool = False
    exit_attempts: int = 0  # 当前层级尝试找出口的次数
    pending_note: str | None = None  # 待阅读的纸条内容
    unlocked_chars: set[str] = field(default_factory=set)  # 已解锁的角色 ID 集合


# ==================== 插件主体 ====================

class BackroomsGamePlugin(MaiBotPlugin):
    """后室:逃出生天游戏插件"""

    config_model = BackroomsGameConfig

    async def on_load(self) -> None:
        """插件加载时初始化玩家数据存储，并恢复已有存档。"""
        self._players: dict[str, PlayerState] = {}
        self._story_manager = StoryManager()
        self._people_manager = PeopleStoryManager()
        self._renderer = BackroomsRenderer()
        self._plugin_disabled: bool = False
        self._admin_id: str = ""

        # 创建持久化数据目录
        self._data_dir = Path(__file__).parent / "br_data"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self.ctx.logger.info("br_data 目录已就绪: %s", self._data_dir)

        # 加载人物关系文件
        self._people_net_text = self._load_people_net()

        # 从配置读取管理员 ID
        self._admin_id = self.config.plugin.admin_id.strip()
        if self._admin_id:
            self.ctx.logger.info("管理员已配置: user_id=%s", self._admin_id)
        else:
            self.ctx.logger.info("未配置管理员，首个使用 /br off 的用户将自动成为管理员")

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
        description="查看后室背景故事 — M.E.G.CN 加密档案",
        pattern=r"^/br\s+story$",
    )
    async def handle_story(self, **kwargs: Any):
        """用 NapCat 合并转发消息展示后室档案。"""
        stream_id = kwargs.get("stream_id", "")

        story_text = (
            "══════════════════════════\n"
            "  M.E.G.CN 内部档案 #BACKROOMS-0001\n"
            "  密级：最高机密 | 仅供特级探员查阅\n"
            "══════════════════════════\n\n"
            "【研究员 Luna · 后室研究中心】\n\n"
            "后室是一个由无数诡异楼层组成的超自然空间。没有人知道它的起源，"
            "也没有人知道它究竟有多少层。目前 M.E.G.CN 已探明的楼层超过 400 层，"
            "其中 Level 0 是所有切入者的起点，而 Level 399 据信是唯一的稳定出口。\n\n"
            "──────────────────────────\n\n"
            "【特级探员 K · 前线报告】\n\n"
            "我永远不会忘记那个瞬间。上一秒我还在基地的走廊里喝咖啡，"
            "下一秒我就站在了一个无限延伸的黄色办公空间里——这就是 Level 0。\n\n"
            "我在里面走了整整三天才发现第一个出口。那三天里，"
            "我学会了辨别荧光灯的声音变化来判断方向，学会了在转角处先听再走。\n\n"
            "──────────────────────────\n\n"
            "【研究员 Luna · 实体威胁评估】\n\n"
            "笑魇（伤害 15）— 黑暗中的无面实体，光可以驱散\n"
            "猎犬（伤害 20）— 高速四足猛兽，会追踪猎物\n"
            "窃皮者（伤害 25）— 极度危险，会剥取皮肤\n"
            "深海之物（伤害 35）— Level 7 的不可名状存在\n\n"
            "携带手电筒是对抗笑魇最有效的手段。层级钥匙则是每个探员梦寐以求的圣物。\n\n"
            "──────────────────────────\n\n"
            "【特级探员 K · 生存建议】\n\n"
            "如果你正在读这段文字，说明你已经被选中执行后室探索任务。记住：\n"
            "1. 每到一个新楼层，先探索环境，不要急着找出口\n"
            "2. 杏仁水和急救包是你的生命线\n"
            "3. 如果某一层多次找不到出口，回头探索找层级钥匙\n"
            "4. 理智值比生命值更容易被忽视，但理智耗尽同样致命\n\n"
            "活下去。我们在外面等你。\n\n"
            "══════════════════════════\n"
            "档案 #BACKROOMS-0001 阅读完毕\n"
            "祝你好运，探员。\n\n"
            "下一步：使用 /br start 开始你的后室之旅\n"
            "══════════════════════════"
        )

        nodes = [
            self._forward_node("M.E.G.CN-档案部", "M.E.G.CN 档案部 | 加密通讯", story_text),
        ]

        self.ctx.logger.info("发送故事档案: nodes=%d", len(nodes))
        await self._send(stream_id, story_text, nodes=nodes)

        return True, "后室档案已发送", 1

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
    def _load_people_net() -> str:
        """从 config_other/people_relationship.txt 加载人物关系文本。"""
        file_path = Path(__file__).parent / "config_other" / "people_relationship.txt"
        if not file_path.is_file():
            return "暂无人物关系数据。"
        try:
            return file_path.read_text(encoding="utf-8").strip()
        except OSError:
            return "人物关系文件读取失败。"

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
        """阅读检到的纸条。"""
        stream_id = kwargs.get("stream_id", "")
        user_id = str(stream_id)
        player = self._get_player(user_id)

        if not player or not player.game_started:
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
        pattern=r"^/br\s+use\s+(\d+)$",
    )
    async def handle_use(self, **kwargs: Any):
        """使用背包物品。"""
        stream_id = kwargs.get("stream_id", "")

        # SDK 的 match_result 不可靠，从原始消息文本手动提取编号
        message = kwargs.get("message", {})
        raw_text = str(
            message.get("raw_message")
            or message.get("text")
            or message.get("message")
            or ""
        )
        m = re.search(r"/br\s+use\s+(\d+)\s*$", raw_text)
        if not m:
            await self._send(stream_id, self._renderer.render_no_item_specified())
            return True, "未指定物品", 1

        item_index = int(m.group(1))
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
        description="随机名言 — 输出一句名人名言",
        pattern=r"^/br\s+say$",
    )
    async def handle_say(self, **kwargs: Any):
        """随机输出一句名人名言。"""
        stream_id = kwargs.get("stream_id", "")
        await self._do_say(stream_id)
        return True, "名言已发送", 1

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
            if command_name not in ("br_off", "br_on") and user_id != self._admin_id:
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

    # ==================== 辅助方法 ====================

    def _player_file_path(self, user_id: str) -> Path:
        """获取指定用户的存档文件路径。"""
        # 对 user_id 做安全文件名处理，防止路径穿越
        safe_id = "".join(c for c in user_id if c.isalnum() or c in "_-")
        return self._data_dir / f"{safe_id}.json"

    def _save_player(self, user_id: str) -> None:
        """将单个玩家状态保存为 JSON 文件。"""
        player = self._players.get(user_id)
        if player is None:
            return
        data = {
            "save_version": SAVE_VERSION,
            "user_id": player.user_id,
            "current_level": player.current_level,
            "health": player.health,
            "sanity": player.sanity,
            "inventory": player.inventory,
            "game_started": player.game_started,
            "exit_attempts": player.exit_attempts,
            "pending_note": player.pending_note,
            "unlocked_chars": sorted(player.unlocked_chars),
        }
        filepath = self._player_file_path(user_id)
        try:
            filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            self.ctx.logger.error("保存玩家存档失败 user_id=%s: %s", user_id, exc)

    def _load_player(self, user_id: str) -> PlayerState | None:
        """从 JSON 文件加载单个玩家状态；文件不存在则返回 None。"""
        filepath = self._player_file_path(user_id)
        if not filepath.is_file():
            return None
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            self.ctx.logger.error("读取玩家存档失败 user_id=%s: %s", user_id, exc)
            return None

        # 自动迁移旧版存档到当前格式
        data = self._migrate_save_data(data)

        return PlayerState(
            user_id=data.get("user_id", user_id),
            current_level=data.get("current_level", 0),
            health=data.get("health", 100),
            sanity=data.get("sanity", 100),
            inventory=data.get("inventory", []),
            game_started=data.get("game_started", False),
            exit_attempts=data.get("exit_attempts", 0),
            pending_note=data.get("pending_note"),
            unlocked_chars=set(data.get("unlocked_chars", [])),
        )

    def _delete_player_save(self, user_id: str) -> None:
        """删除玩家存档文件（游戏结束/通关时调用）。"""
        filepath = self._player_file_path(user_id)
        try:
            filepath.unlink(missing_ok=True)
        except OSError as exc:
            self.ctx.logger.error("删除玩家存档失败 user_id=%s: %s", user_id, exc)

    def _save_all_players(self) -> None:
        """批量保存所有玩家状态。"""
        for user_id in self._players:
            self._save_player(user_id)

    def _load_all_players(self) -> None:
        """批量加载所有玩家存档恢复至内存。"""
        for filepath in self._data_dir.glob("*.json"):
            user_id = filepath.stem  # 文件名去扩展名即 user_id
            player = self._load_player(user_id)
            if player is not None:
                self._players[user_id] = player

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
        save_version = data.get("save_version", "0.0.0")

        if save_version == "0.0.0":
            # 无版本号存档（v1.0.1 / v1.0.2 格式）
            # 当前格式与旧版兼容，无需字段变更
            pass

        # 标记为当前版本
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

    def _get_or_create_player(self, user_id: str) -> PlayerState:
        """获取或创建玩家状态。"""
        if user_id not in self._players:
            self._players[user_id] = PlayerState(user_id=user_id)
        return self._players[user_id]

    def _get_level_info(self, level: int) -> dict[str, Any]:
        """获取楼层信息。"""
        if level in ICONIC_LEVELS:
            return ICONIC_LEVELS[level]

        # 程序化生成普通楼层
        danger_levels = ["低", "低", "中", "中", "中", "高", "高", "极高"]
        danger = danger_levels[min(level // 50, len(danger_levels) - 1)]

        themes = [
            "无尽的走廊和单调的房间",
            "像迷宫一样的废弃建筑群",
            "扭曲而令人不安的几何空间",
            "昏暗潮湿的地下隧道",
            "空旷而诡异的工业复合体",
            "漂浮在虚空中的破碎建筑碎片",
            "充满异样植物的室内温室",
            "不断旋转的楼梯和错位的房间",
        ]
        theme = themes[level % len(themes)]

        return {
            "name": f"未知区域-{level}",
            "title": f"Level {level}",
            "description": (
                f"你来到了 Level {level}。这是一个未被充分记录的后室层级。\n"
                f"这里的主要特征是{theme}。\n"
                f"危险等级：{danger}。保持警惕，继续前进。"
            ),
            "danger": danger,
            "entities": ["未知实体"],
            "shortcut_to": None,
        }

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
        weights = [
            cfg.item_weight_o1,
            cfg.item_weight_o2,
            cfg.item_weight_o3,
            cfg.item_weight_o4,
            cfg.item_weight_o5,
            cfg.item_weight_o6,
            cfg.item_weight_o7,
        ]
        # 确保总权重 > 0
        total_weight = sum(weights)
        if total_weight <= 0:
            return random.choice(ITEMS_POOL)

        r = random.randint(1, total_weight)
        cumulative = 0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative and i < len(ITEMS_POOL):
                return ITEMS_POOL[i]
        return ITEMS_POOL[-1]

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
            game_started=True,
        )
        self._players[user_id] = player
        self._save_player(user_id)

        ctx = self._make_ctx(player)
        nodes = [
            self._forward_node("M.E.G.CN-指挥中心", "M.E.G.CN 指挥部", text)
            for text in self._renderer.render_start_nodes(ctx)
        ]
        await self._send(stream_id, "", nodes=nodes)

    async def _do_use_item(self, stream_id: str, item_index: int) -> None:
        """使用背包物品（按编号）。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.game_started:
            await self._send(stream_id, self._renderer.render_not_started())
            return

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

        if effect == "health_restore":
            player.health = min(cfg.initial_health, player.health + value)
        elif effect == "sanity_restore":
            player.sanity = min(cfg.initial_sanity, player.sanity + value)

        ctx = self._make_ctx(player)
        remaining = [i.get("display_name", i["name"]) for i in player.inventory]

        await self._send(
            stream_id,
            self._renderer.render_use_item(item, ctx, remaining),
        )
        self._save_player(user_id)

    async def _do_explore(self, stream_id: str) -> None:
        """探索当前楼层。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.game_started:
            await self._send(stream_id, self._renderer.render_not_started())
            return

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
        char_encounter: tuple[str, str, str | None] | None = None
        if player.current_level == 1:
            level1_chars = [cid for cid in ("ankexin", "anjinian")
                            if self._people_manager.get_story_count(cid) > 0]
            if level1_chars and random.random() < 0.40:
                char_id = random.choice(level1_chars)
                story_text = self._people_manager.get_random_story(char_id)
                if story_text:
                    # 首次遇到角色：赠送 2 瓶杏仁水
                    char_gift: str | None = None
                    if char_id not in player.unlocked_chars:
                        almond_water = {"name": "o1", "type": "consumable", "effect": "sanity_restore", "value": 30,
                                        "display_name": "杏仁水",
                                        "description": "后室中最常见的补给品，喝下可以恢复理智，味道像融化的杏仁冰淇淋。"}
                        player.inventory.append(dict(almond_water))
                        player.inventory.append(dict(almond_water))
                        char_gift = "🎁 对方给了你 2 瓶杏仁水作为见面礼。"
                    char_encounter = (char_id, story_text, char_gift)
                    player.unlocked_chars.add(char_id)

        # 理智值过低效果
        if player.sanity <= 0:
            player.health = max(0, player.health - 10)

        # 死亡处理
        if player.health <= 0:
            player.game_started = False
            del self._players[user_id]
            self._delete_player_save(user_id)

        ctx = self._make_ctx(player)
        await self._send(
            stream_id,
            self._renderer.render_explore(ctx, event_text, crate_result, health_cost, note_found, entity_encounter, char_encounter),
        )
        self._save_player(user_id)

    async def _do_exit(self, stream_id: str) -> None:
        """尝试寻找出口。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.game_started:
            await self._send(stream_id, self._renderer.render_not_started())
            return

        cfg = self.config.game

        # Level 399 特殊处理
        if player.current_level == 399:
            await self._send(
                stream_id,
                self._renderer.render_level399_escape(player.current_level),
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
                    self._renderer.render_level399_escape(from_level + 1),
                )
                del self._players[user_id]
                self._delete_player_save(user_id)
                return

            shortcut_desc: str | None = None

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

            new_level_info = self._get_level_info(player.current_level)
            ctx = self._make_ctx(player)
            await self._send(
                stream_id,
                self._renderer.render_exit_found(ctx, new_level_info, shortcut_desc, from_level),
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
                player.game_started = False
                del self._players[user_id]
                self._delete_player_save(user_id)

            ctx = self._make_ctx(player)
            await self._send(
                stream_id,
                self._renderer.render_exit_not_found(
                    ctx, player.exit_attempts, event_text,
                    ex_crate_result, ex_health_cost, ex_note_found,
                ),
            )

        self._save_player(user_id)

    async def _do_status(self, stream_id: str) -> None:
        """查看当前状态。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.game_started:
            await self._send(stream_id, self._renderer.render_not_started())
            return

        ctx = self._make_ctx(player)
        inventory_text = self._format_inventory(player)
        await self._send(
            stream_id,
            self._renderer.render_status(ctx, inventory_text),
        )

    async def _do_show_inventory(self, stream_id: str) -> None:
        """查看背包。"""
        user_id = str(stream_id)
        player = self._get_player(user_id)
        if not player or not player.game_started:
            await self._send(stream_id, self._renderer.render_not_started())
            return

        inventory_text = self._format_inventory(player)

        hints = []
        if self._has_item(player, "o4"):
            hints.append("🔑 你持有层级钥匙！使用 /br exit 可以 100% 找到出口。")
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
        if player and player.game_started:
            unlocked = player.unlocked_chars
        await self._send(
            stream_id,
            self._renderer.render_people_net(self._people_net_text, unlocked),
        )

    async def _do_say(self, stream_id: str) -> None:
        """随机输出一句名人名言。"""
        quote = random.choice(FAMOUS_QUOTES)
        await self._send(
            stream_id,
            f"══ 名人名言 ══\n\n{quote}",
        )

    async def _do_off(self, stream_id: str, message: dict) -> None:
        """关闭插件：仅管理员可用，禁用后仅管理员可继续使用。"""
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        # 未配置管理员：首个关闭者自动成为管理员
        if not self._admin_id:
            self._admin_id = user_id
            self._plugin_disabled = True
            self.ctx.logger.info("插件已关闭，管理员 user_id=%s", user_id)
            await self._send(stream_id, "🔒 插件已关闭。现在只有你可以使用本插件。")
            return

        # 已配置管理员：验证身份
        if user_id != self._admin_id:
            await self._send(stream_id, "❌ 你不是管理员，无权关闭插件。")
            return

        self._plugin_disabled = True
        self.ctx.logger.info("插件已由管理员重新关闭 user_id=%s", user_id)
        await self._send(stream_id, "🔒 插件已关闭。")

    async def _do_on(self, stream_id: str, message: dict) -> None:
        """重新启用插件：仅管理员可用。"""
        user_id = self._resolve_user_id(message, stream_id)
        if not user_id:
            await self._send(stream_id, "❌ 无法识别你的身份，不能执行此操作。")
            return

        if user_id != self._admin_id:
            await self._send(stream_id, "❌ 你不是管理员，无权启用插件。")
            return

        self._plugin_disabled = False
        self.ctx.logger.info("插件已由管理员重新启用 user_id=%s", user_id)
        await self._send(stream_id, "🔓 插件已重新启用，所有用户均可使用。")


def create_plugin() -> BackroomsGamePlugin:
    """创建后室:逃出生天游戏插件实例。"""
    return BackroomsGamePlugin()
