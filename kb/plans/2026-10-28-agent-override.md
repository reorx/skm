---
created: 2026-10-28
tags:
  - agents
  - config
  - list
  - install
  - update
---

# 在 skills.yaml 里覆盖内置 agent 的路径和安装方式，并统一各命令对 agent 的解析

## PRD

### 背景

SKM 把同一批 skill 装到多个 agent 的 skill 目录里。每个内置 agent 的目录和安装方式（软链或实体目录）现在写死在程序里，用户能调的只有两样：用 `agents.default` 选启用哪些 agent，用 Claude、Codex 的环境变量改它们的配置根目录。

这带来几类问题：

- **调不了安装方式和目录。** [Issue #4](https://github.com/reorx/skm/issues/4) 的用户，store 和 home 在不同的 Btrfs 子卷上，实体安装要靠 reflink 或复制回退，他更希望能直接改用软链。2026-10-23 起 `standard`（`~/.agents/skills`）改回软链，OpenClaw 也读这个目录，又会跳过指向目录外的软链；依赖它是实体目录的 OpenClaw 用户，现在只能改源码。[Issue #5](https://github.com/reorx/skm/issues/5) 和 [PR #7](https://github.com/reorx/skm/pull/7) 提的就是这件事，维护者的意见是复用 `skills.yaml` 的 `agents`，不新增配置文件。
- **列表显示的 agent 归属会错。** 目录名前缀相同时会认错 agent，例如 `~/.agents/skills-extra/demo` 被显示成 `standard`；不带 `--all` 的 `skm list` 也不认 `--agents-dir`。
- **直接安装时选 agent 会静默失效。** `skm install <source>` 的选择器列出全部内置 agent，勾选 `agents.default` 以外的 agent 不会装进去，也没有提示；直接接受预选，又会把当时的 default 名单写死进这个包的配置，以后改 `agents.default`，这个包不会跟着变。
- **改了 agent 配置后，update 留下孤儿安装。** 改了 agent 配置后先执行 `skm update <skill>`，它会装到新的目标，却不删旧位置上的安装，而且从此不再记录它，之后的 `skm install` 也清理不到。
- **Pi 不认它自己的配置根目录环境变量** `PI_CODING_AGENT_DIR`。

前两条 known issue 见 `kb/known-issues.md`，需求分析见 [PR 需求调研](../notes/2026-10-23-github-pr-requirements-research.md)。

### 目标

用户在 `skills.yaml` 里就能为内置 agent 指定 skill 目录和安装方式，不用改 SKM。install、update、list 对"有哪些 agent、各装在哪、怎么装"的判断完全一致，改了 agent 配置后，旧位置上 SKM 装过的东西会被清理干净。

### 功能与交互

#### 1. 在 skills.yaml 里覆盖内置 agent

在已有的 `agents` 下新增 `override`，按内置 agent 的名字写：

```yaml
agents:
  default:
    - claude
    - standard
    - openclaw
  override:
    standard:
      install_mode: materialize
    openclaw:
      path: ~/my-openclaw/skills
      install_mode: symlink
```

- `path`：这个 agent 的完整 skill 目录（skill 直接装在它下面），支持 `~`。注意它和环境变量含义不同：环境变量指的是 agent 的配置根目录，skill 目录是它下面的 `skills`。
- `install_mode`：`symlink`（软链）或 `materialize`（实体目录，由 SKM 自动选硬链、reflink 或复制）。
- 两项都可以单独写，没写的那项保持内置值。
- 内置默认值不变：`openclaw` 用实体目录，其余用软链。

出错时：

- `override` 里写了不认识的 agent 名字，所有需要读配置的命令都报错退出，提示列出已知的 agent。
- `install_mode` 不是这两个值之一、`path` 为空，同样报错退出，提示指出是哪个 agent 的哪一项。
- `override` 只能覆盖内置 agent，不能注册新 agent。

#### 2. 路径的优先级

一个 agent 最终用哪个目录，从高到低：

1. 命令行 `--agents-dir`（所有 agent 都装到 `<目录>/<agent 名>`，用于测试和试验）
2. `agents.override.<名字>.path`
3. agent 自己的环境变量：Claude 的 `CLAUDE_CONFIG_DIR`、Codex 的 `CODEX_HOME`、Pi 的 `PI_CODING_AGENT_DIR`，取 `<变量值>/skills`；变量未设置或为空时跳过
4. 内置目录

只覆盖 `install_mode` 不影响路径，设置了环境变量的话，路径仍然跟着环境变量走。

#### 3. 修改路径或安装方式之后

- **改 path**：下次执行 `skm install`，SKM 在旧位置装过的 skill 被删掉，在新位置重新装上，输出里列出被移除的旧路径（原因为 agent 配置变化）。只删 SKM 记录过的安装，用户自己放进去的文件和目录不动。
- **改 install_mode**：沿用现有行为。软链换成实体目录直接替换；实体目录换成软链时，副本内容和源完全一致就直接替换，有差异就先询问是否覆盖（`--force` 跳过询问）。
- **先执行 `skm update`**：上游有新提交、update 重新安装 skill 时，装到新目标，同时清理这些 skill 在旧位置上 SKM 记录过的安装。仓库已是最新时，update 和现在一样只输出 Already up to date，不动任何安装；此时 SKM 仍记得旧位置，迁移交给下一次 `skm install`。这一条对所有 agent 配置变化都成立（改 `agents.default`、改包的 includes/excludes、改 override）。
- **用 `skm install <source>` 重新安装已在配置里的包**：同样清理这个包的 skill 在旧位置上 SKM 记录过的安装。

#### 4. 列表里的 agent 归属

- `skm list` 显示每个 skill 装到了哪些 agent。判断依据是：安装位置所在的目录，和某个 agent 的 skill 目录**完全相同**，才算这个 agent 的。名字前缀相同的其他目录不再被误认。
- 判断用的 agent 目录和 install 用的完全一样：包括 override、环境变量、`--agents-dir`。`--all` 和不带 `--all` 都是如此。
- 不带 `--all` 时，按全部内置 agent 识别归属，不只限于 `agents.default` 里的（和现在一样）。`--all` 仍只扫描 default 范围内 agent 的目录（和现在一样）。
- 安装位置不属于任何当前配置下的 agent 时（例如改了 path 但还没重新 install），这一条不显示 agent 名，加 `-v` 仍能看到实际路径。
- 配置文件读不了（格式错误、override 写错）时，`skm list` 不报错退出：先打印一行黄色警告说明原因，再按内置 agent 的目录显示列表（`--all` 此时扫描全部内置 agent，因为读不到 default）。install、update 等会改动安装的命令仍然直接报错。

#### 5. 直接安装时的 agent 选择器

`skm install <source>` 在包还不在配置里、也没有用 `--agents-includes` / `--agents-excludes` 时，会让用户选 agent：

- 设置了 `agents.default`：只列出 default 里的 agent，全部预选。
- 没设置 `agents.default`：列出全部内置 agent，全部预选（和现在一样）。
- 保持全选确认：这个包的配置里不写 `agents`，以后它跟随 `agents.default` 变化。
- 去掉其中一部分：写入 `includes`，只含勾选的 agent。

#### 6. includes 里有不会生效的 agent 时给出警告

包级 `includes` 只能在 `agents.default` 范围内挑选。执行 `skm install` 或 `skm update` 时，如果某个包的 `includes` 里有不会生效的名字（不在 default 范围内，或者根本不是内置 agent），打印一行黄色警告，写明包名和被忽略的 agent，例如：

```
Warning: package https://github.com/foo/bar includes agents not in agents.default, ignored: openclaw
```

不修改配置文件，安装照常进行。`--agents-includes` 指定了 default 以外的 agent 时，同样走这条警告。

#### 7. Pi 的配置根目录环境变量

设置了 `PI_CODING_AGENT_DIR` 时，Pi 的 skill 目录变成 `<变量值>/skills`，优先级按第 2 节。

### 不做的事

- 通过 `override` 注册新的自定义 agent。
- 让包级 `includes` 超出 `agents.default` 的范围。
- 自动改写用户已有配置里不生效的 `includes`，只给警告。
- 新增查看 agent 解析结果的命令，`skm list --all` 已经按 agent 列出目录。
- 实体副本的同步规则：上游删掉的文件、源文件被替换式保存后副本变旧、install 卡在覆盖确认。这些单独立项，见 `kb/known-issues.md` 中 openclaw 一条。
- 修改内置 agent 的默认安装方式。

### 验收标准

**override**
- [ ] 没有 `agents.override` 的旧配置，install 结果和改动前一致（目录、安装方式、lock 内容）。
- [ ] 只写 `override.<名字>.path`，skill 装到该目录，安装方式保持内置值。
- [ ] 只写 `override.<名字>.install_mode`，安装方式改变，目录保持内置值；设置了对应环境变量时，目录仍然跟着环境变量走。
- [ ] `override.standard.install_mode: materialize` 后，`~/.agents/skills` 下是实体目录而不是软链。
- [ ] `path` 里的 `~` 被展开；lock 里记录的路径仍然把 home 写成 `~`。
- [ ] `override` 里写不认识的 agent 名、非法的 `install_mode`、空的 `path`，install 报错退出，提示指出具体问题，没有改动任何安装。

**优先级**
- [ ] 同时设置 `--agents-dir`、`override.path`、环境变量时，用 `--agents-dir`；去掉 `--agents-dir` 用 `override.path`；再去掉用环境变量；都没有用内置目录。

**修改之后**
- [ ] 改 `override.path` 后执行 `skm install`：旧位置上 SKM 装过的 skill 被删除，新位置装上，输出列出被移除的路径。
- [ ] 旧目录里用户自己放的文件或目录，在上一条之后仍然存在。
- [ ] 改 `override.path`、上游有新提交后先执行 `skm update <skill>`：新位置装上，旧位置上该 skill 的安装被删除，lock 只记录新位置。
- [ ] 改 `override.path` 后、上游没有新提交时执行 `skm update <skill>`：输出 Already up to date，旧位置的安装和 lock 都不变；之后 `skm install` 完成迁移。
- [ ] 从 `agents.default` 去掉一个 agent、上游有新提交后执行 `skm update <skill>`，该 agent 目录下这个 skill 被删除。
- [ ] 改 `override.path` 后执行 `skm install <source>` 重新安装这个包，旧位置上这个包的 skill 被删除。

**列表**
- [ ] lock 里路径为 `~/.agents/skills-extra/demo` 时，`skm list` 不把它显示成 `standard`。
- [ ] 用 `--agents-dir` 安装后，用同样的 `--agents-dir` 执行 `skm list`，能显示正确的 agent 名。
- [ ] 用 `override.path` 安装后，`skm list` 和 `skm list --all` 都显示正确的 agent 名。
- [ ] skill 装到了不在 `agents.default` 里、但仍是内置 agent 的目录时，`skm list` 能显示它的 agent 名。
- [ ] 配置文件写坏后，`skm list` 打印警告并照常列出 skill；`skm install` 报错退出。

**选择器**
- [ ] `agents.default: [claude, standard]` 时，选择器只列出这两个，且都已预选。
- [ ] 上一条直接确认后，配置里这个包没有 `agents` 字段；之后在 `agents.default` 加上 codex 再 `skm install`，这个包也装到 codex。
- [ ] 只勾选 claude 确认后，配置写入 `includes: [claude]`，只装到 claude。
- [ ] 没有设置 `agents.default` 时，选择器列出全部内置 agent，全部预选。

**includes 警告**
- [ ] 包的 `includes` 含 default 以外的 agent 时，`skm install` 打印警告，写明包名和被忽略的 agent，退出码为 0，配置文件未被修改。
- [ ] `includes` 含拼错的名字时，同样给出警告。
- [ ] `includes` 全在 default 范围内时，没有警告。

**Pi**
- [ ] 设置 `PI_CODING_AGENT_DIR=~/pi-home` 后，Pi 的 skill 装到 `~/pi-home/skills`；未设置时装到 `~/.pi/agent/skills`。

## Tech Design

### 现状

- **内置 agent 定义**分散在 `src/skm/types.py` 的三处：`_KNOWN_AGENTS_DEFAULTS`（名字 → 目录）、`_AGENT_ENV_OVERRIDES`（只有 claude、codex）、`AGENT_OPTIONS`（只有 openclaw 的 `use_hardlink`）。`KNOWN_AGENTS = _get_known_agents()` 在模块导入时读取环境变量，并且固定下来。
- **配置模型**：`DefaultAgentsConfig` 只有 `default`，它的 validator 拿 `KNOWN_AGENTS` 校验名字。`load_config()`（`src/skm/config.py`）直接执行 `SkmConfig(**data)`。pydantic 的 `ValidationError` 在 CLI 层没人捕获，配置写错时用户看到的是 traceback。
- **CLI 解析**：`src/skm/cli.py` 的 `_expand_agents(agents_dir, default_agents)` 返回 `dict[str, str]`（名字 → 展开后的目录）。install（配置模式和直接安装模式）、update、`list --all` 各自调用它。不带 `--all` 的 `list` 不调用，`run_list` 直接用 `KNOWN_AGENTS`。
- **安装**：`resolve_target_agents()`（`src/skm/linker.py`）在 default 范围内按包的 includes/excludes 过滤，includes 里多余的名字被静默丢掉。`link_skill(..., agent_name=...)` 通过 `_get_agent_option(agent_name, 'use_hardlink')` 决定装软链还是实体目录。调用方是 `src/skm/commands/install.py` 的 `_install_local`、`_install_repo`，以及 `src/skm/commands/update.py` 的 `_update_repo`。
- **清理旧安装**：只有 `run_install()` 会做。它比较旧 lock 和新 lock 的 `linked_to`，删掉旧 lock 里有、新结果里没有的路径（软链 unlink，目录 rmtree），输出 `Removing stale links`。`run_install_package()`（直接安装）在合并 lock 时直接丢掉这个 source 的旧条目；`_update_repo()` 用新的 `linked_paths` 覆盖 lock 条目。这两处都不删旧路径。另外，`_update_repo()` 在 `old_commit == new_commit` 时提前返回。
- **列表**：`_agent_name_from_link()`（`src/skm/commands/list_cmd.py`）对每个内置 agent 做 `expanded_link.startswith(expanded_base)`。
- **选择器**：`cli.install` 的直接安装分支里，`agent_names = list(KNOWN_AGENTS.keys())`，再按 default 预选。只要选中的集合不等于全部 5 个 agent，就写入 `includes`。
- **选择器组件**：`interactive_multi_select()`（`src/skm/tui.py`）在 `preselected=None` 时全部预选。

### 方案

把 agent 定义收拢成一张内置表，配置里的 override 用 pydantic 模型在加载时校验。新增 `src/skm/agents.py`，在每次命令执行时把"内置表 + override + 环境变量 + `--agents-dir`"解析成 `dict[str, ResolvedAgent]`（名字 → 最终目录和安装方式）。install、update、list 都从这一个函数拿结果，`KNOWN_AGENTS`、`AGENT_OPTIONS`、`_expand_agents` 全部删掉。两个 bug 修复、includes 警告和旧安装清理，都建立在这份统一的解析结果上。

关键决策：

- **内置表放在 `types.py`，解析函数放在新的 `agents.py`。** 配置模型的 validator 需要知道有哪些内置名字；如果内置表放在 `agents.py`，`types.py` 就得反过来 import 它，形成循环。读环境变量是运行时行为，不放进 `types.py`。否决的备选：照 PR #7 那样在 `load_config()` 里调用解析函数，只为了顺带校验（返回值不用）。校验应该随模型走，单独构造 `SkmConfig` 时也能生效。
- **区分两种模型：内置定义用 `AgentSpec`（目录模板、环境变量名、默认模式），解析结果用 `ResolvedAgent`（最终目录、模式）。** 否决的备选：PR #7 复用同一个 `AgentSpec`，再把 `path` 原地改成解析后的值。这样同一个字段在不同阶段含义不同，容易用错。
- **`link_skill()` 改成接收 `install_mode` 参数，不接收 agent 对象。** linker 只关心"装到哪个目录、用什么方式"，不需要了解 agent 模型；现有测试大多直接传字符串目录，改动最小。否决的备选：传 `ResolvedAgent`（PR #7 的做法）。
- **`AgentOverride` 设置 `extra='forbid'`。** 把 `install_mode` 拼成 `mode` 之类的笔误会直接报错，而不是被静默忽略。其他配置模型维持现状，不在这次收紧。
- **配置错误在 CLI 层统一转成 `click.ClickException`。** 符合"只在顶层处理错误"的约定。pydantic v2 的 `ValidationError` 是 `ValueError` 的子类，`load_config()` 自己抛的也是 `ValueError`，所以捕获 `ValueError` 就够了。
- **清理旧安装复用同一套规则：只删 lock 里记录过、这次没有再装的路径。** `run_install` 的清理逻辑抽成函数，`run_install_package` 复用；`_update_repo` 按 skill 粒度清理，直接调用 `unlink_skill()`。
- **includes 警告在解析出目标 agent 的地方打印**（`_install_local`、`_install_repo`、`_update_repo`），只针对正在处理的包。判断逻辑是 linker 里的一个纯函数，打印留给各命令，保持 linker 不输出。
- **内置默认值以 master 为准**：只有 openclaw 用实体目录，`standard` 用软链。不能照搬 PR #7 里 `standard` 的 `materialize`。

### 数据变动

**配置 `skills.yaml`**：`agents` 下新增可选的 `override`，见 PRD。旧配置不受影响，不需要迁移。

**`src/skm/types.py` 的模型**

```python
AgentInstallMode = Literal['symlink', 'materialize']

class AgentSpec(BaseModel):        # 内置定义
    path: str                      # 默认 skill 目录，可含 ~
    env_var: str | None = None     # 配置根目录环境变量，skill 目录为 $VAR/skills
    install_mode: AgentInstallMode = 'symlink'

class AgentOverride(BaseModel):    # skills.yaml 里的 agents.override.<name>
    model_config = ConfigDict(extra='forbid')
    path: str | None = None        # validator：不能是空串或纯空白
    install_mode: AgentInstallMode | None = None

class GlobalAgentsConfig(BaseModel):   # 取代 DefaultAgentsConfig
    default: list[str] | None = None   # validator：名字必须在 BUILTIN_AGENTS 里（沿用原文案 'Unknown agents: ...'）
    override: dict[str, AgentOverride] | None = None  # validator：key 必须在 BUILTIN_AGENTS 里

class ResolvedAgent(BaseModel):    # 运行时解析结果
    path: str                      # 展开后的 skill 目录
    install_mode: AgentInstallMode = 'symlink'

BUILTIN_AGENTS: dict[str, AgentSpec] = {   # 顺序即各处的展示顺序，与现在一致
    'standard': AgentSpec(path='~/.agents/skills'),
    'claude': AgentSpec(path='~/.claude/skills', env_var='CLAUDE_CONFIG_DIR'),
    'codex': AgentSpec(path='~/.codex/skills', env_var='CODEX_HOME'),
    'openclaw': AgentSpec(path='~/.openclaw/skills', install_mode='materialize'),
    'pi': AgentSpec(path='~/.pi/agent/skills', env_var='PI_CODING_AGENT_DIR'),
}
```

删除：`DefaultAgentsConfig`、`_KNOWN_AGENTS_DEFAULTS`、`_AGENT_ENV_OVERRIDES`、`_get_known_agents`、`KNOWN_AGENTS`、`AGENT_OPTIONS`，以及 `import os`。openclaw 和 standard 安装方式的来由，原来写在 `AGENT_OPTIONS` 上方的注释里，迁到 `BUILTIN_AGENTS` 上方。`SkmConfig.agents` 的类型改为 `GlobalAgentsConfig | None`。

**lock 文件**：格式不变。`InstalledSkill.linked_to` 的注释改为"安装路径"（不再只是软链）。

### 逻辑变动

**`src/skm/agents.py`（新增）**

- `resolve_agents(agents_config: GlobalAgentsConfig | None, agents_dir: str | None = None, default_only: bool = True) -> dict[str, ResolvedAgent]`
  - 名字集合：`default_only` 为真且配置了 `default` 时取 default 里的名字，否则取全部内置名字。顺序始终按 `BUILTIN_AGENTS`。
  - 目录：`agents_dir` → `Path(agents_dir).expanduser() / name`；`override.path` → `Path(path).expanduser()`；环境变量非空 → `Path(val).expanduser() / 'skills'`；否则 `Path(spec.path).expanduser()`。结果存为 `str`。
  - 模式：`override.install_mode`，没有就用 `spec.install_mode`。
- 可以拆出一个私有的 `_resolve_path(name, spec, override, agents_dir) -> str`，函数里不做异常处理。

**`src/skm/linker.py`**

- 删除 `_get_agent_option` 和对 `AGENT_OPTIONS` 的 import。
- `resolve_target_agents()` 的类型标注改为 `dict[str, ResolvedAgent]`，逻辑不变。
- 新增 `find_ignored_includes(agents_config, known_agents) -> list[str]`：返回 `includes` 里不在 `known_agents` 中的名字，保持原顺序；没有 includes 时返回 `[]`。
- `link_skill(skill_src, skill_name, agent_skills_dir, force=False, install_mode='symlink')`：把 `agent_name` 参数换成 `install_mode`，原来的 `if use_hardlink:` 改为 `if install_mode == 'materialize':`。docstring 里的 "hardlink tree" 改成 "materialized tree"。实体模式内部逻辑不动（同步规则不在本次范围）。

**`src/skm/commands/install.py`**

- `known_agents` 类型改为 `dict[str, ResolvedAgent]`。循环 `for agent_name, agent in target_agents.items()` 调用 `link_skill(skill.path, skill.name, agent.path, install_mode=agent.install_mode)`（包括 force 重试那一次）。
- `_install_local`、`_install_repo` 在 `resolve_target_agents()` 之后调用 `find_ignored_includes()`。有结果时，非 verbose 模式先 `_clear_progress()`，再输出黄色的 `  Warning: package <source> includes agents not in agents.default, ignored: a, b`。`<source>` 用 `repo_config.repo`，或 `compact_path` 处理过的 local path。
- 把 `run_install()` 里从 `# Remove stale links` 到计数结束的那段抽成 `_remove_stale_links(old_skills, new_lock_skills, configured_skill_keys) -> int`，行为和输出不变。
- `run_install_package()` 在合并 lock 的循环里，把属于这个 source、要被替换掉的旧条目收集起来，调用 `_remove_stale_links(replaced, new_lock_skills, configured_skill_keys)`。移除计数加进结尾的汇总输出（沿用 `run_install` 的 "removed N skills" 格式）。

**`src/skm/commands/update.py`**

- `known_agents` 类型改为 `dict[str, ResolvedAgent]`，`link_skill` 调用方式同 install。
- `resolve_target_agents()` 之后打印同样的 includes 警告。
- 每个 skill 重新链接后，`stale = [p for p in locked_skill.linked_to if p not in linked_paths]`。对每个路径，在 `Path(p).expanduser()` 是软链或目录时调用 `unlink_skill(path.name, str(path.parent))`，并输出红色的 `  Removed stale link <p> (agent config changed)`。`old_commit == new_commit` 的提前返回保留不动。

**`src/skm/commands/list_cmd.py`**

- 删除对 `KNOWN_AGENTS` 的 import。`_agent_name_from_link(link, known_agents)` 改为比较 `Path(link).expanduser().parent == Path(agent.path)`。
- `_format_skill(skill, known_agents, verbose)`、`run_list(lock_path, known_agents, verbose=False, skill_name=None)` 增加参数。`run_list_all` 改为读取 `agent.path`。

**`src/skm/cli.py`**

- 删除 `_expand_agents` 和对 `KNOWN_AGENTS` 的 import。
- 新增 `_load_config(config_path) -> SkmConfig`：捕获 `ValueError`，抛出 `click.ClickException(f'Invalid config {config_path}:\n{e}')`。install（两处）、update、list 读配置都改用它。`remove` 在 `run_remove` 内部读配置，不在本次范围。
- 新增 `_resolve_list_agents(config_path, agents_dir, default_only) -> dict[str, ResolvedAgent]`：配置文件不存在时静默用 `resolve_agents(None, agents_dir)`；读取失败（`ValueError`）时输出黄色的 `Warning: failed to load config, using built-in agents: <e>`，再用 `resolve_agents(None, agents_dir)`。
- `install` 配置模式：`agents = resolve_agents(config.agents, ctx.obj['agents_dir'])`。
- `install` 直接安装模式：读完配置后计算一次 `default_agents = resolve_agents(config.agents, ctx.obj['agents_dir'])`，两处 `run_install_package` 都用它。选择器改为 `agent_names = list(default_agents)`、`preselected=None`。判断"全选"时和 `agent_names` 比较，全选则 `agents_config = None`，否则写入 `includes`。
- `update`：`resolve_agents(config.agents, ctx.obj['agents_dir'])`。
- `list`：`--all` 用 `_resolve_list_agents(..., default_only=True)`，不带 `--all` 用 `default_only=False`，结果都传给 `run_list` / `run_list_all`。
- `--agents-dir` 的 help 文案把 "symlinks" 改为 "installs"。

### 实施步骤

每一步先写测试并确认失败（重构步骤则先确认现有测试全绿），再实现，最后 `uv run pytest -m "not network"` 全绿。每一步可以单独提交。

- [ ] **1. 统一 agent 解析（重构，外部行为不变，顺带支持 Pi 环境变量）**：`types.py` 加入新模型和 `BUILTIN_AGENTS`（先不加 `override` 字段）；新增 `agents.py` 和 `tests/test_agents.py`；linker、install、update、list、cli 改用 `ResolvedAgent` / `install_mode`；按"测试与验证"里的清单调整已有测试。
- [ ] **2. 列表归属精确匹配（TDD）**：先写前缀误判、`--agents-dir`、非 default 内置 agent 三个失败用例，再改 `_agent_name_from_link` 和 cli 的 list 分支。
- [ ] **3. 直接安装的选择器（TDD）**：先写选择器三个场景的 e2e 失败用例，再改 cli。
- [ ] **4. includes 警告（BDD）**：先写三个场景的用例，再加 `find_ignored_includes` 和打印。
- [ ] **5. `agents.override`（BDD）**：先写校验、路径、模式、优先级的用例，再加 `AgentOverride`、`GlobalAgentsConfig.override`、`resolve_agents` 里的 override 分支，以及 `_load_config` 的错误转换。
- [ ] **6. 清理旧安装（TDD）**：先写 install 迁移、update 迁移（有新提交和无新提交）、直接安装迁移的用例，再抽 `_remove_stale_links`，改 `run_install_package` 和 `_update_repo`。
- [ ] **7. list 读配置失败时降级**：先写用例，再加 `_resolve_list_agents` 的降级分支。
- [ ] **8. 文档和收尾**：
  - 更新 `AGENTS.md`：Project Structure 加 `agents.py`；Config Format 加 `override`；Known Agents 段改为描述 `BUILTIN_AGENTS`、优先级和 `install_mode`。
  - 更新 README：Config Format、Known Agents 表加环境变量列、Linking Strategies 里 `AGENT_OPTIONS` / `use_hardlink` 改为 `install_mode`。动手前先读 `~/.claude/docs/GITHUB_README.md`。
  - 从 `kb/known-issues.md` 删除"列表前缀误判"和"选择器"两条。
  - 写 session 总结。

### 测试与验证

已有测试的调整（步骤 1）：

- `tests/test_linker.py`：`agent_name='openclaw'` 改为 `install_mode='materialize'`，`agent_name='standard'` 去掉（默认就是 symlink）。`resolve_target_agents` 的三个用例把 dict 的值换成 `ResolvedAgent`。
- `tests/test_install.py`、`tests/test_local_path.py`：`agents = {'claude': str(...)}` 改为 `{'claude': ResolvedAgent(path=str(...))}`。`test_install_uses_env_override_path_in_lock` 删掉对 `skm.cli.KNOWN_AGENTS` 的 monkeypatch（现在运行时读环境变量，不需要它了）。
- `tests/test_list_cmd.py`：不再 monkeypatch `KNOWN_AGENTS`，改为给 `run_list` 传 `known_agents`。
- `tests/test_config.py`：`Unknown agents` 用例保持通过。

PRD 验收标准对应的用例（e2e 都在 `tests/test_cli_e2e.py`，用 `_cli_args` / `_write_config` 隔离；需要真实 home 路径时 monkeypatch `HOME`，并且不传 `--agents-dir`，做法参照 `test_install_uses_env_override_path_in_lock`）：

| 验收项 | 用例 |
|---|---|
| 旧配置行为不变 | 现有测试全绿 |
| 只写 path / 只写 install_mode / env + mode | `test_agents.py`：`resolve_agents` 的单元用例；e2e：override.path 装到指定目录且为软链 |
| standard 改 materialize | e2e：`override.standard.install_mode: materialize` 后，`<dir>/standard/<skill>` 是目录而不是软链（`--agents-dir` 下也适用，因为模式与路径无关） |
| `~` 展开与 lock 压缩 | e2e：monkeypatch `HOME`，`override.path: ~/custom/skills`，断言实际目录和 lock 里的 `~/custom/skills/<skill>` |
| 非法 override 报错 | `test_config.py`：未知名字、`install_mode: copy`、`path: ''`、多余字段 `mode:` 都抛 `ValidationError`；e2e：`install` 退出码非 0，输出含 `Invalid config`，agent 目录未被创建 |
| 优先级四层 | `test_agents.py`：参数化组合 `agents_dir`、override.path、环境变量 |
| install 迁移、保留用户文件 | e2e：install → 改 override.path → install；旧位置软链消失，旧目录里手放的 `manual/` 还在，输出含 `Removing stale links` |
| update 迁移（有新提交） | e2e：install → 改 override.path → 上游提交 → `update <skill>`；新位置存在，旧位置消失，lock 只含新路径 |
| update 无新提交不动 | e2e：install → 改 override.path → `update <skill>`；输出 `Already up to date`，旧位置和 lock 不变 |
| default 去掉 agent 后 update | e2e：default `[claude, codex]` install → 改为 `[claude]` → 上游提交 → update；codex 下该 skill 消失 |
| 直接安装重装迁移 | e2e：monkeypatch 选择器，`install <repo>` → 改 override.path → 再次 `install <repo>`；旧位置消失 |
| 列表前缀 / `--agents-dir` / override / 非 default 内置 agent | `test_list_cmd.py`：`~/.agents/skills-extra/demo` 不显示 standard；非 default 的内置 agent 路径能显示名字。e2e：`--agents-dir` 下 install 后 list 显示 agent 名；override.path 下 `list` 和 `list --all` 都显示 agent 名 |
| 配置损坏 | e2e：install 后把配置改坏（override 写未知名字），`list` 退出码 0、输出含警告和 skill 名；`install` 退出码非 0 |
| 选择器四个场景 | e2e：monkeypatch `skm.cli.interactive_multi_select`，记录传入的 items 和 preselected；断言列出的名字、`preselected is None`、写入的配置、实际安装目录，以及加 codex 后再 install 能装到 codex |
| includes 警告三个场景 | e2e：`includes: [claude, openclaw]`（default 为 `[claude]`）、`includes: [claud]`、`includes: [claude]`；断言警告文案和包名、退出码 0、配置文件内容不变 |
| Pi 环境变量 | `test_agents.py`：设置和不设置 `PI_CODING_AGENT_DIR` |

人工验收：本机执行一次 `uv run skm --config <tmp>/skills.yaml --lock <tmp>/lock.yaml --store <tmp>/store install`，配合 `override` 把某个 agent 指向 `<tmp>` 下的目录，确认真实终端里选择器、警告和清理输出的显示没有问题（主要是 progress 行和警告的交错）。不碰真实的 `~/.config/skm`。

### 风险与待定

- **清理时会 rmtree 实体目录**：沿用 `run_install` 现有的做法，旧位置如果是实体目录且被用户改过，清理时也会删掉。这次把同样的行为扩展到 update 和直接安装。要做到"有改动先确认"，依赖实体副本同步规则那个单独的立项。
- **路径比较只做 pathlib 规范化**：`Path` 会去掉末尾斜杠和 `.`，但不会解析 `..`，也不跟随软链。lock 路径和 agent 目录出自同一套解析，正常情况下一致；用户在 override 里写 `..` 或经软链的目录时，list 可能认不出归属，只影响显示，不影响安装。
- **改配置后 list 的显示**：改了 override.path 但还没 install 时，lock 里的旧路径不属于任何 agent，list 不显示 agent 名（PRD 已写明）。
- **progress 行和警告交错**：非 verbose 模式下，进度行写在 stderr，警告写在 stdout。警告前必须先 `_clear_progress()`，否则会接在进度行后面。人工验收时重点看。
- **PR #7 的署名**：实现参考了 PR #7 的思路（统一解析、父目录比较、选择器只列 default）。提交时可以考虑加 `Co-authored-by`，由用户决定。
