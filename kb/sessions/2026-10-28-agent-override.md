---
created: 2026-10-28
tags:
  - agents
  - config
  - install
  - testing
---

# 实现 agent 路径和安装模式覆盖，统一安装与列表行为

## 概要

按 agent override 计划实施：以 BUILTIN_AGENTS 和运行时 resolve_agents 统一路径、环境变量和安装方式，支持 skills.yaml 覆盖；修复列表前缀误判和直接安装选择器；安装和更新清理旧位置，includes 不生效时给出警告，损坏配置下列表降级。

先运行基线测试（146 passed），新增行为用例确认失败，再实现并迁移原有测试接口。最终 `uv run pytest -m 'not network' -q`：180 passed，4 deselected。PTY 验证选择器只列 default 且全选、standard 实体目录安装、警告与进度行、旧位置清理；样例和复验脚本位于 `tmp/2026-10-28-agent-override/`。没有触碰真实 SKM 配置和 agent 目录，没有启动浏览器或模拟器。

## 修改的文件

- `src/skm/types.py`、`src/skm/agents.py`：统一内置定义、override 校验和运行时解析；增加 Pi 环境变量。
- `src/skm/cli.py`：配置错误转换、list 降级、直接安装选择器跟随 default；clone 前校验配置。
- `src/skm/linker.py`：显式 install_mode 和纯函数 includes 检查。
- `src/skm/commands/{install,update,list_cmd}.py`：使用解析后的 agent，迁移清理、警告、精确父目录匹配。
- `tests/test_agent_override.py`、`tests/test_agents.py`：配置、优先级、迁移、模式切换、列表和选择器行为覆盖；其余相关测试迁移到 ResolvedAgent。
- `README.md`、`AGENTS.md`：更新配置示例、路径优先级、默认模式、Pi 和迁移规则。
- 计划及 `kb/known-issues.md`：勾选完成，移除两个已解决问题，记录验收新发现的已有问题。

## 注意事项

- 环境变量在每次命令执行时读取；override 模式与路径独立，CLI 目录覆盖不影响模式。
- YAML 语法错误属于 YAMLError，必须与 ValueError 一并在 CLI 层处理。
- update 无新提交时保留安装和 lock 中的旧路径，下一次 install 负责迁移；无效 includes 仍会警告。
- 单包重装只清理该来源旧记录，并保护其他包仍在 lock 中使用的路径。
- list 正常模式识别所有内置 agent，--all 只扫描 default；读取配置失败时使用内置定义加环境变量和 CLI 路径。

## 遗留问题

- 实体副本的源文件替换、同步与覆盖确认规则仍按原有行为，见 known issues；本次未改变。
- 验收发现相对 local_path 形成断链，已登记 known issues；绝对路径和 `~/...` 可绕过，复验用绝对路径确认文件可读。
- 按计划沿用旧清理规则：lock 记录的旧实体目录会整体删除，不检查用户对该副本的修改。

## 已解决的已知问题

- 列表：目录名称前缀相同时可能显示错误 agent。改为安装路径父目录精确比较，测试覆盖前缀误判、CLI 路径、override 和非 default agent。
- 直接安装：agent 选择器列出 default 以外的 agent，勾了不生效，还会把 includes 写死进配置。仅列启用的 agent，全选不写 agents；测试验证 default 扩大后包会跟随安装。

## 相关文档

- [agent override 计划](../plans/2026-10-28-agent-override.md) — 本次实施依据，已更新验收和结果。
- [已知问题](../known-issues.md) — 移除已修复条目，记录相对路径问题。
