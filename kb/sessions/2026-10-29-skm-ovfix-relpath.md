---
created: 2026-10-29
tags:
  - agents
  - config
  - testing
---

## 协调者摘要（skm-ovfix-relpath）

- 结果：完成 review 第 3 条；override.path 展开 `~` 后必须是绝对路径，配置错误发生在安装前。
- 提交：代码、测试、README 和本总结同一提交，标题 `fix: reject relative agent override paths`；hash 见交付回复或本文件 git log。
- TDD：定向测试修复前 6 failed、7 passed、48 deselected；修复后 13 passed、48 deselected。
- 全量：`uv run pytest -m "not network" -q` → 206 passed、4 deselected（基线 198 passed，新增 8 例）。
- repro：`relative_override` 修复前首次安装成功，第二次删除 cwd-b 的无关目录；修复后首次退出 1、输出 Invalid config、lock 为 None，第二次合法安装成功且无关目录和 precious.txt 完整保留。
- 决定：沿用 D5；只在 AgentOverride.check_path 增加校验，保留原配置字符串，由 Pydantic 字段定位指出具体 agent 的 path。
- 未验证：network 测试、真实用户安装目录、README 浏览器预览；未 push，未启动浏览器或模拟器。
- 交给协调者：请在 AGENTS.md 的 override 配置说明同步绝对路径约束；共享文件和第 4 条问题未改，无新增范围外发现。

## 修改与验证细节

`src/skm/types.py` 在已有空路径校验后检查 `Path(value).expanduser().is_absolute()`；错误提示为 `'path' must be an absolute path or ~/...`。现有 CLI 错误路径输出 `agents.override.claude.path` 和 `Invalid config`，无需修改 resolver 或清理逻辑。

`tests/test_config.py` 直接构造 SkmConfig，验证 `rel-skills`、`./x`、`../x` 被拒绝，绝对路径和 `~/x` 被接受，并断言错误定位及修正提示。`tests/test_agent_override.py` 扩展非法配置参数化测试，使用真实临时 git 仓库确保校验阻止安装，断言 agents、store、HOME 和 lock 均未创建。HOME 和 agent 环境变量均隔离。cc-format hook 对该文件已有两处表达式自动换行，无行为变化。

`README.md` 两处路径说明补充 override 必须使用绝对路径或能展开为绝对路径的 `~` 写法。本次没有修改 `--agents-dir`、环境变量、local_path 的相对路径规则。

定向测试命令：

```bash
uv run pytest tests/test_config.py tests/test_agent_override.py -k 'override_rejects_relative_path or override_accepts_absolute_or_home_path or invalid_override_has_no_install_side_effects' -q
```

复现命令（分别在修复前后运行；脚本自带隔离、交互 mock 和 60 秒超时）：

```bash
uv run python tmp/2026-10-29-agent-override-review/repro.py relative_override tmp/2026-10-29-agent-override-review/work/relpath-before
uv run python tmp/2026-10-29-agent-override-review/repro.py relative_override tmp/2026-10-29-agent-override-review/work/relpath-after
```

`git diff --check` 通过。任务范围内没有遗留问题；没有创建截图或需清理的测试服务。

## 相关文档

- [agent override 实施总结](2026-10-28-agent-override.md) — 参考既有架构及总结 frontmatter。
