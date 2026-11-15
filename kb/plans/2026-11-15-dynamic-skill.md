---
created: 2026-11-15
tags:
  - dynamic-skill
  - source-cmd
  - install
  - update
---

# Dynamic skill：用 CLI 输出生成 skill（`source_cmd`）

## PRD

### 背景

有些 CLI 自带 skill，内容要运行命令才能拿到，例如 `tinyhost skill` 往 stdout 打印一份带 frontmatter（`name: tinyhost`）的完整 SKILL.md。skm 目前只能装 git repo 和本地目录里的 skill，这类 skill 只能手动重定向到文件再当 local_path 装，CLI 升级后内容不会跟着更新。

### 目标

在 skills.yaml 里写一行命令，skm 就能把它的输出装成 skill，和其他 skill 一样 link 到各 agent 目录；`skm update` 时重新运行命令刷新内容。

### 功能与交互

```yaml
packages:
  - source_cmd: tinyhost skill
    agents:            # 可选，和其他包一样
      includes: [claude]
```

- **install**：第一次运行命令，把输出存成 skill 并 link。已经生成过就不重跑（和 repo 已 clone 就不 pull 一样）。命令失败（比如共享 skills.yaml 的另一台设备没装这个 CLI）时打黄色警告和原因，跳过这个包，其余照常装，退出码 0；下次 install 再试。
- **命令执行**：用 `sh -c` 运行，可以用管道和环境变量；不接 stdin，工作目录固定为 home，最多运行 60 秒。
- **输出校验**：必须是带 frontmatter 和 `name` 的 SKILL.md；`name` 只能由字母数字和 `._-` 组成且不以符号开头，否则报错，不会写入任何文件。
- **update**：`skm update <name>` 和 `--all` 都重跑命令。内容没变显示 `✔ Already up to date`；变了就刷新内容并重新 link（skill 名变了，旧名的链接会被删掉）。命令失败直接报错。
- **list**：显示 `cmd: tinyhost skill`；`list --all` 在来源处显示命令。
- **remove**：删除链接、lock 条目和 skills.yaml 里的包。
- **check-updates**：不对比，提示 `Skipping dynamic skill: tinyhost (run skm update tinyhost to regenerate)`。
- **local source**：同名时 local source 照样优先。
- **`skm install --cmd "<cmd>"`**：不能和 SOURCE、`--local` 同时用。先运行并校验，命令有错就不写 skills.yaml；已在配置里就沿用原有包。agent 选择同直接安装：`--agents-includes/--agents-excludes`，否则交互多选，全选时不写 agents。

### 不做的事

- check-updates 不运行命令对比内容
- 一个命令只产出一个 skill，不支持 `skills`/`skills_excludes`/`skills_dir`/`clone_strategy`
- remove 不删除生成的文件（和 repo clone 一样留在 store 里）
- 不给 repo 里的 SKILL.md `name` 补路径校验

### 验收标准

- skills.yaml 写了 `source_cmd` 后 `skm install`，agent 目录里出现同名 skill，内容就是命令输出
- 命令不存在时 install 打警告、退出码 0，其他包照常装
- 上游输出变化后 `skm update <name>` 刷新内容；没变化时提示已是最新
- `skm list`、`check-updates`、`remove` 表现如上
- `skm install --cmd` 写入配置并安装；命令失败时配置不变

## Tech Design

### 现状

- 包类型由 `SkillRepoConfig`（`src/skm/types.py`）的 `repo` / `local_path` 二选一决定；`source_key` 用于配置合并、lock 归属、local source 覆盖判断。
- `run_install` / `run_install_package`（`src/skm/commands/install.py`）按 `is_local` 分派到 `_install_local` / `_install_repo`，两者有一大段重复的"逐个 agent link 并记 lock"循环。
- lock 条目 `InstalledSkill` 用 `repo or local_path` 表示来源，散落在 install、remove、list 里。
- `config._raw_pkg_source_key` 只认 `local_path` 和 `repo`。

### 方案

新增 `source_cmd` 包类型：运行命令得到 SKILL.md 文本，校验后写到 store 下 skm 管理的目录，再走现有的 link 流程。

关键决策：

