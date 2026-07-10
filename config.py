"""后室:逃出生天插件配置模型。"""

from __future__ import annotations

from typing import Literal

from maibot_sdk import Field, PluginConfigBase


class PluginSectionConfig(PluginConfigBase):
    """插件基础配置。"""

    __ui_label__ = "插件"
    __ui_icon__ = "package"
    __ui_order__ = 0

    enabled: bool = Field(
        default=True,
        description="是否启用插件",
        json_schema_extra={
            "label": "启用插件",
            "hint": "关闭后插件将停止响应，所有游戏功能不可用。",
            "order": 0,
        },
    )
    output_mode: Literal["text", "forward"] = Field(
        default="text",
        description="消息输出模式：text=普通消息，forward=合并转发消息",
        json_schema_extra={
            "label": "消息输出模式",
            "hint": "选择插件消息的发送方式。text=普通文本消息，forward=合并转发消息（更美观）。",
            "order": 1,
        },
    )
    admin_ids: list[str] = Field(
        default_factory=list,
        description="管理员QQ号列表（只能通过修改配置文件来增减管理员）",
        json_schema_extra={
            "label": "管理员QQ号列表",
            "hint": "在此填写管理员的 QQ 号（每行一个）。只有列表中的用户可以使用 /br off、/br on、/br shut 命令。留空则无人可管理。",
            "order": 2,
        },
    )
    config_version: str = Field(
        default="1.1.0",
        description="配置版本（与插件版本同步）",
        json_schema_extra={
            "label": "配置版本",
            "disabled": True,
            "hidden": True,
            "order": 99,
        },
    )


