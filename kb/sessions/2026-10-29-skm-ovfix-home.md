---
created: 2026-10-29
tags:
  - agents
  - paths
  - testing
---

## 协调者摘要（skm-ovfix-home）

- 结果：compact_path 仅在路径等于 HOME 或以 HOME + 路径分隔符开头时压缩，兄弟目录保留绝对路径。
- 提交：本总结与代码、测试同一提交，提交信息 `fix: respect home directory boundary in compact_path`（hash 见最终交付回复）。
- TDD：`uv run pytest tests/test_utils.py tests/test_agent_override.py -k 'compact_path or home_prefix' -q` 修复前 5 failed、5 passed、46 deselected；修复后 10 passed、46 deselected。
- 全量：`uv run pytest -m "not network" -q` → 216 passed、4 deselected。
- repro home_prefix：修复前 list 和第二次 install 均 exit 1 / RuntimeError，旧安装仍在；修复后全部 exit 0，list 显示 claude，旧安装 MISSING。
- 自行决定：HOME 末尾斜杠由 Path.home() 规范化，正常与带斜杠 HOME 都覆盖相同边界用例；路径字符串本身不额外规范化。
- 未验证：网络测试、真实用户安装目录；按 D6 不迁移损坏 lock、不添加 expanduser 容错。
- 交给协调者：无新增范围外问题；共享文档未改。

## 修改的文件

- `src/skm/utils.py`：增加路径分隔符边界判断，签名和 same_install_location 行为不变。
- `tests/test_utils.py`：9 个单元用例，覆盖 HOME 本身、子路径、两类同前缀兄弟目录、无关路径及 HOME 末尾斜杠。
- `tests/test_agent_override.py`：新增隔离 e2e，验证兄弟目录 lock 绝对路径、list agent 归属及修改 override 后清理旧安装。

## 验证细节

复现命令：`uv run python tmp/2026-10-29-agent-override-review/repro.py home_prefix tmp/2026-10-29-agent-override-review/work/home-after-fix`；修复前同命令的输出目录为 `home-before-fix`。两次均使用脚本内临时 HOME、独立 config/lock/store、交互 mock 和 60 秒超时。修复后 lock 从绝对兄弟目录更新为 `~/new/demo`。

首次编写 e2e 时误将确认 mock 指向 linker，已纠正为 commands.install，并在修改生产代码之前重跑，确认失败点是 lock 错写 `~2/skills/demo`。未启动浏览器、模拟器，无截图或测试资源需要清理。

## 相关文档

- [agent override 实施总结](2026-10-28-agent-override.md) — 参考 frontmatter 格式及原始实施背景。
