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
├── plugin.py                   # 主入口：命令注册、状态机、存档、LLM 路由
├── renderer.py                 # 消息渲染器 + renderer_load 统一导入中心
├── config.py / config.toml     # Pydantic 配置模型 + 运行时配置
├── _manifest.json              # 插件清单
├── update.md                   # 版本更新日志
├── renderer_load/
│   ├── __init__.py             # 透出所有拓展模块
│   ├── people_manage.py        # CHARACTERS 注册表、角色遭遇、赠礼、好感度
│   ├── story_manage.py         # QuestManager / WorkManager / StoryManager
│   ├── state_machine.py        # GameState / GameEvent / GameStateMachine
│   ├── shut.py                 # ShutManager（群聊静默）
│   ├── dialogue_manage.py      # LLM 对话（system prompt / 历史管理 / CoT 剥离）
│   └── backrooms_data.json     # 物品与实体数据
└── br_story/
    ├── people_story/           # 角色剧情 .txt + people_relationship.json + people_quests.json
    ├── level_story/            # 楼层剧情 l1_story.txt ~ l11_story.txt
    └── base_story/             # base_work.json + work_W*.txt（工作解锁故事）
```

**核心原则**：
- `plugin.py` 仅通过 `renderer.py` 导入，禁止直接引用 `renderer_load.*`。
- 渲染逻辑集中在 `renderer.py`，游戏逻辑与呈现严格分离。
- 所有路径使用 `pathlib.Path`，禁止 `os.path` 和硬编码相对路径。

**参考文档**：
- [麦麦插件开发文档](https://docs.mai-mai.org/plugin/)
- [麦麦本体开发指南](https://docs.mai-mai.org/develop/)

## 4. 角色系统

### CHARACTERS 注册表（唯一数据源）

定义文件：`renderer_load/people_manage.py`

新增角色完整流程：
1. 在 `CHARACTERS` 注册一条记录（`char_id` 须与剧情文件名一致）。
2. 在 `br_story/people_story/` 下创建 `<char_id>.txt`。
3. 在 `br_story/people_story/people_relationship.json` 补充角色卡。
4. 在 `renderer.py` 的 `companion_lines` 和 `companion_exit_lines` 补齐同伴台词。

### 角色名映射

角色名一律从 `CHARACTERS` 注册表动态获取，禁止新增硬编码映射字典：

```python
char_name = CHARACTERS.get(char_id, {}).get("name", char_id)
```

## 5. 渲染器约定

`BackroomsRenderer` 的所有方法均为纯函数：接收数据，返回字符串，不依赖 SDK、无副作用、不访问网络。

- `companion_lines`：探索时同伴的随机台词（字典）。
- `companion_exit_lines`：找到出口时同伴的台词（字典，值为 `lambda n -> str`）。
- 两个字典的键集必须覆盖 `CHARACTERS` 中所有角色。

## 6. 状态机

`GameStateMachine` 是核心流程控制器，所有命令处理器须通过 `fsm.can(GameEvent)` 校验操作合法性。

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

- `PlayerState` 以 JSON 存储，顶层含 `save_version` 字段。
- 加载时对比 `save_version` 与 `SAVE_VERSION`，不一致则执行迁移。
- 配置加载时对比 `config_version` 与 `PLUGIN_VERSION`，不一致则自动迁移并回写 `config.toml`。

## 9. 常见任务速查

| 任务 | 关键文件 | 关键类/函数 |
|------|----------|-------------|
| 新增角色 | people_manage.py / people_story/ / people_relationship.json / renderer.py | `CHARACTERS` / `companion_lines` |
| 新增任务 | people_quests.json / renderer.py | `QuestManager` |
| 新增工作 | base_work.json / work_W*.txt / renderer.py | `WorkManager` / `BaseWorkStoryManager` |
| 新增楼层故事 | level_story/l\<N\>_story.txt | `StoryManager` |
| 修改 LLM 提示词 | dialogue_manage.py | `build_system_prompt()` |
| 修改命令 | plugin.py | `@Command` 装饰器方法 |
| 修改状态规则 | state_machine.py | `_TRANSITIONS` |

## 10. 约束

- 修改 `renderer_load/` 模块导出后，必须同步更新 `renderer.py` 的 `__all__`。
- 楼层编号不得硬编码（如 `== 1`），应使用角色 `level` 字段或配置项。
- 不得删除 `update.md` 中的旧版本日志，仅在顶部追加。
- 路径拼接一律使用 `pathlib.Path`，禁止 `os.path`。
