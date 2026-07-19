"""后室:逃出生天 — Hook 处理器包

将插件 Hook 处理逻辑从 ``plugin.py`` 中提取为独立模块，
每个文件专注于一类 Hook 事件。

目录结构::

    hooks/
    ├── access_control.py    # 访问控制（黑/白名单 + 插件禁用检查）
    └── message_hooks.py     # 消息处理（Planner 跳过 / 对话拦截 / 静默检查）

所有 Hook 函数以独立函数形式实现，接收 ``plugin`` 实例作为第一个参数，
由 ``plugin.py`` 中的 ``@HookHandler`` 装饰器方法委托调用。
"""

from __future__ import annotations

from .access_control import check_access_before_command
from .message_hooks import skip_planner_after_command, handle_dialog_message, check_shut_before_process

__all__ = [
    "check_access_before_command",
    "skip_planner_after_command",
    "handle_dialog_message",
    "check_shut_before_process",
]
