build skm, which is a skill manager that manage agent skills by a certral yaml config.

skm should be build with uv and python, use python modern packaing best practices. use click library to implement CLI.

skm can detect skills from a github repo. follow the patterns:
- find ./skills dir, if exists, start walk through  from ./skills; if not exists, start walk through from ./
- how to walk through: iterate the sub dirs, if a dir has SKILL.md, it's a skill, stop digging down that dir
- note that ./ may also contain a SKILL.md, in this case the repo itself is a singleton skill, and no need to start the walk through

## Config

config path: `~/.config/skm/skills.yaml`

see @skills.example.yaml for the config example:
- repo: github repo url
- skills: list of skill name to use in this repo. note that this is the name in skill frontmatter, not the skill dir's name.
- agents: configure which agents to install this skill. either `includes` or `excludes` is configured, by default install to all the known agents.

skills should be cloned to a central path `~/.local/share/skm/skills/`, then soft link to agents according to `agents:` option. when linking skills from the central path to the agent's skill dir, you should always use the skill's frontmatter name as the target dir name.


## Agents

currently support agents:
- standard dir: `~/.agents/skills`
- claude: `~/.claude/skills`
- codex: `~/.codex/skills`
- openclaw: `~/.openclaw/skills`

## CLI

- `skm install`: install/remove skills based on config, this command does not update an installed skill. a lock file (~/.config/skm/skills-lock.yaml`) will be generated or updated after install, representing the version (commit), linked pathes, and other states of installed skills.
- `skm check-updates`: check for each skills' repo to see if there's any updates, list the git log for each skill with new commits, similar to some nvim plugin managers like how lazyvim does
- `skm update <skill-name>`: update a skill and show changes, reflect on skills-lock.yaml
- `skm list`: list each installed skill with the pathes they are linked to.
