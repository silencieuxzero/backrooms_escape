# AGENTS.md — 后室:逃出生天

AI 协作开发指引。阅读本文档可快速了解项目架构、开发约束和常见操作规范。

## 1. 项目概述

MaiBot 文字冒险插件。玩家扮演 M.E.G.CN 工作人员，从 Level 0 出发探索后室，寻找出口逐层深入，直至 Level 399 最终出口。
核心循环：探索 → 遭遇角色/事件 → 寻找出口 → 切入下一楼层。

## 2. 版本号（必须同步）

以下 4 处版本号必须保持一致：

- `_manifest.json` → `version`
- `plugin.py` → `PLUGIN_VERSION`、`SAVE_VERSION`
- `config.toml` → `config_version`
- `update.md` → 顶部最新版本区块

发版流程：先同步 4 处版本号，再在 `update.md` 顶部追加变更记录。

## 3. 架构总览

```
backrooms_escape/
├── plugin.py                   # 主入口：命令注册、Hook、生命周期（~570行）
├── config.py / config.toml     # Pydantic 配置模型 + 运行时配置
├── _manifest.json              # 插件清单
├── update.md                   # 版本更新日志
├── renderer.py                 # 向后兼容层（透出 rendering/ 和 story_load/ 的公开符号）
│
├── core/                       # 核心游戏逻辑层
│   ├── __init__.py             # 透出所有核心类型
│   ├── state_machine.py        # GameState / GameEvent / GameStateMachine
│   ├── player_state.py         # PlayerState 数据类
│   ├── game_data.py            # 静态数据（楼层/事件/捷径）+ 物品加载 + GameDataService
│   ├── exploration.py          # ExplorationService（楼层/基地探索）
│   └── exit_handler.py         # ExitService（出口搜索/楼层回溯）
│
├── handlers/                   # 命令处理混入层（将 _do_* 方法按功能领域拆分）
│   ├── __init__.py             # 统一导出所有混入类
│   ├── base.py                 # HandlerBase — 共享工具方法（消息解析/发送/物品管理）
│   ├── game_commands.py        # GameCommandMixin — 游戏流程（开始/探索/使用物品）
│   ├── exit_commands.py        # ExitCommandMixin — 出口搜索与楼层回溯
│   ├── player_commands.py      # PlayerCommandMixin — 玩家状态（查看/背包/帮助）
│   ├── story_commands.py       # StoryCommandMixin — 故事档案
│   ├── quest_commands.py       # QuestCommandMixin — 任务系统
│   ├── work_commands.py        # WorkCommandMixin — 基地工作
│   ├── character_commands.py   # CharacterCommandMixin — 角色交互（关系图/LLM对话）
│   ├── companion_commands.py   # CompanionCommandMixin — 同伴同行与赠礼
│   └── admin_commands.py       # AdminCommandMixin — 管理员命令
│
├── hooks/                      # Hook 处理器（访问控制/消息拦截）
│   ├── __init__.py             # 统一导出
│   ├── access_control.py       # 黑白名单 + 插件禁用检查
│   └── message_hooks.py        # Planner 跳过 / 对话拦截 / 静默检查
│
├── rendering/                  # 渲染层（纯函数，无副作用）
│   ├── __init__.py             # 统一导出 + 透出 story_load 模块
│   ├── context.py              # RenderContext（渲染参数容器）
│   ├── renderer.py             # BackroomsRenderer（所有消息格式化）
│   └── companion_script.py     # companion_lines / companion_exit_lines
│
├── story_load/                 # 故事与角色数据管理
│   ├── __init__.py             # 透出所有子模块
│   ├── people_manage.py        # CHARACTERS 注册表、角色遭遇、赠礼、好感度
│   ├── story_manage.py         # QuestManager / WorkManager / StoryManager / PeopleStoryManager
│   ├── dialogue_manage.py      # LLM 对话（system prompt / 历史管理 / CoT 剥离）
│   ├── shut.py                 # ShutManager（群聊静默）
│   └── backrooms_data.json     # 物品与实体数据
│
├── persistence/                # 持久化层
│   ├── __init__.py
│   └── save_manager.py         # SaveManager（存档 CRUD + 迁移）
│
└── br_story/                   # 故事内容数据
    ├── people_story/           # 角色剧情 .txt + people_relationship.json + people_quests.json
    ├── level_story/            # 楼层剧情 l1_story.txt ~ l11_story.txt
    └── base_story/             # base_work.json + work_W*.txt（工作解锁故事）
```

