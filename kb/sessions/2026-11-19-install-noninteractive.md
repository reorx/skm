---
created: 2026-11-19
tags:
  - install
  - cli
  - non-interactive
  - prompts
---

# `skm install` 支持 `-y`，没有终端时所有提示自动取默认值

## 概要

上一个 session 用 `skm install --cmd "tinyhost skill"` 真实安装时，agent 勾选框会弹出来。用 `script` 模拟终端发回车，回车被提前吞掉，进程一直卡在勾选框，最后靠 `expect` 才装上。用 `--agents-includes claude,standard` 能跳过提示，但会把列表写死进 `skills.yaml`，以后改了 `agents.default` 也不会跟着变。所以脚本和 coding agent 没有办法得到"跟随默认 agent"的配置。这次做了两件事：
1. `install` 新增 `-y/--yes`，跳过 skill 和 agent 两个勾选框，取默认值：全部 skill、全部默认 agent，不保存 agent 过滤。`--cmd` 和直接安装 source 两条流程都支持。显式的 `--agents-includes/--agents-excludes` 仍然优先。
2. 没有终端时（stdin 不是 TTY）所有提示自动取默认值，不再等按键：勾选框返回预选项（默认全选），并用黄字打印选了什么；"目录已存在，是否覆盖"自动回答 N，并提示用 `--force`。

测试先写，新增 `tests/test_noninteractive.py` 共 12 条，实现前全部失败，实现后全量 319 passed。在隔离路径下用真实的 `tinyhost skill` 验收了三种情况：无终端不加 `-y`、加 `-y`、目标位置已有真实目录。验收产物在 `tmp/2026-11-19-noninteractive-install/`。

## 修改的文件

- `src/skm/tui.py`：新增 `has_terminal()`；`interactive_multi_select` 没有终端时直接返回预选项，并打印选择结果。
- `src/skm/commands/install.py`：`_confirm_override` 没有终端时回答 N，提示 `--force`。
- `src/skm/cli.py`：`install` 新增 `-y/--yes`，docstring 说明无终端行为；`_choose_agents_config` 和 `_install_cmd_source` 接收 `yes`；直接安装 source 时 `-y` 跳过 skill 勾选框。
- `tests/test_noninteractive.py`（新）：勾选框和覆盖确认在无终端下的行为，`--cmd` 和直接安装 source 两种流程分别在 `-y` 和无终端下的行为，已有目录不被覆盖。
- `README.md`：命令示例加 `-y`，补一段 `-y` 和无终端的说明；Dynamic skills 小节和命令表提到 `-y`。
- `AGENTS.md`：CLI Commands 加 `-y` 一行，新增 Non-interactive Runs 小节，测试列表加新文件。
- `kb/known-issues.md`：openclaw 硬链和同名 skill 两条里"非终端下报错"的描述，改成现在的"自动回答 N"。

## 注意事项

- **无终端检查放在提示函数内部，不在 `cli.py` 调用处。** 已有测试大量 monkeypatch `skm.cli.interactive_multi_select` 和 `_confirm_override`，而 `CliRunner` 的 stdin 永远不是 TTY。如果放在调用处，这些 mock 会被直接绕过，选择部分 skill 的测试就会失败。
- **无终端时的默认值不能有破坏性。** `-y` 和无终端都只是"取默认值"，不等于 `--force`：覆盖确认的默认答案是 N。
- 不加 mock 时，`CliRunner` 里的 `click.getchar()` 读到空字符串，原来的勾选框循环会一直转下去。测试里用 `no_keypress` fixture 把 `click.getchar` 换成直接抛异常，出了问题会立刻失败，不会卡住。
- 测试 `-y` 时要用 `no_picker` fixture，确认勾选框根本没被打开。否则在 `CliRunner` 里，即使 `-y` 没实现，走无终端分支也是全选，测试照样会通过。
- 判断依据只有 stdin，不看 stdout。`skm install ... | tee log` 这种 stdin 仍是终端的情况，勾选框照常弹出。

## 遗留问题

- stdout 不是终端时，进度行里的 `\033[K` 控制字符会原样输出（验收日志里可以看到 `[K  tinyhost[K`）。这是原有行为，只影响日志的可读性。

## 相关文档

- [Dynamic skill session](2026-11-15-dynamic-skill.md)：参考，`install --cmd` 和 `_choose_agents_config` 来自这次
- [Known Issues](../known-issues.md)：更新了两条条目中无终端时的表现
