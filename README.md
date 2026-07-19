# 后室：逃出生天 (Backrooms Escape)

重要：由于本插件更新频繁，因此请以作者仓库中最新版本为准，麦麦仓库插件显示的版本可能会有滞后性。

本插件基于 MaiBot SDK + NapCat 适配器运行。本项目的代码基于 MIT 协议开源。

本插件未对snowluma进行适配，可能在该适配器下运行异常。若要使用本插件，请尽量使用napcat适配器。

由于作者水平有限，故使用了DeepSeek进行辅助开发，因而本插件的bug较多，但作者会尽快修复，当前还处于测试版本，请及时更新。

本插件较为复杂，且玩法较多，因此README文件仅包含核心功能说明。若想查看完整版README文件，请参考 `webreadme.md`。

## 安装

1. 将 `backrooms_escape` 文件夹放入 MaiBot 的 `plugins/` 目录下
2. 编辑 `config.toml`，若需限制访问范围，请在 `[whitelist]` 中添加你的群号和 QQ 号（白名单默认关闭）
3. 在 MaiBot WebUI 中加载插件，或重启 MaiBot

```toml
[whitelist]
enabled = true
group_ids = ["你的群号"]
user_ids = ["你的QQ号"]
```

## 输出模式

可在 `config.toml` 的 `[plugin]` 段中设置消息输出模式：

```toml
[plugin]
output_mode = "text"      # 普通文本消息（兼容性更好）
# output_mode = "forward" # 合并转发消息（更美观，但仅支持napcat适配器）
```

- `text`：所有游戏回复以普通文本形式发送
- `forward`：所有游戏回复以合并转发消息形式发送

## 快速上手

发送 `/br test` 验证插件，回复正常后使用 `/br start` 开始游戏。

```
/br start     → 从 Level 0 出发
/br explore   → 探索楼层（搜集物品、遇敌、捡纸条）
/br exit      → 寻找出口（切入下一层）
/br status    → 查看状态与背包
/br help      → 查看所有命令
```

重复 explore → exit 循环直到抵达 Level 399 通关。

## 命令列表

| 命令 | 说明 |
|------|------|
| `/br test` | 测试插件连通性 |
| `/br story` | 查看后室背景故事（合并转发消息） |
| `/br start` | 开始新游戏 |
| `/br explore` | 探索当前楼层 |
| `/br exit` | 尝试寻找出口 |
| `/br exit l<N>` | 回溯到已访问过的指定楼层，如 `/br exit l1` 回到 Level 1 |
| `/br read` | 阅读捡到的纸条（合并转发消息） |
| `/br use <编号>` | 使用物品，如 `/br use 1` |
| `/br status` | 查看探员状态 |
| `/br inventory` | 查看背包 |
| `/br invite <角色名>` | 邀请好感度达标的角色同行 |
| `/br dismiss` | 让同行角色返回基地 |
| `/br gift <角色名> <编号>` | 赠送物品给角色提升好感度 |
| `/br said <角色名>` | 与指定角色进行自由对话（LLM 驱动） |
| `/br say <对话内容>` | 在对话模式下向角色发送消息 |
| `/br explore base` | 在 Alpha 基地内探索，遇到角色后才解锁 |
| `/br help` | 查看所有命令 |

## 游戏机制

- **生命值**：初始 100，归零则死亡。通过急救包/能量棒恢复。
- **理智值**：初始 100，探索消耗 2 点、找出口消耗 5 点。通过杏仁水/镇定剂恢复。归零额外扣血。
- **出口概率**：基础 20%，每次失败 +10%。楼层钥匙 100% 成功，手电筒/无线电各 +5%，同行角色额外 +5%。
- **捷径**：12% 概率跳过 2~20 个楼层。
- **知名楼层**：Level 0~11、Level 399 有专属描述和实体；其余楼层程序化生成。
- **好感度系统**：在 Level 1 与安可欣/安继年/Luna/洛疏律互动，在 Level 2 与白宇互动，可累计好感度，达到阈值后可邀请同行探索。同行角色提供出口率 +5% 加成，并触发专属互动台词。使用 `/br said <角色名>` 可与已解锁的角色进行 LLM 驱动的自由对话。
- **赠礼系统**：可将背包物品赠送给角色以提升好感度，不同物品增加的好感度可在配置文件中自定义。

## 物品