- **生成目录** `<store>/_dynamic/<slug>-<hash8>/SKILL.md`：slug 是命令里 `[a-z0-9]+` 片段用 `-` 连接，最长 40；hash8 是命令 sha256 前 8 位。`--store` 一并隔离，不新增 flag；改命令即换目录。repo 目录名形如 `host_path`，不会以 `_` 开头，不会撞名。备选"放在 config 目录旁"被否决：config 目录可能在 git 里共享。
- **运行**：复用 `git.run_cmd(['sh', '-c', cmd], text=True, stdin=DEVNULL, cwd=Path.home(), timeout=60)`；非零退出由 `run_cmd` 抛 ClickException 带 stderr；超时抛 `subprocess.TimeoutExpired`。
- **先校验后写入**：去掉开头空白，用拆出来的 `parse_skill_name_text` 解析 name，再按 `^[A-Za-z0-9][A-Za-z0-9._-]*$` 校验——name 会成为 agent 目录下的路径名，`../x` 会写出目录外。
- **原地写入**：内容不变不写；变了 `write_text` 覆盖，不换 inode，materialize agent 的硬链副本自动同步（避开 known-issues 里替换式保存的问题）。
- **失败处理**：`_install_dynamic` 是失败处理的顶层，捕获 `ClickException`/`TimeoutExpired`/`ValueError` 后警告并返回空结果；底层 `dynamic.py` 不写 try/except。

### 数据变动

- `SkillRepoConfig.source_cmd: str | None`；校验三选一；空白命令报错；与 `skills_dir`/`clone_strategy`/`skills`/`skills_excludes` 同时出现报错；`is_dynamic` 属性；`source_key` 返回命令。
- `InstalledSkill.source_cmd: str | None` 和 `source` 属性。lock 条目：`source_cmd: <cmd>`、`skill_path: '.'`、`commit: null`。`save_lock` dump 全部字段，现有条目会一次性多出 `source_cmd: null`。

### 逻辑变动

- `src/skm/dynamic.py`（新）：`dynamic_skill_dir`、`render_source_cmd`、`generate_dynamic_skill`、`load_dynamic_skill`。
- `src/skm/detect.py`：拆出 `parse_skill_name_text(text, origin)`。
- `install.py`：提取 `_target_agents`、`_link_skills`，三种来源共用；新增 `_install_dynamic`、`_install_package` 分派；`_remove_stale_links` 与合并逻辑改用 `.source`。
- `update.py`：dynamic 条目单独分组，`_update_dynamic` 重跑、`force=True` 重新 link、清理旧路径、替换 lock 条目。
- `check_updates.py` / `list_cmd.py` / `remove.py`：识别 `source_cmd`，用 `.source`。
- `config.py`：`_raw_pkg_source_key` 加 `source_cmd` 分支（否则多个 dynamic 包 key 都是 `''`，保存时互相串掉）。
- `cli.py`：`install --cmd` 与 `_install_cmd_source`。
- 文档：`AGENTS.md`、`README.md`。

### 实施步骤

- [x] 写 `tests/test_dynamic.py`（BDD，先失败）
- [x] types / detect / dynamic.py
- [x] install 重构 + dynamic 分支
- [x] update / check-updates / list / remove / config
- [x] cli `--cmd`
- [x] 全量测试通过
- [x] 用真实 `tinyhost skill` 隔离路径手动验收
- [x] 文档、session summary、commit

### 测试与验证

`tests/test_dynamic.py`，命令统一用 `cat <tmp>/out.md`（`shlex.quote`），改 out.md 模拟上游变化；全程 `_cli_args(tmp_path)` 隔离。

- config：只写 source_cmd 通过；与 repo 同写、与 skills/skills_dir 同写、空命令报错
- 生成：写到 `_dynamic/<slug>-<hash>/SKILL.md`；无 frontmatter、name 非法、非零退出（带 stderr）、超时报错
- install e2e：创建链接、lock 有 source_cmd；二次 install 不重跑；失败时警告、exit 0、其他包照装、不进 lock；删包后清理链接；local source 同名覆盖
- update：内容变 → 重新生成 relink；不变 → up to date；`--all` 包含 dynamic；name 改变时旧链接删除；materialize agent 副本刷新
- list 显示 `cmd:`；remove 删链接/lock/配置；check-updates skip 提示
- 配置往返：两个 dynamic 包时 `skm install <repo>`，两个都保留
- `install --cmd`：写配置并安装；失败不写配置；已在配置中沿用 agents

手动验收：隔离路径下用 `tinyhost skill` 走 install --cmd / list / update / check-updates / 失败路径 / remove，证据放 `tmp/2026-11-15-dynamic-skill/`。

### 风险与待定

- 命令输出可能依赖环境变量（如 PATH），skm 被不同 shell 调用时结果可能不同；`sh -c` 继承当前环境，不做额外处理。
- repo 里 SKILL.md 的 `name` 同样没做路径校验，收尾时对照 known-issues 门槛决定是否登记。
