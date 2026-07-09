> **说明**：版本号与 [`_manifest.json`](_manifest.json) 中的 `version` 字段保持同步，更新版本时两者需一起修改。

## v1.1.1 (2026-07-09)

### 新增
- **新角色「白宇」**：28岁，前 M.E.G.CN 外勤勘探员，沉默寡言的独行流浪者，在 **Level 2** 管道迷宫中出现。见面礼：手电筒
- **新角色「Luna」（陆遥）**：26岁，后室现象独立研究员，曾在意大利留学。在 **Level 1** Alpha 基地通讯室中出现。见面礼：镇定剂
- **新角色「洛疏律」**：24岁，M.E.G.CN 信息系统管理员，戴黑框眼镜的务实派技术员。在 **Level 1** Alpha 基地数据中心中出现。见面礼：能量棒
- **对话系统**：`/br said <角色名>` 进入自由对话模式，通过麦麦 LLM 实时生成角色回复，角色卡作为临时 system prompt
- `people_relationship.json` 新增 `personality`（性格）字段，共 5 个角色
- `CHARACTERS` 注册表新增 `level` 字段，支持角色在不同楼层出现
- 状态机新增 `DIALOG` 状态及 `ENTER_DIALOG` / `END_DIALOG` 事件
- `PlayerState` 新增 `dialog_history` 字段，保存 LLM 对话历史

### 变更
- 全局用语统一："层级" → "楼层"（涉及 12 个文件共 36 处）
- 角色遭遇系统从硬编码 Level 1 改为按角色 `level` 字段动态筛选
- `/br said`、`/br invite`、`/br gift` 命令提示列表同步更新
- 合并转发模式优化：游戏事件消息拆分为三段（当前事件 + 人物状态 + 可用命令）合并发送
- 项目结构文档、README、webreadme 同步更新

### 修复
- 修复 `_do_said` 缺少 `_save_player` 调用导致对话状态不持久化的问题
- 修复对话模式中 `dialog_node_id` 默认值不一致的问题
- 删除 `render_start_nodes()` 死代码 41 行
- 修复 `renderer.py` 中 5 处硬编码角色名映射（`render_status`、`render_explore`、`render_exit_found`、`render_level399_escape`），改为从 `CHARACTERS` 注册表动态获取，新增角色无需再手动修改
- 新增 baiyu、luna、luo_shulv 三种角色的同伴探索台词（各 4 条）和出口台词
- 修复角色遭遇 header 硬编码（`if char_id == "ankexin"`），改为动态显示楼层和角色名
- 修复 `plugin.py` 中 4 处 Level 1 硬编码提示（`_do_invite`、`_do_dismiss`、`_do_gift`），改为根据角色 `level` 字段动态生成

## v1.1.0 (2026-07-09)

### 重构
- 项目结构重组：新建 `renderer_load/` 拓展模块目录，`shut.py`、`story_manage.py`、`people_manage.py` 等拓展模块移入其中
- `renderer.py` 成为拓展模块的统一加载入口，所有 `renderer_load/` 下的模块通过 `renderer.py` 透出
- `plugin.py` 不再直接引用 `story_manage` 和 `shut` 模块，改为全部从 `renderer` 导入
- 新增 `.gitignore`，排除 `__pycache__/`、`br_data/`、`*.log`、IDE 配置等不应进入仓库的文件
- 新建 `br_story/` 故事集中目录，`level_story/`、`people_story/`、`base_story/` 三个故事文件夹移入其中
- 废弃 `config_other/` 目录，其中的 `base_work.json` 移至 `br_story/base_story/`、`people_quests.json` 和 `people_relationship.json` 移至 `br_story/people_story/`，相关加载路径同步更新
- 版本号统一更新至 `1.1.0`

### 新增
- 引入有限状态机（FSM）：新建 `renderer_load/state_machine.py`，定义 `GameState`（5 个状态）、`GameEvent`（7 个事件）、`GameStateMachine` 类
- 角色系统模块化：新建 `renderer_load/people_manage.py`，包含 `Character` 注册表 + `CharacterEncounterService`
- `renderer_load/people.py` → `people_manage.py`，`renderer_load/story.py` → `story_manage.py`，模块名统一加 `_manage` 后缀
- **好感度系统**：角色遭遇时自动增加好感度，`/br status` 和 `/br people_net` 面板可查看
- **同行系统**：好感度达到阈值（默认70）后可用 `/br invite <角色名>` 邀请角色同行，同行时出口率 +5%，探索时触发同伴互动台词
- **赠礼系统**：使用 `/br gift <角色名> <物品编号>` 可将背包物品赠送给角色提升好感度，不同物品增加的好感度可在配置文件中自定义
- 配置文件新增 `favorability_threshold`（邀请阈值）、`favorability_per_encounter`（单次遭遇好感度）和 `gift_favorability_values`（赠礼好感度映射）

