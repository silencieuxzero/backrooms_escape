"""后室:逃出生天 — 游戏插件

扮演 M.E.G.CN 工作人员，从 Level 0 出发，在后室中寻找出口不断切入下一个楼层，
直至找到最终出口 Level 399。
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from maibot_sdk import Command, HookHandler, MaiBotPlugin
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy

from .config import BackroomsGameConfig
from .renderer import (
    BackroomsRenderer,
    RenderContext,
    GameEvent,
    GameStateMachine,
    CHARACTERS,
    CharacterEncounterService,
    build_system_prompt,
    build_message_list,
    trim_history,
    is_end_dialog,
    StoryManager,
    PeopleStoryManager,
    QuestManager,
    WorkManager,
    BaseWorkStoryManager,
    ShutManager,
)

# ==================== 外部数据文件 ====================

_BACKROOMS_DATA_PATH = Path(__file__).parent / "renderer_load" / "backrooms_data.json"
"""插件目录下的物品/实体数据文件路径。"""

ITEMS_POOL: list[dict] = []
ENTITIES: dict[str, dict] = {}


def _load_backrooms_data() -> None:
    """加载 backrooms_data.json 到模块全局变量。"""
    global ITEMS_POOL, ENTITIES
    fp = _BACKROOMS_DATA_PATH
    if not fp.is_file():
        raise FileNotFoundError(f"缺少数据文件: {fp}，请确保 backrooms_data.json 存在于插件根目录。")
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"读取 backrooms_data.json 失败: {exc}") from exc

    ITEMS_POOL = data.get("items", [])
    ENTITIES = data.get("entities", {})
    if not ITEMS_POOL:
        raise RuntimeError("backrooms_data.json 中缺少 items 数据")
    if not ENTITIES:
        raise RuntimeError("backrooms_data.json 中缺少 entities 数据")


# 模块导入时加载数据
_load_backrooms_data()


# ==================== 版本常量 ====================

PLUGIN_VERSION = "1.1.5"
"""插件版本号（与 _manifest.json 同步）。"""

SAVE_VERSION = "1.1.5"
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
            "这里相对安全，是 M.E.G.CN 建立了 Alpha 基地的地方。"
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
            "街道整洁有序，但空无一人。这里是一个相对安全的楼层，\n"
            "M.E.G.CN 在此设有多个前哨站。但你仍然需要保持警惕。"
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
    {"type": "discovery", "text": "你找到了一个 M.E.G.CN 遗弃的通讯设备，上面记录了一些关于附近出口的线索。"},
    {"type": "danger", "text": "地板突然塌陷了一小块，你差点摔下去！", "health_cost": 5},
    {"type": "danger", "text": "一股刺鼻的气体从通风口涌出，呛得你直咳嗽。", "health_cost": 5},
    {"type": "discovery", "text": "你在一间废弃的办公室里找到了一张手绘地图，标记了附近区域的概况。"},
    {"type": "discovery", "text": "地上散落着几页日记，上面的字迹潦草而绝望。其中一页写着出口的线索。"},
    {"type": "neutral", "text": "你听到了远处传来的脚步声……但走近后发现什么都没有。"},
    {"type": "neutral", "text": "荧光灯闪烁了几下，然后恢复了正常。空气变得更加凝重了。"},
    {"type": "danger", "text": "你的手不小心碰到了墙壁上的不明黏稠物，皮肤有些刺痛。", "health_cost": 3},
    {"type": "discovery", "text": "你在走廊拐角处发现了一个小型补给箱——运气不错！", "give_item": True},
    {"type": "discovery", "text": "一张贴在墙上的 M.E.G.CN 公告：「前方高危区域，请谨慎前行。」"},
    {"type": "neutral", "text": "你在一扇半开的门后面发现了一具已经干枯的遗骸，看来有人曾在这里绝望地等待。"},
    {"type": "discovery", "text": "墙上的涂鸦写着一条线索：「红色的门通向安全的地方。」"},
    {"type": "danger", "text": "一根断裂的管道从天花板上掉下来，险些砸到你！", "health_cost": 8},
    {"type": "found_note", "text": "你在墙角发现了一张泛黄的纸条，上面似乎写着什么……"},
]

# ── Alpha 基地探索事件 ──
# 仅在 Level 1 使用 /br explore base 时触发
BASE_EXPLORE_EVENTS = [
    {"area": "休息区", "text": "你走进 Alpha 基地的休息区。几盏暖黄色的灯照亮了摆放着旧沙发和折叠椅的角落，墙上的公告板贴满了便签和手绘地图。空气中弥漫着速溶咖啡的味道。", "type": "neutral"},
    {"area": "通讯室", "text": "通讯室里设备嗡嗡作响。一名操作员正戴着耳机调试频率，屏幕上跳动着信号波形图。角落里堆着几台待修的无线电设备。", "type": "neutral"},
    {"area": "工程部", "text": "工程部的门半掩着，里面传来工具碰撞的清脆声响。工作台上散落着拆开的零件和电路板，墙上挂满了各种手工改造的工具。", "type": "neutral"},
    {"area": "食堂", "text": "食堂里，薛师傅正往大锅里倒着什么。几个探员围坐在简易餐桌旁，低声交流着各楼层的见闻。后室的罐头食品虽然乏味，但在这片混乱中能有一口热乎的已属不易。", "type": "discovery"},
    {"area": "仓库", "text": "仓库里整齐地码放着物资箱——杏仁水、急救包、手电筒电池。管理员正在清点库存，看到你进来点了点头。", "type": "discovery"},
    {"area": "档案室", "text": "档案室里弥漫着旧纸和灰尘的气味。铁皮柜里分类存放着各楼层的探索记录、实体观察报告和已知出口坐标。你在翻阅时发现了一些有趣的信息。", "type": "discovery", "info_gain": True},
    {"area": "医疗站", "text": "医疗站的灯光比基地其他地方都要亮一些。简易的床位上躺着一名刚从前线回来的伤员，医护人员正在为他包扎伤口。", "type": "neutral"},
    {"area": "训练场", "text": "训练场上，几名新人在进行模拟逃生演练。一名教官正在大声强调着后室生存的基本原则——「永远不要背对黑暗。」", "type": "neutral"},
    {"area": "休息区", "text": "休息区里，有人在弹一把走了音的旧吉他。虽然音准不对，但那旋律在这样的环境里却出奇地让人安心。", "type": "neutral"},
    {"area": "通讯室", "text": "你路过通讯室时，正好收到一段来自 Level 5 的加密信号。操作员表示解码后会交给信息分析组处理。", "type": "discovery", "info_gain": True},
    {"area": "工程部", "text": "安继年不在工程部，但工作台上留着一张字条——「去北区修管道了，扳手别动。」旁边还放着一个简易的应急灯。", "type": "discovery", "give_item": True},
    {"area": "食堂", "text": "食堂今天开了一箱宝贵的调味料。薛师傅心情不错，给每个人多加了一勺酱料——虽然不知道是什么做的，但至少让罐头有了些滋味。", "type": "neutral"},
    {"area": "仓库", "text": "仓库管理员正在整理新到的一批物资。他看到你后把你叫住，递给你一小瓶杏仁水——「路上小心，新人。」", "type": "discovery", "give_item": True},
    {"area": "档案室", "text": "你在档案室找到了一份旧日志，记录着 M.E.G.CN 刚建立 Alpha 基地时的艰难岁月。日志的作者用平淡的语气描述了最初那批人如何在 Level 1 扎下了根。", "type": "discovery", "info_gain": True},
]

# 捷径楼层
SHORTCUT_POOL = [
    {"levels_skip": (5, 15), "description": "你发现了一部还能运转的电梯，它带你穿过了多个楼层！"},
    {"levels_skip": (3, 10), "description": "地板突然裂开，你跌入了一个滑道，加速滑过了数个楼层……"},
    {"levels_skip": (2, 8), "description": "你找到了一扇标注着「快速通道」的防火门，M.E.G.CN 真该多建几个这样的东西。"},
    {"levels_skip": (8, 20), "description": "一个神秘的传送门悬浮在半空中，你鼓起勇气走了进去——出来时已经跨越了多个楼层。"},
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


def _load_companions(data: dict) -> list[str]:
    """从存档字典加载同行列表，兼容旧版单个 ``companion`` 字段。

    - 新版（v1.1.3+）：``"companions": ["ankexin", "xiazhong"]``
    - 旧版（v1.1.2-）：``"companion": "ankexin"``
    """
    raw = data.get("companions")
    if isinstance(raw, list):
        return list(raw)
    raw = data.get("companion")
    if isinstance(raw, str) and raw:
        return [raw]
    return []

@dataclass
class PlayerState:
    """玩家游戏状态。"""
    user_id: str = ""
    current_level: int = 0
    health: int = 100
    sanity: int = 100
    inventory: list[dict] = field(default_factory=list)
    fsm: GameStateMachine = field(default_factory=GameStateMachine)
    exit_attempts: int = 0  # 当前楼层尝试找出口的次数
    pending_note: str | None = None  # 待阅读的纸条内容
    unlocked_chars: set[str] = field(default_factory=set)  # 已解锁的角色 ID 集合
    currency: int = 0  # M.E.G.CN 内部贡献点
    active_quests: set[str] = field(default_factory=set)  # 进行中的任务 ID
    completed_quests: set[str] = field(default_factory=set)  # 已完成的任务 ID
    pending_quest_offer: str | None = None  # 待接受的任务 ID（角色给出但还未接受）
    available_works: set[str] = field(default_factory=set)  # 基地可接的工作 ID
    completed_works: set[str] = field(default_factory=set)  # 已完成的工作 ID
    work_stories: set[str] = field(default_factory=set)  # 已解锁的工作故事 ID
    l1_explore_count: int = 0  # Level 1 中已探索次数（达到阈值触发日常任务）
    favorability: dict[str, int] = field(default_factory=dict)  # 角色好感度 {char_id: 数值}
    companions: list[str] = field(default_factory=list)  # 同行角色 ID 列表
    consecutive_misses: int = 0  # 同楼层连续未触发角色遭遇的次数
    visited_levels: set[int] = field(default_factory=set)  # 已访问过的楼层集合
    dialog_char_id: str | None = None  # 对话模式中的角色 ID，None 表示非对话模式
    dialog_node_id: str = "start"  # 当前对话树节点 ID
    dialog_history: list[dict[str, str]] = field(default_factory=list)  # 对话历史 [{role, content}]


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
            "state": player.fsm.state.value,
            "exit_attempts": player.exit_attempts,
            "pending_note": player.pending_note,
            "unlocked_chars": sorted(player.unlocked_chars),
            "currency": player.currency,
            "active_quests": sorted(player.active_quests),
            "completed_quests": sorted(player.completed_quests),
            "pending_quest_offer": player.pending_quest_offer,
            "available_works": sorted(player.available_works),
            "completed_works": sorted(player.completed_works),
            "work_stories": sorted(player.work_stories),
            "l1_explore_count": player.l1_explore_count,
            "favorability": player.favorability,
            "companions": list(player.companions),
            "consecutive_misses": player.consecutive_misses,
            "visited_levels": sorted(player.visited_levels),
            "dialog_char_id": player.dialog_char_id,
            "dialog_node_id": player.dialog_node_id,
            "dialog_history": player.dialog_history,
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
            fsm=GameStateMachine.from_dict(data),
            exit_attempts=data.get("exit_attempts", 0),
            pending_note=data.get("pending_note"),
            unlocked_chars=set(data.get("unlocked_chars", [])),
            currency=data.get("currency", 0),
            active_quests=set(data.get("active_quests", [])),
            completed_quests=set(data.get("completed_quests", [])),
            pending_quest_offer=data.get("pending_quest_offer"),
            available_works=set(data.get("available_works", [])),
            completed_works=set(data.get("completed_works", [])),
            work_stories=set(data.get("work_stories", [])),
            l1_explore_count=data.get("l1_explore_count", 0),
            favorability=data.get("favorability", {}),
            companions=_load_companions(data),
            consecutive_misses=data.get("consecutive_misses", 0),
            visited_levels=set(data.get("visited_levels", [])),
            dialog_char_id=data.get("dialog_char_id"),
            dialog_node_id=data.get("dialog_node_id", "start"),
            dialog_history=data.get("dialog_history", []),
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
                f"你来到了 Level {level}。这是一个未被充分记录的后室楼层。\n"
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
                reply = result.get("response", "").strip()
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
                farewell_text = result.get("response", "").strip()
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
                    farewell_text = result.get("response", "").strip()
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
                reply = result.get("response", "").strip()
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

    async def _do_say(self, stream_id: str) -> None:
        """随机输出一句名人名言。"""
        quote = random.choice(FAMOUS_QUOTES)
        await self._send(
            stream_id,
            f"══ 名人名言 ══\n\n{quote}",
        )

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
