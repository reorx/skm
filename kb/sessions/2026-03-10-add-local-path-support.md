---
created: 2026-03-10
tags:
  - feature
  - local-path
  - config
  - bdd
---

# 为 SKM 添加 local_path 包源支持

## 概要

本次 session 为 SKM 添加了 `local_path` 作为 config 中 package 的替代来源。之前只支持 git repo URL，现在可以直接指向本地目录，skill 通过 symlink 链接到本地路径而非 clone 到 store_dir。local_path 包跳过所有 git 操作（check-updates、update）。按照 BDD 方法，先编写了 12 个行为测试，再实现功能，所有 60 个测试全部通过。

## 修改的文件

- **`src/skm/types.py`** — `SkillRepoConfig`: `repo` 改为 optional，新增 `local_path` 字段、`model_validator` 互斥校验、`is_local` 和 `source_key` 属性。`InstalledSkill`: `repo`/`commit` 改为 optional，新增 `local_path` 字段。
- **`src/skm/commands/install.py`** — 拆分为 `_install_local`（直接使用本地路径，无 clone/store_dir/commit）和 `_install_repo`（原有逻辑）。removal detection 使用 `repo or local_path` 作为 source key。
- **`src/skm/commands/check_updates.py`** — 跳过 `repo is None` 的 skill，输出 "Skipping local path package" 日志。
- **`src/skm/commands/update.py`** — 对 local_path skill 提前返回并输出提示信息。
- **`src/skm/commands/list_cmd.py`** — 显示 `local_path` 替代 `repo`，`commit` 为 None 时不显示 commit 行。
- **`tests/test_local_path.py`** — 新增 12 个 BDD 测试覆盖：config 校验互斥、local_path 安装/symlink/filter、lock 字段、check-updates 跳过、update 跳过。

## Git 提交记录

本次 session 无 git 提交。

## 注意事项

- `SkillRepoConfig` 的 `repo` 从必填改为 optional 是破坏性变更，但由于 `model_validator` 强制要求 `repo` 和 `local_path` 二选一，现有只用 `repo` 的配置文件和测试不受影响。
- local_path 的 skill 检测复用了 `detect_skills()`，该函数本身不依赖 git，对任意目录都能正常工作。
- lock 文件中 local_path 包的 `repo` 和 `commit` 为 null，反序列化时 Pydantic 自动处理。
- removal detection 中用 `old_skill.repo or old_skill.local_path` 匹配 configured_skill_keys，确保两种来源的 skill 都能正确检测移除。
