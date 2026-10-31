---
created: 2026-10-31
tags:
  - install
  - local-sources
  - multi-device
---

# 新增 `skm install --local`：每台设备各自的本地 skill 源，同名时本地源优先

## 概要

`~/.config/skm` 放在 git 里多台设备共享时，`skills.yaml` 只能全设备一致，无法让某台机器额外装一些只属于它的 skill。新增 `skm install --local <dir>`：把目录软链到 `skills.yaml` 同级的 `local_sources/<name>` 并立即安装，不写 `skills.yaml`；之后每次全量 `skm install` 都会扫描 `local_sources/`，把每个可用条目当作 `local_path:` 包安装（全部 skill、默认 agents）。`local_sources/` 里自动写一个内容为 `*` 的 `.gitignore`，目录本身不会进 git，不依赖用户仓库根 `.gitignore`。验收时发现本地源和 skills.yaml 同名的 skill 每次 install 都来回替换（openclaw 下还会弹确认、非终端崩溃），用户定为"本地源优先，并在安装时输出覆盖关系"：被覆盖的 skill 在其他包里跳过、不进 lock，每次 install 末尾打印 `Local source overrides` 段落。行为测试先行（`tests/test_local_sources.py` 共 32 条），全量 252 passed；隔离脚本实机走了 install / list / remove / 删链接 / 同名覆盖（含 openclaw）。

## 修改的文件

- `src/skm/local_sources.py`（新）：`get_local_sources_dir`（`skills.yaml` 的父目录 + `local_sources`）、`scan_local_sources`（返回可用/损坏条目，忽略点文件）、`add_local_source`（目标转绝对路径；同目标复用已有条目；重名加 `-2`、`-3` 后缀；写 `.gitignore`）、`is_local_source_path`、`find_configured_duplicate`。
- `src/skm/cli.py`：所有 `run_install_package` 调用（`--local`、`install <source>`）都传入 local sources，直接安装的流程不打印悬空链接等警告（`warn=False`）。`install` 新增 `--local` 选项，与 SOURCE、`--agents-includes/excludes` 互斥；`_install_local_source` 先探测 skill（没有就报错且不建链接；目录已是 skills.yaml 的 local_path 时提示后退出），再建链接并用 `run_install_package` 只安装这个源；全量 install 用 `_local_source_packages` 生成包列表，悬空链接和与 skills.yaml 重复的条目会给出警告后跳过；没有 `skills.yaml` 但有 local sources 时用空配置继续执行。
- `src/skm/commands/install.py`：`run_install` 新增 `local_sources` 参数，排在 `config.packages` 之后处理，不会被保存进配置。新增 `LocalOverrides`（skill 名 → 拥有它的本地源，以及覆盖记录）：`_collect_local_overrides` 预先探测本地源，`_install_local` / `_install_repo` 用 `_drop_overridden` 跳过被覆盖的 skill，`_print_overrides` 输出覆盖关系；`run_install_package` 也接收 `local_sources`，作为胜出的本地源时会接管其他来源的同名 lock 条目。
- `src/skm/commands/remove.py`：`run_remove` 新增 `local_sources_dir` 参数；移除的 skill 来自本地源时，若它是该源最后一个已安装的 skill，就删掉 `local_sources` 里的链接（只删软链，不碰目标目录）；否则警告下次 install 会装回来。
- `src/skm/types.py`：新增常量 `LOCAL_SOURCES_DIRNAME`。
- `tests/test_local_sources.py`（新）：覆盖 `--local` 建链/lock/gitignore/不写配置/相对路径/幂等/重名/无 skill/与配置重复/参数互斥，全量 install 合并、删链接清理、悬空链接、无 skills.yaml，以及 remove 的两种情况。
- `README.md`：新增 "Device-local skills" 小节、命令表一行、同步行为和 Key Paths 说明。
- `AGENTS.md`：项目结构、Key Paths、CLI 命令和新的 Local Sources 小节。
- `kb/known-issues.md`：登记 skills.yaml 包之间同名来回替换的问题；openclaw 条目补充本地覆盖开始/结束时弹确认的场景。
- `kb/todo.md`（新）：记录 `skills.local.yaml` 覆盖层的想法（用户要求，暂不做）。

## 注意事项

- lock 里的 `local_path` 记录的是条目路径（`~/.config/skm/local_sources/<name>`），不是解析后的目标；agent 软链也经由这个条目指向源目录。好处：`skm list` 一眼能看出哪些是本机专属的 skill；`skm remove` 也靠这个识别本地源；重新指向条目后，agent 链接自动跟着走。
- `local_sources/` 的位置跟随 `--config` 而不是写死 `CONFIG_DIR`，所以测试和手动实验只需 `--config` 就能完全隔离，不必再加 CLI 参数。
- `--local` 的目标统一 `resolve()` 成绝对路径，避开 known-issues 里相对 `local_path` 导致软链悬空的问题（那条针对的是 `skm install <相对路径>`，仍未修）。
- 删除本地源的方式：删掉条目再 `skm install`，靠已有的 declarative 清理移除链接，清理原因会显示为 "no longer in config"。
- 刻意没做的：`--local` 不支持 `skills` 过滤和 agent 过滤，因为本地源没有地方存这些设置。用户已认可 `skills.local.yaml` 覆盖层的方向，记在 `kb/todo.md`。
- 覆盖优先级靠"先探测、再跳过"实现，不依赖处理顺序：被覆盖的 skill 根本不链接，所以不会出现一次 install 里先链上再换掉的情况，也不会触发 materialize 的覆盖确认。被覆盖的 skill 不写进 lock，`update` 只重新链接 lock 里的条目，因此不需要改动。
- 覆盖提示每次 install 都打印（即使 up to date），用来提醒本机还有覆盖在生效，避免共享配置更新了却不见效时找不到原因。

## 遗留问题

- skills.yaml 包之间同名仍会来回替换（本地源相关的同名已解决），已登记 `kb/known-issues.md`。
- openclaw（materialize）在本地覆盖开始和结束时各弹一次覆盖确认，因为原副本属于另一个来源；已并入 known-issues 的 openclaw 条目。
- `skm remove` 删掉一个覆盖了共享版本的本地 skill 后，共享版本要等下次 `skm install` 才会恢复，remove 不会提示这一点。
- 全量 install 清理本地源链接时，原因文案是 "no longer in config"，对本地源不太准确；摘要里的 "removed N skills" 计的是链接数而不是 skill 数（原有行为）。
- `skm list` 对本地路径来源仍标为 `repo:`（原有行为）。

## 相关文档

- [TODO](../todo.md) — 新建，记录 `skills.local.yaml` 想法
- [Known Issues](../known-issues.md) — 本次新增同名 skill 来回替换一条
- [local_path 支持](2026-03-10-add-local-path-support.md) — 本地源复用的 `local_path` 安装逻辑来源
