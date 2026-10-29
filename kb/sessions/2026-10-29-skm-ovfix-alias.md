---
created: 2026-10-29
tags:
  - agents
  - install
  - bugfix
  - testing
---

## 协调者摘要（skm-ovfix-alias）

- 结果：全量 install、直接安装、update 有新提交时，共用文件系统位置判断，兼容软链及大小写目录别名不再导致刚安装的 skill 被删除；lock 记录新路径。
- 提交：代码、测试和本总结同在 `fix: preserve installed skills when agent paths alias the same directory` 提交中；hash 见最终回复，也可用 `git log -1 --format=%H -- kb/sessions/2026-10-29-skm-ovfix-alias.md` 查询。
- TDD：`uv run pytest tests/test_agent_override.py -k alias -q`：修复前 14 failed、29 deselected，修复后 14 passed、29 deselected。
- 全量：`uv run pytest -m "not network" -q`：197 passed、4 deselected（18.72 秒），包含上一任务的全部 decline 用例；`git diff --check` 通过。
- repro：`alias_install` 首次迁移 MISSING → symlink；`alias_update` MISSING → dir；`alias_case_heal` 首次 MISSING → symlink，第二次仍为 symlink；`decline_direct` 前后均 dir、lock 为 `{'demo': []}`；所有 CLI exit 0。
- 自行决定：将同一位置判断也用于 skipped_paths，新增两个“别名迁移后拒绝覆盖”用例，保留用户目录并退出 lock 管理；测试覆盖 symlink/materialize 两种模式及三个入口。
- 未验证：网络测试、真实用户目录、真实交互输入、大小写敏感文件系统上的 skip 分支；本机大小写不敏感，六个大小写用例均实际执行。
- 交给协调者：请修正计划「风险与待定」第二条关于别名只影响显示的说法；可在 AGENTS.md 说明清理按名称及父目录身份判断。共享文件均未改。list 别名显示、第 3–7 条仍在原范围边界，本任务没有顺带修复第 5 条。
- 返工 r1：新增 set 精确匹配快速路径；新提交 `fix: skip alias comparisons for unchanged install paths`（hash 见返工最终回复或本文件最新 git log）。500 条保留路径 + 5 条 stale，7 次中位耗时由 2e76357 的 704.666 ms 降至 14.065 ms（50.10×）；离线全量 198 passed、4 deselected。

## 修改的文件

- `src/skm/utils.py`：新增 `same_install_location`，展开 `~`，相同路径直接命中，否则要求名称相同且两个父目录存在并且 `samefile`。
- `src/skm/commands/install.py`：新安装路径和拒绝覆盖路径的保护均使用同一判断；全量和直接安装继续共用 `_remove_stale_links`。
- `src/skm/commands/update.py`：有新提交后的旧路径清理使用同一判断，lock 仍记录新配置产生的路径。
- `tests/test_agent_override.py`：新增 12 个安装迁移场景及 2 个拒绝覆盖场景，检查文件实际可读、安装模式、更新内容、lock 路径和无误删输出。

## 注意事项

只比较父目录的文件系统身份，不对 skill 链接自身调用 samefile：不同 agent 的独立链接通常指向同一个源，不能因此阻止移除真正过期的旧链接。现有 `test_override_migration` 和 agent 取消选择测试继续验证真实路径迁移仍会清理。

父目录缺失时不调用 samefile，仍按原来的存在性判断跳过不存在的旧安装。底层函数没有新增 try/except。`compact_path` 行为未修改；cc-format 编辑 hook 调整了该函数及 update 的少量既有排版，没有主动运行 formatter/linter。

所有测试在 tmp_path 下运行；repro 使用脚本自建的 HOME/config/lock/store，清除三个 agent 环境变量，mock 选择器和确认，60 秒超时。没有启动浏览器、模拟器，也没有截图。

## 复现证据

脚本：`tmp/2026-10-29-agent-override-review/repro.py`。

运行格式：`uv run python tmp/2026-10-29-agent-override-review/repro.py <场景> tmp/2026-10-29-agent-override-review/work/ovfix-alias-<before|after>-<场景>`。

日志目录：`tmp/2026-10-29-agent-override-review/`，文件名为 `ovfix-alias-<before|after>-<场景>.log`，对应工作目录保留在该目录的 `work/` 下。

| 场景 | 修复前 | 修复后 |
|---|---|---|
| alias_install | 新路径缺失，lock 却已记录新路径 | 新路径为 symlink，lock 记录 `~/data/claude-skills/demo` |
| alias_update | 新路径缺失，lock 却已记录新路径 | 新路径为 dir，lock 记录 `~/data/openclaw-skills/demo` |
| alias_case_heal | 首次缺失，第二次 install 才恢复 | 首次就是 symlink，第二次仍为 symlink |
| decline_direct | 用户目录保留、lock linked_to 为空 | 用户目录保留、lock linked_to 仍为空 |

## 相关文档

- [agent override 计划](../plans/2026-10-28-agent-override.md) — 参考范围及风险条目，修订交给协调者。
- [上一任务：拒绝覆盖保护](2026-10-29-skm-ovfix-decline.md) — 保留并扩展 skipped_paths 对别名的保护。
- [agent override 实现总结](2026-10-28-agent-override.md) — 参考原行为和 frontmatter 格式。

## 返工 r1 验证详情

- `_remove_stale_links` 先检查 `new_linked_paths` 与 `skipped_paths` 的 set 成员关系；任一精确命中就跳过，未命中才沿用原来的别名比较。update 未改；未新增按名称分组，当前少量 stale 的扫描保留。
- 新增 `test_stale_cleanup_exact_matches_skip_alias_comparisons`，同时覆盖保留路径和拒绝路径，断言精确命中时不调用文件系统别名比较，且目录均保留。`uv run pytest tests/test_install.py -k exact_matches -q` 修复前 1 failed、7 deselected；修复后随全量测试通过。
- `uv run pytest -m "not network" -q`：198 passed、4 deselected（16.53 秒）；既有 alias 与 decline 用例全部通过。`git diff --check` 通过。
- 计时脚本：`tmp/2026-10-29-agent-override-fixes/benchmark-alias-r1.py`；运行 `uv run python tmp/2026-10-29-agent-override-fixes/benchmark-alias-r1.py`，输出保存在同目录的 `benchmark-alias-r1.log`。tmp 按仓库约定不纳入提交。
- 脚本用 `git show 2e76357:src/skm/commands/install.py` 加载旧版清理函数，与工作目录版本在同一进程比较。临时 HOME 位于该 tmp 目录内，清空三个 agent 环境变量，60 秒超时；构造 100 个 skill × 5 个 agent，再加一个含 5 条 stale 路径的旧条目。每版运行 7 次，建目录及断言不计入耗时；每次确认保留 500 个安装目录、删除 5 个 stale 目录。结束自动删除临时目录。
- 这是本机该数据规模的计时证据，不代表所有环境的固定提升比例；没有访问真实配置或 agent 目录，没有运行网络测试。