### 模块依赖关系

```
plugin.py
  ├── handlers/       (命令 _do_* 方法，按功能领域拆分为混入类)
  │     └── handlers/base.py  (共享工具方法)
  ├── hooks/          (Hook 处理逻辑)
  ├── core/           (GameState, PlayerState, GameDataService, ExplorationService, ExitService)
  ├── rendering/      (BackroomsRenderer, RenderContext, companion_lines)
  │     └── story_load/  (via rendering/__init__.py)
  ├── persistence/    (SaveManager)
  └── config.py
```

**层级原则**：
- `plugin.py` 是唯一的编排层，负责命令注册和 SDK 交互，通过多重继承组合 handlers/ 中的混入类。
- `handlers/` 为命令处理混入层，每个文件专注于一类游戏功能的 ``_do_*`` 实现。
- `hooks/` 为 Hook 处理层，以独立函数形式实现，通过 ``plugin.py`` 委托调用。
- `core/` 为纯业务逻辑层，不依赖 SDK，通过 `plugin_ref` 访问配置/日志。
- `rendering/` 为纯函数渲染层，不依赖 SDK、无副作用、不访问网络。
- `story_load/` 为静态数据管理层，管理故事文本、角色注册表等。
- `persistence/` 为存档读写层，封装序列化/反序列化/迁移逻辑。
- `br_story/` 为只读内容文件，供 `story_load/` 的子模块加载。

### 导入规则

- `plugin.py` 从 `handlers/`、`hooks/`、`core/`、`rendering/`、`persistence/` 直接导入。
- `handlers/` 中的混入类从 `core/`、`rendering/` 导入，不依赖 SDK。
- `hooks/` 中的处理函数接收 ``plugin`` 实例作为参数，不做模块级导入。
- `story_load/` 中无 SDK 依赖的模块（如 `people_manage.py`）保持独立。
- `story_load/__init__.py` 从 `..core.state_machine` 导入状态机类型（单一数据源）。
- `renderer.py` 保留为向后兼容的重新导出入口。
- 所有路径使用 `pathlib.Path`，禁止 `os.path` 和硬编码相对路径。

