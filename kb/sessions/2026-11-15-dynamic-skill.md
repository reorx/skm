---
created: 2026-11-15
tags:
  - dynamic-skill
  - source-cmd
  - install
  - update
---

# 新增 dynamic skill：用 `source_cmd` 把 CLI 打印的 SKILL.md 装成 skill

## 概要

有些 CLI 自带 skill，要运行命令才能拿到内容，例如 `tinyhost skill` 会往 stdout 打印一份完整的 SKILL.md。这次新增 `source_cmd` 包类型：skm 用 `sh -c` 运行命令（不接 stdin，cwd 为 home，超时 60s），先在内存里校验输出（必须有 frontmatter，`name` 必须是安全的路径名），通过后写到 `<store>/_dynamic/<slug>-<hash8>/SKILL.md`，再走现有的 link 流程。install 只在还没生成过时运行命令，失败只打警告并跳过这个包，这样共享 skills.yaml 的设备即使没装这个 CLI，其余包也照常安装。update 每次都重跑命令，失败直接报错；内容变了才重新 link，name 变了会清掉旧链接。check-updates 跳过 dynamic skill，list 显示 `cmd:`，remove 会删掉链接、lock 条目和包。另外新增了 `skm install --cmd "<cmd>"`：先运行并校验，通过后才写 skills.yaml。顺带把 install 里三种来源重复的 link 循环提取成了 `_link_skills`，并修好 `_raw_pkg_source_key`：之前它认不出 `source_cmd`，保存配置时会丢掉 dynamic 包上的注释。测试先写，`tests/test_dynamic.py` 共 55 条，全量 307 passed（含 network）。在隔离路径下用真实的 `tinyhost skill` 走了一遍 install --cmd / list / list --all / update（未变和已变两种情况）/ check-updates / 二次 install / 命令不存在 / remove / verbose。

## 修改的文件

- `src/skm/dynamic.py`（新）：`dynamic_skill_dir`、`render_source_cmd`（运行并校验，返回文本）、`generate_dynamic_skill`（内容没变就不写，变了原地覆盖，返回是否有变化）、`load_dynamic_skill`；常量 `SOURCE_CMD_TIMEOUT`、`SAFE_SKILL_NAME_RE`、`SOURCE_CMD_ERRORS`。底层没有 try/except。
- `src/skm/types.py`：`SkillRepoConfig.source_cmd`，三种来源只能选一个；source_cmd 不能为空白，也不能和 `skills`/`skills_excludes`/`skills_dir`/`clone_strategy` 同时写；新增 `is_dynamic`；`source_key` 返回命令字符串。`InstalledSkill.source_cmd` 加上 `source` 属性。
- `src/skm/detect.py`：拆出 `parse_skill_name_text(text, origin)`。
- `src/skm/commands/install.py`：新增 `_install_package` 按来源分派，`_target_agents`（解析 agent 并对 ignored includes 发警告）和 `_link_skills`（逐个 agent link 并记 lock）三种来源共用；新增 `_install_dynamic` / `_prepare_dynamic_skill`；清理与合并改用 `.source`。
- `src/skm/commands/update.py`：dynamic 条目单独分组，新增 `_update_dynamic`。
- `src/skm/commands/check_updates.py`、`list_cmd.py`、`remove.py`：识别 `source_cmd`，用 `.source`。
- `src/skm/config.py`：`_raw_pkg_source_key` 加 `source_cmd` 分支。
- `src/skm/cli.py`：`install --cmd`，新增 `_install_cmd_source`；agent 选择提取为 `_choose_agents_config`，直接安装 repo 时也用它，行为不变。
- `tests/test_dynamic.py`（新）：config 校验、生成与校验、install、update、list/remove/check-updates、配置往返、`install --cmd`。
- `README.md`、`AGENTS.md`：新增 Dynamic skills 小节，更新配置示例、命令表、Key Paths、项目结构。
- `kb/plans/2026-11-15-dynamic-skill.md`（新）、`kb/known-issues.md`（新增一条，更新一条）。

## 注意事项

- 生成目录按命令字符串命名，`--store` 会一并隔离它；改了命令就换一个新目录，相当于重新生成。旧目录不会被删除，和 repo clone 一样留在 store 里。
- 原地 `write_text` 不换 inode，openclaw 这类 materialize agent 的硬链副本会自动同步；跨设备的 reflink/copy 副本则靠 update 时的 `force=True` 重建。
- install 遇到失败时这个包不进 lock，所以之前装过的链接会按"no longer in config"清掉。这只会在生成文件不存在时发生（第一次安装、store 被清空、命令改了），而这时链接本来就已失效。
- 校验 `_raw_pkg_source_key` 的测试最开始只比较数据，即使不修也能通过：key 没对上只会让这个包按新数据重建，数据不变，丢的是注释。所以改成断言注释保留，并确认过去掉修复后测试会失败。
- 这次之后，`save_lock` 会给 lock 文件里每个条目都加一行 `source_cmd: null`，第一次运行时会出现一次性的 diff。
- `install --cmd` 对已在配置里的命令也会重跑并刷新内容，和 `skm install <repo>` 对已 clone 的 repo 会 pull 是同一个语义；agents 沿用配置里的设置，不写配置。

## 遗留问题

- repo / local_path 来源的 SKILL.md `name` 没做路径校验，可能写到 agent 目录外面；已记入 `kb/known-issues.md`。
- `_update_dynamic` 清理旧路径时，没有排除其他包正在用的路径，和 `update.py` 原有的问题一样；已经补进 known-issues 里对应的那一条。
- 超时后只会 kill `sh`。命令里有管道时，孙进程可能变成孤儿继续运行，但 skm 自己不会卡住（Python 3.12 的 `subprocess.run` 超时后只 `wait()` 子进程）。目前没有处理。
- `_dynamic/` 里不再使用的旧目录没有清理机制。

## 相关文档

- [Dynamic skill 开发计划](../plans/2026-11-15-dynamic-skill.md) — 本次新建并按此实现
- [Known Issues](../known-issues.md) — 新增 skill name 校验一条，update 清理一条补充了 dynamic 的情况
- [Local sources session](2026-10-31-install-local-sources.md) — 参考：local source 覆盖逻辑（`LocalOverrides`）被 dynamic 包复用