class GameConfig(PluginConfigBase):
    """游戏参数配置。"""

    __ui_label__ = "游戏参数"
    __ui_icon__ = "gamepad-2"
    __ui_order__ = 1

    # ---- 核心属性 ----
    initial_health: int = Field(
        default=100,
        description="初始生命值",
        json_schema_extra={
            "label": "初始生命值",
            "hint": "玩家进入游戏时的初始生命值，生命值归零则游戏结束。",
            "order": 0,
        },
    )
    initial_sanity: int = Field(
        default=100,
        description="初始理智值",
        json_schema_extra={
            "label": "初始理智值",
            "hint": "玩家进入游戏时的初始理智值，理智值归零则游戏结束。",
            "order": 1,
        },
    )

    # ---- 探索消耗 ----
    explore_sanity_cost: int = Field(
        default=2,
        description="每次探索所消耗的理智值",
        json_schema_extra={
            "label": "探索理智消耗",
            "hint": "玩家每探索一个楼层所消耗的理智值。",
            "order": 2,
        },
    )
    exit_search_sanity_cost: int = Field(
        default=5,
        description="每次寻找出口所消耗的理智值",
        json_schema_extra={
            "label": "寻找出口理智消耗",
            "hint": "玩家每次尝试寻找出口所消耗的理智值。",
            "order": 3,
        },
    )

    # ---- 出口概率 ----
    base_exit_chance: float = Field(
        default=0.2,
        ge=0.0, le=1.0,
        description="成功找到出口的基础概率（0.0~1.0）",
        json_schema_extra={
            "label": "基础出口概率",
            "hint": "每次寻找出口时的基础成功概率，取值范围 0.0 ~ 1.0。",
            "order": 4,
        },
    )
    exit_chance_increment: float = Field(
        default=0.1,
        ge=0.0, le=1.0,
        description="每次寻找失败后成功概率的提升值",
        json_schema_extra={
            "label": "出口概率递增值",
            "hint": "每次寻找出口失败后，下次寻找的成功概率会累加该值。",
            "order": 5,
        },
    )

    # ---- 遭遇概率 ----
    entity_encounter_chance: float = Field(
        default=0.25,
        description="在楼层中遭遇实体的基础概率",
        json_schema_extra={
            "label": "实体遭遇概率",
            "hint": "玩家在每个楼层中遭遇实体的基础概率，取值范围 0.0 ~ 1.0。",
            "order": 6,
        },
    )
    ankexin_task_chance: float = Field(
        default=0.5,
        description="遇到安可欣时获得任务的概率（0.0~1.0）",
        json_schema_extra={
            "label": "安可欣任务概率",
            "hint": "在 Alpha 基地遇到安可欣时，她给你布置任务的概率，取值范围 0.0 ~ 1.0。",
            "order": 7,
        },
    )
    work_trigger_interval: int = Field(
        default=10,
        description="在 Level 1 每探索多少次触发一次安可欣的日常工作任务",
        json_schema_extra={
            "label": "日常任务触发间隔",
            "hint": "在 Level 1 每探索多少次后，安可欣会主动给你派发一个新的基地日常工作任务。",
            "order": 8,
        },
    )
    # ---- 物资箱概率 ----
    crate_large_chance: float = Field(
        default=0.08,
        description="大型物资箱出现概率",
        json_schema_extra={
            "label": "大型物资箱概率",
            "hint": "触发补给事件时出现大型物资箱的概率。大型箱必出杏仁水。",
            "order": 9,
        },
    )
    crate_medium_chance: float = Field(
        default=0.15,
        description="中型物资箱出现概率",
        json_schema_extra={
            "label": "中型物资箱概率",
            "hint": "触发补给事件时出现中型物资箱的概率。中型箱必出杏仁水。",
            "order": 10,
        },
    )
    crate_small_chance: float = Field(
        default=0.25,
        description="小型物资箱出现概率",
        json_schema_extra={
            "label": "小型物资箱概率",
            "hint": "触发补给事件时出现小型物资箱的概率。小型箱必出杏仁水。",
            "order": 11,
        },
    )

    # ---- 好感度配置 ----
    favorability_threshold: int = Field(
        default=70,
        description="邀请角色一起探索所需的好感度阈值",
        json_schema_extra={
            "label": "邀请好感度阈值",
            "hint": "与角色的好感度达到此值后，可以使用 /br invite <角色名> 邀请对方一起探索后室。",
            "order": 19,
        },
    )
    favorability_per_encounter: int = Field(
        default=2,
        description="每次在 Level 1 遇到角色时增加的好感度",
        json_schema_extra={
            "label": "单次遭遇好感度",
            "hint": "在 Level 1 的 Alpha 基地遇到角色并互动时，好感度增加的值。",
            "order": 20,
        },
    )

    # ---- 赠礼配置 ----
    gift_favorability_values: dict[str, int] = Field(
        default_factory=lambda: {
            "o1": 5,
            "o2": 5,
            "o3": 5,
            "o4": 5,
            "o5": 5,
            "o6": 5,
            "o7": 5,
        },
        description="各物品作为赠礼时的好感度值映射（key=物品name，value=好感度）",
        json_schema_extra={
            "label": "赠礼好感度映射",
            "hint": "将背包中的物品赠送给角色时，各物品增加的好感度值。",
            "order": 21,
        },
    )

    # ---- 各物品获取权重（权重越高，获得概率越大） ----
    item_weight_o1: int = Field(
        default=3,
        description="杏仁水获取权重（越高越常见）",
        json_schema_extra={
            "label": "杏仁水权重",
            "hint": "发现补给品时获得杏仁水的权重，权重越高越常见。",
            "order": 12,
        },
    )
    item_weight_o2: int = Field(
        default=3,
        description="急救包获取权重",
        json_schema_extra={
            "label": "急救包权重",
            "hint": "发现补给品时获得急救包的权重，权重越高越常见。",
            "order": 13,
        },
    )
    item_weight_o3: int = Field(
        default=2,
        description="手电筒获取权重",
        json_schema_extra={
            "label": "手电筒权重",
            "hint": "发现补给品时获得手电筒的权重，权重越高越常见。",
            "order": 14,
        },
    )
    item_weight_o4: int = Field(
        default=1,
        description="楼层钥匙获取权重",
        json_schema_extra={
            "label": "楼层钥匙权重",
            "hint": "发现补给品时获得楼层钥匙的权重，权重越高越常见。",
            "order": 15,
        },
    )
    item_weight_o5: int = Field(
        default=2,
        description="M.E.G.CN 无线电获取权重",
        json_schema_extra={
            "label": "M.E.G.CN 无线电权重",
            "hint": "发现补给品时获得 M.E.G.CN 无线电的权重，权重越高越常见。",
            "order": 16,
        },
    )
    item_weight_o6: int = Field(
        default=2,
        description="能量棒获取权重",
        json_schema_extra={
            "label": "能量棒权重",
            "hint": "发现补给品时获得能量棒的权重，权重越高越常见。",
            "order": 17,
        },
    )
    item_weight_o7: int = Field(
        default=2,
        description="镇定剂获取权重",
        json_schema_extra={
            "label": "镇定剂权重",
            "hint": "发现补给品时获得镇定剂的权重，权重越高越常见。",
            "order": 18,
        },
    )


