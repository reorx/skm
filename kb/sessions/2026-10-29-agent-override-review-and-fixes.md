---
created: 2026-10-29
tags:
  - agents
  - review
  - install
  - update
  - coordination
---

# 评审 agent override 提交，并协调修复中等及以上的 4 个问题

## 概要

对 22ec4ba（agents.override 与统一 agent 解析）做了独立评审。写了隔离的复现脚本，并用 `git archive` 导出 `22ec4ba^` 的源码做对照，区分哪些问题是这个提交引入的、哪些原来就有。共确认 7 个问题：1 个高、3 个中、1 个低–中、2 个低。按用户要求修复中等及以上的 4 个：由本会话按 herdr 协调技能拆成 4 个任务，串行派给 Astra（codex）执行，每条一个提交，测试先写。第 2 条第一次交付后又做了一次性能返工。最后更新了 AGENTS.md、计划的风险说明和 known-issues。离线测试从 180 个增加到 216 个，全部通过；修复前会失败的复现场景，修复后都通过。

修复的问题：
1. （高）用户在覆盖确认里选 N 后，SKM 仍然删掉用户目录：4e128e2。全量 install 原来就有这个问题，这个提交把它带到了直接安装。
2. （中）新旧路径经软链或只差大小写、其实是同一位置时，清理把刚装好的 skill 删掉：2e76357 + f0eb7f8。
3. （中）`override.path` 接受相对路径，后续命令按当前目录清理，会删掉无关目录：ed04037。
4. （中）`compact_path` 不看路径分隔符，lock 写成 `~2/...`，之后 list 和 install 崩溃：f5901ea。

## 修改的文件

- `src/skm/commands/install.py`：记录用户拒绝覆盖的路径，清理时跳过，lock 也不再记录；清理先按字符串匹配，匹配不上再判断是否同一位置。
- `src/skm/commands/update.py`：清理改用同一个判断位置的函数。
- `src/skm/utils.py`：新增 `same_install_location`（名字相同，且父目录 `samefile`）；`compact_path` 只在 HOME 的路径分隔符边界处压缩。
- `src/skm/types.py`：`AgentOverride.check_path` 要求展开 `~` 后是绝对路径。
- `tests/test_agent_override.py`、`tests/test_install.py`、`tests/test_config.py`、`tests/test_utils.py`：上述 4 个问题的回归用例。
- `README.md`：补充拒绝覆盖后的行为，以及 `override.path` 的绝对路径要求。
- `AGENTS.md`：写明清理按同一位置判断、拒绝覆盖的目录保留、override 路径必须是绝对路径、`compact_path` 的边界；`--agents-dir` 的说明改为 installs。
- `kb/plans/2026-10-28-agent-override.md`：修正"别名路径只影响显示"的风险说明，实施结果链接到 4 份修复总结。
- `kb/known-issues.md`：新增 update 清理会删掉另一个包同名安装的条目（评审第 5 条）。
- `kb/sessions/2026-10-29-skm-ovfix-*.md`：4 个执行者各自的修复总结，和代码在同一个提交里。

## 注意事项

- 清理判断"是否同一位置"要看文件系统身份，不能只比字符串：软链目录、大小写不敏感的卷、旧版 lock 里的绝对路径，都会让字符串不同、位置相同。逐对比较的代价是 O(旧 × 新)，必须先做 set 精确匹配，只有没匹配上的路径再比较。实测 500 条路径从 705 ms 降到 14 ms。
- 计划里的风险判断要用复现验证。原计划说别名"只影响显示，不影响安装"，复现证明 install 和 update 都会因此删掉新安装。
- 区分新问题和原有问题的办法：`git archive <rev>^ src | tar -x -C tmp/.../base`，再用 `PYTHONPATH=tmp/.../base/src uv run python ...` 跑同一个场景。这样不碰工作区，也不建 worktree。
- CliRunner 的 stdin 是空的，`interactive_multi_select` 读到空字符会一直循环，复现脚本因此卡住过。用例和脚本里都要 mock 选择器和 `_confirm_override`，脚本再加 `signal.alarm` 兜底。
- `pathlib.Path('~2/x').expanduser()` 会抛 `RuntimeError`（`os.path.expanduser` 则原样返回），所以 lock 里一旦写入 `~<非用户名>` 前缀，后面所有读取都会崩溃。
- 协调时选择串行派发：第 1、2 条改的是同一个清理函数；而且 TDD 先写的失败用例会让同一个 checkout 里其他 agent 跑全量测试时变红。

## 遗留问题

- update 清理不保护其他包仍在用的同一路径（评审第 5 条），已记入 `kb/known-issues.md`。
- `override.path` 写成 `~不存在的用户/x` 时，validator 里抛的 `RuntimeError` 没有转成校验错误，用户看到的是 traceback。影响小，没有记入 known-issues。
- update 一直用 `force=True`：如果新的 override 路径下已有同名的用户目录，update 会不经确认直接覆盖。这是原有行为，没有复现，留待用户决定要不要查。
- 直接安装的汇总输出少了空行（评审第 6 条），只影响外观，没有修。
- `skm list` 的归属判断不跟随软链或 `..`，属于计划已接受的显示问题。
- 执行者的 tab `w4H:t3`–`w4H:t6` 还开着，等用户决定是否关闭。协调记录在 `tmp/2026-10-29-agent-override-fixes/`，复现脚本和对照源码在 `tmp/2026-10-29-agent-override-review/`。

## 相关文档

- [agent override 计划](../plans/2026-10-28-agent-override.md)：被评审的计划，本次修正了风险说明并补充了实施结果。
- [agent override 实施总结](../sessions/2026-10-28-agent-override.md)：产生被评审代码的 session。
- [修复：拒绝覆盖不删除](../sessions/2026-10-29-skm-ovfix-decline.md)：第 1 条的执行总结。
- [修复：别名路径清理](../sessions/2026-10-29-skm-ovfix-alias.md)：第 2 条的执行总结（含性能返工）。
- [修复：相对路径校验](../sessions/2026-10-29-skm-ovfix-relpath.md)：第 3 条的执行总结。
- [修复：compact_path 边界](../sessions/2026-10-29-skm-ovfix-home.md)：第 4 条的执行总结。
- [已知问题](../known-issues.md)：本次新增 update 同名安装清理一条。