### 变更
- `PlayerState.game_started: bool` 替换为 `fsm: GameStateMachine`，状态机管理游戏核心流程而非布尔标志
- 全部 22 处 `game_started` 引用更新为 `fsm.is_playable()` / `fsm.apply()` 调用
- 存档字段 `game_started` → `state`，`GameStateMachine.from_dict()` 恢复状态
- 角色遭遇逻辑从 `plugin.py._do_explore` 中抽离至 `CharacterEncounterService`，消除重复的杏仁水硬编码和角色 ID 硬编码；新增角色只需在 `CHARACTERS` 注册表中添加记录 + 创建剧情文件
- 移除 `_maybe_ankexin_task` 方法（功能已合并到 `CharacterEncounterService`）

### 修复
- 修复 `handle_read` 早期返回签名不匹配：裸 `return` → `return True, "未开始游戏", 1`
- 修复 `__pycache__` 被 git 跟踪的问题：从索引中移除，确保 `.gitignore` 规则生效
- 修复 `/br invite`、`/br dismiss` 缺少 `_save_player` 导致同行状态不持久化的问题
- 修复 `pending_quest_offer` 在无任务发放时不清除旧值导致残留过期任务 ID
- 修复 `CHARACTERS` 未导入 `plugin.py` 导致 `/br invite`、`/br gift`、`/br dismiss` 必崩 `NameError`
- 修复 `_do_explore` 未传递 `favorability_per_encounter` 参数导致好感度无法累加
- 修复 Level 11 捷径通关显示 "12 个楼层" 的文本错误，统一传入 `399`
- 移除 `FAVORABILITY_PER_ENCOUNTER` 常量死代码（已定义但未被引用）
- 为 `base_exit_chance` 和 `exit_chance_increment` 添加 `ge=0.0, le=1.0` 范围校验，防止非法配置

## v1.0.9 (2026-06-20)

### 新增
- `/br shut` 命令：管理员可静默群聊，静默后群内非 `/br` 消息不会触发 Planner/LLM 处理
- `shut.py` 模块：ShutManager 管理静默群组列表，持久化到 `br_data/shut_groups.json`

### 变更
- 管理员系统重构：`admin_id` 改为 `admin_ids` 列表，支持多位管理员
- 管理员只能通过修改 `config.toml` 来增减，无法通过命令自任命
- 版本号统一更新至 `1.0.9`

### 修复
- 修复 `render_exit_found` 使用错误楼层信息显示搜索消息的 bug：找到出口后 `ctx.level_info` 已指向新楼层，导致"你仔细搜索着 XXX 的每一个角落……"显示的楼层名与实际不符
- 移除 `_get_or_create_player` 死代码（定义但从未被调用）

## v1.0.8 (2026-06-20)

### 新增
- 任务系统：5 个安可欣发布的任务（探索取证、收集物品、提交物资），完成可获 M.E.G.CN 贡献点
- `/br quest` 命令：查看任务面板 / 接受任务 / 提交任务
- M.E.G.CN 贡献点系统：在状态面板和任务面板中显示
- 到达新楼层自动检测任务进度，达标时提示提交
- 基地工作系统：5 个基于高中自然地理的解谜工作，完成获得贡献点并解锁故事
- `/br work` 命令：查看工作面板 / 开始工作 / 提交答案
- `base_story/` 目录：存放工作完成后解锁的故事事件文件
- `BaseWorkStoryManager`：自动加载 base_story/ 下的故事
- `/br story` 改为故事档案面板：查看已解锁的工作故事，使用 `/br story <ID>` 以合并转发消息查看

### 变更
- Level 1 遇到安可欣时有概率接到任务
- Level 1 探索时刷新可用工作列表
- 存档新增 `currency`、`active_quests`、`completed_quests`、`pending_quest_offer`、`available_works`、`completed_works`、`work_stories` 字段
- 版本号统一更新至 `1.0.8`

## v1.0.7 (2026-06-20)

### 变更
- 人物数据由 `people_relationship.txt` 改为 `people_relationship.json` 结构化存储
- `/br people_net` 渲染器改为直接解析 JSON 数据，输出格式化人物卡
- 版本号统一更新至 `1.0.7`

## v1.0.6 (2026-06-20)

### 变更
- 物品与实体数据迁移至 `backrooms_data.json` 集中管理，插件从 JSON 文件动态加载
- 恢复 `/br use <编号>` 命令使用物品，`/br inventory` 仅查看背包
- 版本号统一更新至 `1.0.6`

## v1.0.5 (2026-06-20)

### 变更
- 物品使用命令改为 `/br inventory <编号>`，原有的 `/br use` 命令已移除
- 版本号统一更新至 `1.0.5`

## v1.0.4 (2026-06-20)

### 变更
- 物品使用改为按背包编号：`/br use <编号>`，使用后剩余物品自动向前补齐
- 新增 `admin_id` 配置项：可在 `config.toml` 中预配置管理员 QQ 号
- 版本号统一更新至 `1.0.4`

## v1.0.3 (2026-06-20)