| 代码 | 名称 | 效果 |
|------|------|------|
| o1 | 杏仁水 | 恢复 30 理智 |
| o2 | 急救包 | 恢复 30 生命，受伤时自动减伤 5 |
| o3 | 手电筒 | 驱散笑魇和猎犬，其他实体减伤 10，+5% 出口率 |
| o4 | 楼层钥匙 | 100% 找到出口（稀有） |
| o5 | M.E.G.CN 无线电 | +5% 出口率 |
| o6 | 能量棒 | 恢复 15 生命 |
| o7 | 镇定剂 | 恢复 15 理智 |

探索时（Level 0 除外）有概率发现大/中/小物资箱，所有箱型必出杏仁水，各物品按权重随机分配。权重及箱型概率可在 `config.toml` 中调整。

## 实体

探索中可能遭遇实体并损失生命值。携带手电筒可减轻伤害，笑魇和猎犬会被完全驱散。

笑魇(15)、猎犬(20)、窃皮者(25)、死亡飞蛾(10)、旅馆管理者(30)、深海之物(35)、以及其他楼层专属实体。

## 配置

在 `config.toml` 中调整游戏参数和访问控制。

### 白名单（默认关闭）

白名单默认关闭，此时所有用户均可使用插件。若需限制访问，设置 `enabled = true` 并填入群号和 QQ 号。

```toml
[whitelist]
enabled = true
group_ids = ["你的群号"]
user_ids = ["你的QQ号"]
```

### 黑名单

禁止指定群组/用户使用，优先级高于白名单。默认关闭。

### 游戏参数

生命/理智初始值、消耗量、出口基础概率、实体遭遇概率、物资箱概率、各物品权重、好感度参数等均可在 `[game]` 段调整。新增好感度相关配置：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `favorability_threshold` | 70 | 邀请角色同行所需的最低好感度 |
| `favorability_per_encounter` | 2 | 每次遭遇角色时自动增加的好感度 |
| `gift_favorability_values` | 见配置 | 赠礼好感度映射，键为物品代码（如 `o4`），值为增加的好感度 |

## 存档

游戏进度自动保存到 `br_data/` 目录，每个玩家对应一个 JSON 文件。插件重载或 MaiBot 重启不会丢失进度。死亡或通关后存档自动删除。

## 自定义故事

探索时可捡到背景故事纸条，也可在 Level 1 遇到 NPC 角色（首次赠送 2 瓶杏仁水）。编辑 `l1_story.txt` 即可自定义内容。格式为 `===STORY_NNN===` 分隔的 UTF-8 文本段，修改后重载插件生效。

## 项目结构

```
backrooms_escape/
├── plugin.py                  # 插件主入口 — 命令注册、Hook、生命周期（~570行）
├── renderer.py                # 向后兼容层（透出各层公开符号）
├── config.py / config.toml    # Pydantic 配置模型 + 运行时配置
│
├── core/                      # 核心游戏逻辑层
│   ├── state_machine.py       #   有限状态机（GameStateMachine）
│   ├── player_state.py        #   PlayerState 数据类
│   ├── game_data.py           #   游戏静态数据 + GameDataService
│   ├── exploration.py         #   ExplorationService（探索逻辑）
│   └── exit_handler.py        #   ExitService（出口/回溯逻辑）
│
├── handlers/                  # 命令处理混入层（_do_* 方法按功能拆分）
│   ├── base.py                #   HandlerBase — 共享工具方法
│   ├── game_commands.py       #   GameCommandMixin — 开始/探索/使用物品
│   ├── exit_commands.py       #   ExitCommandMixin — 出口搜索/楼层回溯
│   ├── player_commands.py     #   PlayerCommandMixin — 查看状态/背包/帮助
│   ├── story_commands.py      #   StoryCommandMixin — 故事档案
│   ├── quest_commands.py      #   QuestCommandMixin — 任务系统
│   ├── work_commands.py       #   WorkCommandMixin — 基地工作
│   ├── character_commands.py  #   CharacterCommandMixin — 关系图/LLM对话
│   ├── companion_commands.py  #   CompanionCommandMixin — 同伴同行/赠礼
│   └── admin_commands.py      #   AdminCommandMixin — 管理员命令
│
├── hooks/                     # Hook 处理器
│   ├── access_control.py      #   黑白名单 + 插件禁用检查
│   └── message_hooks.py       #   Planner 跳过 / 对话拦截 / 静默检查
│
├── rendering/                 # 渲染层（纯函数，无副作用）
│   ├── renderer.py            #   BackroomsRenderer（所有消息格式化）
│   ├── context.py             #   RenderContext（渲染参数容器）
│   └── companion_script.py    #   同伴台词（独立维护）
│
├── story_load/                # 故事与角色数据管理
│   ├── people_manage.py       #   CHARACTERS 注册表 + CharacterEncounterService
│   ├── story_manage.py        #   QuestManager / WorkManager / StoryManager
│   ├── dialogue_manage.py     #   LLM 对话系统
│   ├── shut.py                #   ShutManager（群聊静默）
│   └── backrooms_data.json    #   物品/实体数据
│
├── persistence/               # 持久化层
│   └── save_manager.py        #   SaveManager（存档 CRUD + 迁移）
│
├── br_story/                  # 故事内容数据
│   ├── people_story/          #   角色剧情 .txt + 任务/关系 JSON
│   ├── level_story/           #   楼层剧情 l1~l11_story.txt
│   └── base_story/            #   基地工作解谜 + 解锁故事
│
└── br_data/                   # 玩家存档（自动创建）
```

