# Known Issues

> 当前影响使用或稳定性、仍待处理的问题；解决后删除，处理结果写入 KB。

## openclaw：源文件被替换式保存后硬链副本变旧，install 卡在覆盖确认

- 记录：2026-10-23，standard 改为软链时确认 openclaw 仍走硬链（内置 `install_mode: materialize`）。
- 编辑器、agent 的 Edit 工具和 `sed -i` 保存时会换掉 inode，`~/.openclaw/skills` 里的副本还是旧内容，源里新增的文件和点开头的文件也不会带过去。之后 `skm install` 判定副本"不是受管副本"，逐个询问是否覆盖；非终端环境下直接报错退出。只影响启用了 openclaw 的用户，本机目前没启用。
- 处理方向：OpenClaw 新版支持 `skills.load.allowSymlinkTargets`，配置 skm store 和 local_path 目录后也许可以改回软链，需要实测；或者把 lock 里记录过的副本直接当作受管副本刷新，前提是先确认副本里没有只存在于副本的改动。

## update：两个包提供同名 skill 时，清理会删掉另一个包正在用的安装

- 记录：2026-10-29，agent override 评审第 5 条；复现场景 `update_shared_path`（`tmp/2026-10-29-agent-override-review/repro.py`）。
- 仓库 A、B 都有 `demo`，后装的 B 占了 `codex/demo`。给 A 加 `excludes: [codex]`，A 有新提交后执行 `skm update`，B 的 `codex/demo` 被删，lock 仍记录 B 装在 codex，下次 `skm install` 才恢复。直接安装和全量 install 会保护其他包仍在用的路径，只有 `update.py` 的清理不会。
- 处理方向：update 清理时排除 lock 里其他条目的 `linked_to`，最好复用 `install.py` 的 `_remove_stale_links`。

## 相对 local_path：软链目标相对于安装目录，导致 skill 不可读

- 记录：2026-10-28，agent override 的隔离终端验收发现。
- `skm install tmp/.../source` 将相对路径原样写入 local_path 并作为软链目标，系统从 agent 安装目录解析该目标，导致 dangling symlink；CLI 仍然报告安装成功。已有 `cli.py` / `linker.py` 路径处理即如此，与 override 无关。
- 复现：`tmp/2026-10-28-agent-override/manual/`；初次安装后的 `readlink new-claude/override-demo` 返回 `tmp/2026-10-28-agent-override/manual/source`，从该目标目录无法访问源文件。把配置里的 local_path 改成绝对路径并重新 install 后文件可读。
- 临时方式：使用绝对路径或 `~/...`。后续应先补相对源路径的失败测试，再在源路径解析时统一转为绝对路径。

## install：两个包提供同名 skill 时，每次 install 都来回替换，启用 openclaw 时会卡在覆盖确认

- 记录：2026-10-31，`skm install --local` 验收时发现；复现脚本 `tmp/2026-10-31-local-sources/same_name.sh`。
- 软链 agent 下，每次 `skm install` 先由前一个包换上自己的链接，后一个包再换回去，结果每次都报 "added 2 skills"，最终谁生效只取决于处理顺序（local sources 排在 skills.yaml 之后，所以本地源总是赢）。openclaw 用 materialize 时，后一个包发现副本内容不同就弹覆盖确认；非终端环境下 `click.getchar` 打开 `/dev/tty` 失败，抛出 traceback，lock 也不会保存。这个问题对任意两个同名包都存在，但"本机放一份开发版覆盖共享配置里的同名 skill"正是 local sources 的典型用法，碰到的概率高了很多。
- 处理方向：需要先定语义。一种做法是 local source 优先：install 跳过 skills.yaml 里同名的 skill 并提示一次，`update` 重新链接时同样跳过；另一种是检测到跨包同名就直接报错。同类问题另见上面 update 清理那一条。
