"""后室:逃出生天 — 游戏静态数据

包含楼层层级定义、探索事件、捷径池、物品/实体加载等静态游戏数据。
所有数据为模块级常量，服务启动时通过 ``load_items_pool()`` 加载外部 JSON。
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

# ==================== 物品/实体数据加载 ====================

_BACKROOMS_DATA_PATH = Path(__file__).parent.parent / "story_load" / "backrooms_data.json"

ITEMS_POOL: list[dict] = []
"""全局物品模板池，启动时从 backrooms_data.json 加载。"""

ENTITIES: dict[str, dict] = {}
"""全局实体数据，启动时从 backrooms_data.json 加载。"""


def load_items_pool() -> None:
    """加载 backrooms_data.json 到模块全局变量 ITEMS_POOL 和 ENTITIES。

    在服务初始化时调用一次。
    若加载失败则抛出异常，阻止插件启动。
    """
    global ITEMS_POOL, ENTITIES
    fp = _BACKROOMS_DATA_PATH
    if not fp.is_file():
        raise FileNotFoundError(
            f"缺少数据文件: {fp}，请确保 backrooms_data.json 存在于 story_load 目录。"
        )
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


# ==================== 知名楼层定义 ====================

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
        "entities": [],
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
        "entities": [],
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
        "entities": [],
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

# ==================== 探索事件 ====================

EXPLORE_EVENTS: list[dict[str, Any]] = [
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

# Alpha 基地探索事件（仅 Level 1 使用 /br explore base 时触发）
BASE_EXPLORE_EVENTS: list[dict[str, Any]] = [
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
SHORTCUT_POOL: list[dict[str, Any]] = [
    {"levels_skip": (5, 15), "description": "你发现了一部还能运转的电梯，它带你穿过了多个楼层！"},
    {"levels_skip": (3, 10), "description": "地板突然裂开，你跌入了一个滑道，加速滑过了数个楼层……"},
    {"levels_skip": (2, 8), "description": "你找到了一扇标注着「快速通道」的防火门，M.E.G.CN 真该多建几个这样的东西。"},
    {"levels_skip": (8, 20), "description": "一个神秘的传送门悬浮在半空中，你鼓起勇气走了进去——出来时已经跨越了多个楼层。"},
]


# ==================== 游戏数据服务 ====================

class GameDataService:
    """游戏静态数据服务。

    封装楼层信息查询、事件抽取、物品权重随机等与静态数据相关的操作。
    作为纯数据服务，不依赖插件实例或 SDK。
    """

    @staticmethod
    def get_level_info(level: int) -> dict[str, Any]:
        """获取指定楼层的信息字典。

        知名楼层（0-11, 399）返回预定义描述，
        其他楼层通过程序化生成返回通用描述。
        """
        if level in ICONIC_LEVELS:
            return ICONIC_LEVELS[level]

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

    @staticmethod
    def random_item(item_weights: dict[str, int]) -> dict:
        """根据配置权重从 ITEMS_POOL 中随机选择一个物品。

        Args:
            item_weights: {"o1": weight, "o2": weight, ...} 物品权重映射。

        Returns:
            随机选中的物品模板字典。
        """
        weights = [
            item_weights.get("o1", 1),
            item_weights.get("o2", 1),
            item_weights.get("o3", 1),
            item_weights.get("o4", 1),
            item_weights.get("o5", 1),
            item_weights.get("o6", 1),
            item_weights.get("o7", 1),
        ]
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

    @staticmethod
    def item_display_name(item_name: str) -> str:
        """获取物品的显示名称。"""
        for i in ITEMS_POOL:
            if i["name"] == item_name:
                return i.get("display_name", item_name)
        return item_name
