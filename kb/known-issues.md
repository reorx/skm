# Known Issues

> 当前影响使用或稳定性、仍待处理的问题；解决后删除，处理结果写入 KB。

## 列表：目录名称前缀相同时可能显示错误 agent

- 记录：2026-10-23，见 [PR 需求调研](notes/2026-10-23-github-pr-requirements-research.md)。
- `src/skm/commands/list_cmd.py` 的 `_agent_name_from_link` 使用字符串 `startswith` 判断归属。例如 lock 路径 `~/.agents/skills-extra/demo` 会匹配内置 `standard` 的 `~/.agents/skills`，导致列表显示错误 agent；自定义 agent 目录与另一个目录共享前缀时可触发。
- 2026-10-28 已实测复现：`_agent_name_from_link('~/.agents/skills-extra/demo')` 返回 `standard`，`'~/.claude/skills2/x'` 返回 `claude`。另外不带 `--all` 的 `skm list` 用的是全局 `KNOWN_AGENTS`，不认 `--agents-dir`。开放的 [PR #7](https://github.com/reorx/skm/pull/7) 改为比较父目录是否相等，并附回归测试，尚未合入。处理时应先补失败测试，再改判断。

## 直接安装：agent 选择器列出 default 以外的 agent，勾了不生效，还会把 includes 写死进配置

- 记录：2026-10-28，对照 [PR #7](https://github.com/reorx/skm/pull/7) 时发现；复现脚本 `tmp/2026-10-28-pr-priority/repro_agent_picker.py`。
- 在 `agents.default: [claude, standard]` 下执行 `skm install <source>`，选择器会列出全部 5 个 agent。勾上 openclaw 后，配置里写入 `includes: [standard, claude, openclaw]`，退出码为 0，但 openclaw 里没有装任何东西，因为安装只在 default 范围内过滤。如果直接接受预选，配置会写入 `includes: [standard, claude]`，之后往 `agents.default` 里加 agent，这个包也不会跟着装。
- 处理方向：选择器只列 default 范围内的 agent，全选时不写 `agents`。PR #7 的做法就是这样。

## openclaw：源文件被替换式保存后硬链副本变旧，install 卡在覆盖确认

- 记录：2026-10-23，standard 改为软链时确认 openclaw 仍走硬链（`AGENT_OPTIONS`）。
- 编辑器、agent 的 Edit 工具和 `sed -i` 保存时会换掉 inode，`~/.openclaw/skills` 里的副本还是旧内容，源里新增的文件和点开头的文件也不会带过去。之后 `skm install` 判定副本"不是受管副本"，逐个询问是否覆盖；非终端环境下直接报错退出。只影响启用了 openclaw 的用户，本机目前没启用。
- 处理方向：OpenClaw 新版支持 `skills.load.allowSymlinkTargets`，配置 skm store 和 local_path 目录后也许可以改回软链，需要实测；或者把 lock 里记录过的副本直接当作受管副本刷新，前提是先确认副本里没有只存在于副本的改动。
