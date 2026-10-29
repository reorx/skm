---
created: 2026-10-29
tags:
  - agents
  - install
  - bugfix
  - testing
---

## 协调者摘要（skm-ovfix-decline）

- 结果：全量 install、直接安装拒绝覆盖后保留用户目录及内容，拒绝路径不再进入 lock；后续移除配置也不会删除该目录。
- 提交：代码、测试、README、本总结在同一个 `fix: preserve user directories when skill overwrite is declined` 提交中；hash 见最终回复，也可用 `git log -1 --format=%H -- kb/sessions/2026-10-29-skm-ovfix-decline.md` 查到。
- TDD：`uv run pytest tests/test_agent_override.py -k declined_override -q` 修复前 3 failed、26 deselected，修复后 3 passed、26 deselected；中间发现 agent.path 是 str，修正 Path 转换后通过。
- 全量：`uv run pytest -m "not network" -q`：183 passed、4 deselected（13.43 秒）；`git diff --check` 通过。
- repro：`decline_direct`、`decline_install` 修复前均为 `MISSING`，修复后均为 `dir`，lock 均为 `{'demo': []}`，CLI 均 exit 0；完整输出路径见下。
- 自行决定：保持现有提示行为，只在 verbose 模式输出 `Skipped ...`，非 verbose 不增加提示；新增回归覆盖 Git 来源和后续清理，避免只验证本地来源的当前一次安装。
- 未验证：网络测试、真实用户目录、真实交互键盘；选择器和确认均 mock，测试与 repro 全部隔离，没有启动浏览器或模拟器。
- 交给协调者：本任务无新范围外发现或反对意见；别名路径仍按 D4 交下一任务处理，需将 skipped_paths 的保护判断一并考虑。本任务未修改共享协调文件、AGENTS.md、计划或 known issues。

## 修改的文件

- `src/skm/commands/install.py`：每次安装独立收集 `skipped_paths`，本地和 Git 来源拒绝覆盖时记录目标；全量与直接安装将集合交给 `_remove_stale_links`，清理跳过这些路径，不写回 lock。
- `tests/test_agent_override.py`：三个参数化回归场景（全量本地、全量 Git、直接本地），断言用户目录与文件保留、lock 只记录另一 agent 的正常安装、移除配置后用户文件仍在且正常安装被清理。
- `README.md`：Install Sync Behavior 补充拒绝覆盖保留目标并退出 lock 管理的行为。
- 本总结：记录测试和复现证据。编辑后的 cc-format hook 自动调整了两份 Python 文件的部分排版，没有主动运行 formatter/linter。

## 复现证据

脚本：`tmp/2026-10-29-agent-override-review/repro.py`，自建 HOME/config/lock/store，清除三个 agent 环境变量，mock 两个交互函数，60 秒超时。

运行格式：`uv run python tmp/2026-10-29-agent-override-review/repro.py <场景> tmp/2026-10-29-agent-override-review/work/<目录名>`。

| 场景 | 修复前目录名 / 日志 | 修复后目录名 / 日志 | 目标状态 |
|---|---|---|---|
| decline_direct | `decline-before-direct` / `decline-before-direct.log` | `decline-after-direct` / `decline-after-direct.log` | MISSING → dir |
| decline_install | `decline-before-install` / `decline-before-install.log` | `decline-after-install` / `decline-after-install.log` | MISSING → dir |

上述日志都在 `tmp/2026-10-29-agent-override-review/`。两条修复后输出的关键行均为：

```text
[user dir after declining] agents/claude/demo -> dir
lock: {'demo': []}
```

本次只改变当前安装目标拒绝覆盖后的清理；计划接受的旧位置实体目录清理规则保持现状。skipped_paths 目前沿用 compact_path 字符串匹配，路径别名问题不在本任务范围。

## 相关文档

- [agent override 计划](../plans/2026-10-28-agent-override.md) — 参考风险边界，拒绝覆盖不属于已接受的旧位置清理风险。
- [agent override 实现总结](2026-10-28-agent-override.md) — 参考原实现与 frontmatter 格式。
