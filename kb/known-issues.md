# Known Issues

> 当前影响使用或稳定性、仍待处理的问题；解决后删除，处理结果写入 KB。

## 列表：目录名称前缀相同时可能显示错误 agent

- 记录：2026-10-23，见 [PR 需求调研](notes/2026-10-23-github-pr-requirements-research.md)。
- `src/skm/commands/list_cmd.py` 的 `_agent_name_from_link` 使用字符串 `startswith` 判断归属。例如 lock 路径 `~/.agents/skills-extra/demo` 会匹配内置 `standard` 的 `~/.agents/skills`，导致列表显示错误 agent；自定义 agent 目录与另一个目录共享前缀时可触发。
- 已通过当前代码静态确认，尚未执行独立复现测试。开放的 [PR #7](https://github.com/reorx/skm/pull/7) 提供父目录精确比较及回归测试，尚未合入。处理时应先补充失败测试，再修复判断。

## openclaw：源文件被替换式保存后硬链副本变旧，install 卡在覆盖确认

- 记录：2026-10-23，standard 改为软链时确认 openclaw 仍走硬链（`AGENT_OPTIONS`）。
- 编辑器、agent 的 Edit 工具和 `sed -i` 保存时会换掉 inode，`~/.openclaw/skills` 里的副本还是旧内容，源里新增的文件和点开头的文件也不会带过去。之后 `skm install` 判定副本"不是受管副本"，逐个询问是否覆盖；非终端环境下直接报错退出。只影响启用了 openclaw 的用户，本机目前没启用。
- 处理方向：OpenClaw 新版支持 `skills.load.allowSymlinkTargets`，配置 skm store 和 local_path 目录后也许可以改回软链，需要实测；或者把 lock 里记录过的副本直接当作受管副本刷新，前提是先确认副本里没有只存在于副本的改动。