class WhitelistConfig(PluginConfigBase):
    """白名单配置 — 分别控制群组和私聊的访问权限。"""

    __ui_label__ = "访问白名单"
    __ui_icon__ = "security"
    __ui_order__ = 2

    enabled: bool = Field(
        default=False,
        description="是否启用白名单（关闭后所有用户均可使用插件）",
        json_schema_extra={
            "label": "启用白名单",
            "hint": "开启后仅白名单内的群组和用户可以使用插件，关闭后所有用户均可使用。",
            "order": 0,
        },
    )
    group_ids: list[str] = Field(
        default_factory=list,
        description="群组白名单列表（在此填写允许使用插件的群号，每行一个）",
        json_schema_extra={
            "label": "群组白名单",
            "hint": "在此填写允许使用插件的群号，每行填写一个群号。",
            "order": 1,
        },
    )
    user_ids: list[str] = Field(
        default_factory=list,
        description="私聊白名单列表（在此填写允许使用插件的用户 QQ 号，每行一个）",
        json_schema_extra={
            "label": "私聊白名单",
            "hint": "在此填写允许使用插件的用户 QQ 号，每行填写一个 QQ 号。",
            "order": 2,
        },
    )

    # ---- 白名单拒绝提示（可自定义） ----
    group_deny_message: str = Field(
        default="你所在的群组不在白名单中，无法使用后室:逃出生天插件。",
        description="群组被白名单拒绝时显示的提示信息",
        json_schema_extra={
            "label": "群组拒绝提示",
            "hint": "当群组不在白名单中时，向该群发送的拒绝提示信息。",
            "order": 3,
        },
    )
    private_deny_message: str = Field(
        default="你不在白名单中，无法使用后室:逃出生天插件。",
        description="私聊用户被白名单拒绝时显示的提示信息",
        json_schema_extra={
            "label": "私聊拒绝提示",
            "hint": "当用户不在私聊白名单中时，向该用户发送的拒绝提示信息。",
            "order": 4,
        },
    )
    empty_group_list_message: str = Field(
        default="白名单已启用，但群组列表为空，请联系管理员添加。",
        description="白名单启用但群组列表为空时的提示信息",
        json_schema_extra={
            "label": "群组列表为空提示",
            "hint": "白名单启用但群组白名单列表为空时，向群聊发送的提示信息。",
            "order": 5,
        },
    )
    empty_private_list_message: str = Field(
        default="白名单已启用，但私聊白名单为空，请联系管理员添加。",
        description="白名单启用但私聊列表为空时的提示信息",
        json_schema_extra={
            "label": "私聊列表为空提示",
            "hint": "白名单启用但私聊白名单列表为空时，向私聊用户发送的提示信息。",
            "order": 6,
        },
    )


class BlacklistConfig(PluginConfigBase):
    """黑名单配置 — 禁止指定群组或用户使用插件。"""

    __ui_label__ = "访问黑名单"
    __ui_icon__ = "ban"
    __ui_order__ = 3

    enabled: bool = Field(
        default=False,
        description="是否启用黑名单（关闭后不拦截任何用户）",
        json_schema_extra={
            "label": "启用黑名单",
            "hint": "开启后将禁止黑名单中的群组和用户使用插件。",
            "order": 0,
        },
    )
    group_ids: list[str] = Field(
        default_factory=list,
        description="群组黑名单列表（在此填写禁止使用插件的群号，每行一个）",
        json_schema_extra={
            "label": "群组黑名单",
            "hint": "在此填写禁止使用插件的群号，每行填写一个群号。",
            "order": 1,
        },
    )
    user_ids: list[str] = Field(
        default_factory=list,
        description="用户黑名单列表（在此填写禁止使用插件的用户 QQ 号，每行一个）",
        json_schema_extra={
            "label": "用户黑名单",
            "hint": "在此填写禁止使用插件的用户 QQ 号，每行填写一个 QQ 号。",
            "order": 2,
        },
    )

    # ---- 黑名单拒绝提示（可自定义） ----
    group_deny_message: str = Field(
        default="你所在的群组已被加入黑名单，无法使用后室:逃出生天插件。",
        description="群组被黑名单拦截时显示的提示信息",
        json_schema_extra={
            "label": "群组拒绝提示",
            "hint": "当群组在黑名单中时，向该群发送的拒绝提示信息。",
            "order": 3,
        },
    )
    private_deny_message: str = Field(
        default="你已被加入黑名单，无法使用后室:逃出生天插件。",
        description="用户被黑名单拦截时显示的提示信息",
        json_schema_extra={
            "label": "私聊拒绝提示",
            "hint": "当用户或私聊群组在黑名单中时，向该用户发送的拒绝提示信息。",
            "order": 4,
        },
    )


class BackroomsGameConfig(PluginConfigBase):
    """后室:逃出生天插件完整配置。"""

    plugin: PluginSectionConfig = Field(default_factory=PluginSectionConfig)
    game: GameConfig = Field(default_factory=GameConfig)
    whitelist: WhitelistConfig = Field(default_factory=WhitelistConfig)
    blacklist: BlacklistConfig = Field(default_factory=BlacklistConfig)