### 模块依赖

```
plugin.py
  ├── handlers/       (命令 _do_* 方法，按功能领域拆分为混入类)
  │     └── handlers/base.py  (共享工具方法)
  ├── hooks/          (Hook 处理逻辑)
  ├── core/           (GameState, PlayerState, GameDataService, ...)
  ├── rendering/      (BackroomsRenderer, RenderContext, companion_lines)
  │     └── story_load/  (via rendering/__init__.py)
  ├── persistence/    (SaveManager)
  └── config.py
```

> 状态机定义在 `core/state_machine.py` 中（单一数据源），`story_load/` 从此处导入。

## 状态机

插件使用**有限状态机（FSM）** 管理游戏核心流程，定义在 [core/state_machine.py](file:///e:/yuzhu_backrooms/backrooms_escape/core/state_machine.py) 中。

### 状态定义

| 状态 | 含义 | 可执行操作 |
|------|------|-----------|
| `NOT_STARTED` | 未开始游戏 | `/br start` |
| `ALIVE` | 存活探索中（Level 0~398） | 全部命令 |
| `AT_399` | 到达最终出口 | `/br exit`（触发通关） |
| `DIALOG` | 对话模式 | `/br said`（选择选项或输入文本） |
| `DEAD` | 生命值归零 | `/br start` 重新开始 |
| `ESCAPED` | 成功逃出后室 | `/br start` 重新开始 |

### 状态转移图

```
NOT_STARTED ──start──▶ ALIVE ──reach_399──▶ AT_399 ──exit_399──▶ ESCAPED
                         │  │                                           │
                         │  ├──enter_dialog──▶ DIALOG ──end_dialog──▶   │
                         │  │                                           │
                         │ die                                           │ restart
                         ▼                                              │
                       DEAD ◀────────────────────────────────────────────┘
                         │
                         └── restart ──▶ ALIVE
```

ALIVE 状态下 `explore`、`exit`、`use_item` 等事件不会改变状态，但可能触发 `die`（生命归零时）或 `reach_399`（到达 Level 399 时）进入新状态。

### 代码使用

```python
from .core import GameState, GameEvent, GameStateMachine

# 创建状态机
fsm = GameStateMachine()  # 初始为 NOT_STARTED

# 查询
fsm.is_playable()    # True/False — 当前能否执行游戏操作
fsm.can(GameEvent.EXPLORE)   # True/False — 特定事件是否允许
fsm.state            # 当前状态 (GameState 枚举)

# 转移
fsm.apply(GameEvent.START)   # NOT_STARTED → ALIVE
fsm.apply(GameEvent.DIE)     # ALIVE → DEAD

# 序列化
data = fsm.to_dict()              # → {"state": "ALIVE"}
fsm2 = GameStateMachine.from_dict(data)  # 从存档恢复
```

### 在 PlayerState 中使用

```python
@dataclass
class PlayerState:
    fsm: GameStateMachine = field(default_factory=GameStateMachine)
    # ... 其他字段

# 守卫检查（替代旧的 game_started 判断）
if not player.fsm.is_playable():
    # 拒绝操作
```

> 状态机消除了散落在各命令处理器中的 `if game_started` 隐式状态判断，将游戏流程显式化为一张可读的转移表，非法操作自然被拦截，不再需要手写 `if-else`。
