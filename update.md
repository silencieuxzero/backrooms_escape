> **说明**：版本号与 [`_manifest.json`](_manifest.json) 中的 `version` 字段保持同步，更新版本时两者需一起修改。

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