**参考文档**：
- [麦麦插件开发文档](https://docs.mai-mai.org/plugin/)
- [麦麦本体开发指南](https://docs.mai-mai.org/develop/)

## 4. 角色系统

### CHARACTERS 注册表（唯一数据源）

定义文件：`story_load/people_manage.py`

新增角色完整流程：
1. 在 `CHARACTERS` 注册一条记录（`char_id` 须与剧情文件名一致）。
2. 在 `br_story/people_story/` 下创建 `<char_id>.txt`。
3. 在 `br_story/people_story/people_relationship.json` 补充角色卡。
4. 在 `rendering/companion_script.py` 的 `companion_lines` 和 `companion_exit_lines` 补齐同伴台词。

### 角色名映射

角色名一律从 `CHARACTERS` 注册表动态获取，禁止新增硬编码映射字典：

```python
char_name = CHARACTERS.get(char_id, {}).get("name", char_id)
```

## 5. 渲染器约定

`BackroomsRenderer` 的所有方法均为纯函数：接收数据，返回字符串，不依赖 SDK、无副作用、不访问网络。

- `companion_lines`：探索时同伴的随机台词（字典）。定义文件：`rendering/companion_script.py`。
- `companion_exit_lines`：找到出口时同伴的台词（字典，值为 `lambda n -> str`）。定义文件：`rendering/companion_script.py`。
- 两个字典的键集必须覆盖 `CHARACTERS` 中所有角色。

## 6. 状态机

`GameStateMachine` 是核心流程控制器，所有命令处理器须通过 `fsm.can(GameEvent)` 校验操作合法性。
定义文件：`core/state_machine.py`（单一数据源）。

| 当前状态 | 允许的事件 |
|----------|-----------|
| `NOT_STARTED` | `START` |
| `ALIVE` | `EXPLORE` / `EXIT` / `USE_ITEM` / `ENTER_DIALOG` |
| `DIALOG` | `END_DIALOG` |
| `AT_399` | `EXIT_399` |
| `DEAD` / `ESCAPED` | `RESTART` |

新增命令时，先评估是否需要扩展 `GameEvent` 及 `_TRANSITIONS` 表。

## 7. LLM 对话系统

- 通过 `dialog_model` 指定模型，`llm.generate` 直连，绕过 Planner。
- system prompt 由 `build_system_prompt()` 根据 `people_relationship.json` 动态构建。
- 对话历史最多保留 `MAX_HISTORY_ROUNDS` 轮（6 轮 = 12 条消息）。
- LLM 回复须经 `strip_cot()` 剥离思维链后展示。

## 8. 存档与迁移

- `PlayerState` 以 JSON 存储，顶层含 `save_version` 字段（定义文件：`core/player_state.py`）。
- 持久化操作通过 `persistence/save_manager.py` 的 `SaveManager` 统一管理。
- 加载时对比 `save_version` 与 `SAVE_VERSION`，不一致则执行迁移。
- 配置加载时对比 `config_version` 与 `PLUGIN_VERSION`，不一致则自动迁移并回写 `config.toml`。

## 9. 游戏静态数据

- 楼层定义（ICONIC_LEVELS）、探索事件（EXPLORE_EVENTS）、捷径（SHORTCUT_POOL）集中在 `core/game_data.py`。
- 物品/实体数据通过 `backrooms_data.json` 加载，由 `core/game_data.py` 的 `load_items_pool()` 初始化。
- 楼层信息查询通过 `GameDataService.get_level_info()` 统一获取。

## 10. 常见任务速查

| 任务 | 关键文件 | 关键类/函数 |
|------|----------|-------------|
| 新增角色 | story_load/people_manage.py / br_story/people_story/ / rendering/companion_script.py | `CHARACTERS` / `companion_lines` |
| 新增任务 | br_story/people_story/people_quests.json / story_load/story_manage.py | `QuestManager` |
| 新增工作 | br_story/base_story/base_work.json / story_load/story_manage.py | `WorkManager` |
| 新增楼层故事 | br_story/level_story/l\<N\>_story.txt | `StoryManager` |
| 修改 LLM 提示词 | story_load/dialogue_manage.py | `build_system_prompt()` |
| 新增/修改命令 | plugin.py（@Command 注册） + handlers/ 对应混入类（_do_* 实现） | `@Command` / `*CommandMixin` |
| 新增/修改 Hook | plugin.py（@HookHandler 注册） + hooks/ 对应文件 | `@HookHandler` / hook 函数 |
| 修改状态规则 | core/state_machine.py | `_TRANSITIONS` |
| 修改探索逻辑 | core/exploration.py | `ExplorationService` |
| 修改出口逻辑 | core/exit_handler.py | `ExitService` |
| 修改游戏静态数据 | core/game_data.py | `ICONIC_LEVELS` / `GameDataService` |
| 修改渲染消息 | rendering/renderer.py | `BackroomsRenderer` |
| 修改存档格式 | persistence/save_manager.py | `SaveManager` |
| 修改访问控制 | hooks/access_control.py | `check_access_before_command` |
| 修改消息拦截 | hooks/message_hooks.py | `handle_dialog_message` / `check_shut_before_process` |

## 11. 约束

- 修改 `story_load/` 模块导出后，必须同步更新 `story_load/__init__.py` 的 `__all__` 和 `rendering/__init__.py` 的 `__all__`。
- 新增 `core/` 模块后，必须同步更新 `core/__init__.py` 的 `__all__`。
- 新增 `handlers/` 混入类后，必须同步更新 `handlers/__init__.py` 的 `__all__` 并在 `plugin.py` 的类继承中添加。
- 新增 `hooks/` 处理函数后，必须同步更新 `hooks/__init__.py` 的 `__all__` 并在 `plugin.py` 中注册对应的 `@HookHandler`。
- 楼层编号不得硬编码（如 `== 1`），应使用角色 `level` 字段或配置项。
- 不得删除 `update.md` 中的旧版本日志，仅在顶部追加。
- 路径拼接一律使用 `pathlib.Path`，禁止 `os.path`。
- `story_load/state_machine.py` 已删除，状态机类型统一从 `core/state_machine.py` 获取。
- `renderer.py` 是向后兼容层，新代码应直接从 `rendering/`、`story_load/`、`core/` 导入。
- 每个 `handlers/` 文件控制在 300 行以内，如需新增方法优先评估放入哪个现有混入类。
