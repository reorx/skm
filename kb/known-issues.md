# Known Issues

> 当前影响使用或稳定性、仍待处理的问题；解决后删除，处理结果写入 KB。

## openclaw：源文件被替换式保存后硬链副本变旧，install 卡在覆盖确认

- 记录：2026-10-23，standard 改为软链时确认 openclaw 仍走硬链（内置 `install_mode: materialize`）。
- 编辑器、agent 的 Edit 工具和 `sed -i` 保存时会换掉 inode，`~/.openclaw/skills` 里的副本还是旧内容，源里新增的文件和点开头的文件也不会带过去。之后 `skm install` 判定副本"不是受管副本"，逐个询问是否覆盖；非终端环境下直接报错退出。只影响启用了 openclaw 的用户，本机目前没启用。
- 处理方向：OpenClaw 新版支持 `skills.load.allowSymlinkTargets`，配置 skm store 和 local_path 目录后也许可以改回软链，需要实测；或者把 lock 里记录过的副本直接当作受管副本刷新，前提是先确认副本里没有只存在于副本的改动。

## 相对 local_path：软链目标相对于安装目录，导致 skill 不可读

- 记录：2026-10-28，agent override 的隔离终端验收发现。
- `skm install tmp/.../source` 将相对路径原样写入 local_path 并作为软链目标，系统从 agent 安装目录解析该目标，导致 dangling symlink；CLI 仍然报告安装成功。已有 `cli.py` / `linker.py` 路径处理即如此，与 override 无关。
- 复现：`tmp/2026-10-28-agent-override/manual/`；初次安装后的 `readlink new-claude/override-demo` 返回 `tmp/2026-10-28-agent-override/manual/source`，从该目标目录无法访问源文件。把配置里的 local_path 改成绝对路径并重新 install 后文件可读。
- 临时方式：使用绝对路径或 `~/...`。后续应先补相对源路径的失败测试，再在源路径解析时统一转为绝对路径。
