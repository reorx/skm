# Known Issues

> 当前影响使用或稳定性、仍待处理的问题；解决后删除，处理结果写入 KB。

## 列表：目录名称前缀相同时可能显示错误 agent

- 记录：2026-10-23，见 [PR 需求调研](notes/2026-10-23-github-pr-requirements-research.md)。
- `src/skm/commands/list_cmd.py` 的 `_agent_name_from_link` 使用字符串 `startswith` 判断归属。例如 lock 路径 `~/.agents/skills-extra/demo` 会匹配内置 `standard` 的 `~/.agents/skills`，导致列表显示错误 agent；自定义 agent 目录与另一个目录共享前缀时可触发。
- 已通过当前代码静态确认，尚未执行独立复现测试。开放的 [PR #7](https://github.com/reorx/skm/pull/7) 提供父目录精确比较及回归测试，尚未合入。处理时应先补充失败测试，再修复判断。