### 新增
- 更新机制：插件启动时自动检测配置文件版本，旧版本自动迁移至最新
- 存档版本化：存档文件新增 `save_version` 字段，标识存档格式版本，便于后续兼容
- 存档自动迁移：加载旧版存档时自动补全版本号并适配当前格式，无需手动处理
- 配置热重载版本检测：`on_config_update` 时自动检查并迁移配置版本

### 变更
- `config_version` 统一调整为 `"1.0.3"`（与插件版本同步）
- `_manifest.json` 版本号更新至 `1.0.3`

## v1.0.2 (2026-06-20)

### 新增
- `/br say` 命令：随机输出一句名人名言
- `/br off` 命令：管理员关闭插件，关闭后仅管理员可用
- `/br on` 命令：管理员重新启用插件
- 首次遇到安可欣或安继年时，对方赠送 **2 瓶杏仁水**（自动收入背包，仅首次触发）

### 变更
- 补给品系统改为**物资箱系统**：探索时产生大、中、小三种物资箱，所有箱型**必出杏仁水**，同时附带一件随机物品
- 物资箱概率可在 `config.toml` 独立配置（`crate_large_chance`、`crate_medium_chance`、`crate_small_chance`）
- `supply_find_chance` 配置项废弃
- 手电筒驱散范围扩展：携带手电筒时同时可驱散**笑魇**与**猎犬**，使二者攻击无效化
- 寻找出口理智消耗从 10 点调整为 **5 点**
- 基础出口概率从 40% 调整为 **20%**
- Level 11 特殊出口：在 Level 11 找到出口后直接跳转至 **Level 399** 通关
- `/br teststory` 更名为 `/br story`
- `config_other/people_story.txt` 重命名为 `people_relationship.txt`，删去独立人物关系区块，关系信息嵌入各自人物卡

### 修复
- 修复故事纸条无法加载的 bug：`story.py` 路径解析改用 `Path(__file__).parent`，移除 `os.path` 相对路径依赖

## v1.0.1 (2026-06-19)

### 新增
- 输出模式配置：`config.toml` 新增 `output_mode` 字段，支持 `"text"`（普通消息）和 `"forward"`（合并转发消息）两种模式
- `_send()` 辅助方法：所有游戏消息统一通过该方法发送，自动根据配置选择模式
- 防 planner 钩子：`br_skip_planner` 确保命令处理后不会进入 LLM/Planner 处理链
- 人物剧情系统：`people_story/` 目录，可加载自定义角色剧情文件（`===CHARACTER_NNN===` 分隔）
- Level 1 Alpha 基地特殊事件：40% 概率在探索时遇到角色（安可欣、安继年）
- `/br people_net` 命令：查看已解锁人物关系图（数据来自 `config_other/people_relationship.txt`）
- `config_other/people_relationship.txt`：人物关系配置文件，记录安可欣与安继年的姐弟关系
- 角色解锁系统：遭遇角色后自动解锁，仅已解锁角色会显示在人物关系图中
- 存档系统新增 `unlocked_chars` 字段，角色解锁状态持久化到 JSON
- 消息回复渲染器 (`renderer.py`)：将消息格式化逻辑从 `plugin.py` 解耦，使用 `RenderContext` 封装渲染上下文
- 多文件故事系统：`level_story/` 目录下新增 `l2~l11_story.txt` 共 10 个楼层主题故事文件（共 25 条新故事），`story.py` 自动匹配 `l*_story.txt` 模式加载
- README 新增安装说明
- `update.md` 更新日志文件

### 变更
- 命令拦截等级调整为 `1`（兼顾防 LLM 处理与消息去重）
- 白名单默认关闭（`enabled = false`），安装后所有用户可直接使用，无需手动配置
- 每次探索消耗理智值从 5 点调整为 **2 点**
- 安可欣、安继年剧情文本根据人物关系全面重写
  - 调整为 22 岁龙凤胎姐弟设定，互称"安安"/"可欣"
  - 安可欣全篇融入对弟弟的提及（搜救、暖泉区、工作锚点等）
  - 安继年全篇使用"可欣"称呼，去除不符设定的表述
- `config_other/people_relationship.txt` 补充年龄信息、关系更新为"龙凤胎姐弟"
- 插件名称统一改为"后室:逃出生天"（涉及 6 个文件共 19 处）
- `_manifest.json` 格式对齐标准规范，移除 `plugin_type`、`display` 等非标准字段
- `README.md` 精简为 96 行，原完整版另存为 `webreadme.md`
- `/br start` 改为合并转发消息发送

### 修复
- 修复 `/br start` 消息输出模式切换：当 `output_mode = "forward"` 时仍使用 3 节点合并转发
- 探索时补给箱空箱现在会显示"……但里面已经空了"
- 捡到纸条不再出现重复文本

### 重构
- `plugin.py` 中所有 `_do_*` 方法的消息构建逻辑迁移至 `renderer.py`
- `story.py` 故事文件统一收纳至 `level_story/` 子目录
