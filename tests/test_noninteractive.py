"""BDD tests for running `skm install` without a person at the keyboard.

Two ways to get there:
- `-y/--yes` skips the skill and agent pickers and takes their defaults.
- When stdin is not a terminal (scripts, coding agents), every prompt falls back
  to its default instead of waiting for a keypress that never comes.

The default for a picker is "everything checked"; picking every agent stores no
agent filter, so the package follows `agents.default`. The default for the
"override existing directory?" prompt is No.
"""

import io
import shlex
import subprocess
from io import StringIO
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from ruamel.yaml import YAML

from skm.cli import cli
from skm.commands.install import _confirm_override
from skm.tui import interactive_multi_select

_yaml = YAML()
_yaml.default_flow_style = False

DEFAULT_AGENTS = {'default': ['claude', 'codex']}


# --- helpers ---


def _cli_args(tmp_path: Path) -> list[str]:
    return [
        '--config',
        str(tmp_path / 'config' / 'skills.yaml'),
        '--lock',
        str(tmp_path / 'config' / 'skills-lock.yaml'),
        '--store',
        str(tmp_path / 'store'),
        '--agents-dir',
        str(tmp_path / 'agents'),
    ]


def _invoke(tmp_path: Path, *args: str):
    return CliRunner().invoke(cli, [*_cli_args(tmp_path), *args])


def _config_path(tmp_path: Path) -> Path:
    return tmp_path / 'config' / 'skills.yaml'


def _write_config(tmp_path: Path, packages: list[dict], agents: dict | None = None) -> None:
    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {'packages': packages}
    if agents is not None:
        data['agents'] = agents
    buf = StringIO()
    _yaml.dump(data, buf)
    config_path.write_text(buf.getvalue())


def _load_config(tmp_path: Path) -> dict:
    return _yaml.load(_config_path(tmp_path))


def _locked_names(tmp_path: Path) -> set[str]:
    data = _yaml.load(tmp_path / 'config' / 'skills-lock.yaml') or {}
    return {s['name'] for s in data.get('skills', [])}


def _cat_cmd(tmp_path: Path, name: str = 'tinyhost') -> str:
    out = tmp_path / 'out.md'
    out.write_text(f'---\nname: {name}\ndescription: generated {name}\n---\n# {name}\n')
    return f'cat {shlex.quote(str(out))}'


def _make_skill_repo(base: Path, repo_name: str, names: list[str]) -> Path:
    repo = base / repo_name
    repo.mkdir(parents=True)
    for name in names:
        skill_dir = repo / 'skills' / name
        skill_dir.mkdir(parents=True)
        (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test skill {name}\n---\n# {name}\n')
    subprocess.run(['git', 'init'], cwd=repo, capture_output=True, check=True)
    return repo


def _linked(tmp_path: Path, agent: str, skill: str) -> bool:
    return (tmp_path / 'agents' / agent / skill).is_symlink()


@pytest.fixture
def no_keypress(monkeypatch):
    """Fail fast instead of hanging if anything still waits for a key."""

    def boom():
        raise AssertionError('read a keypress without a terminal')

    monkeypatch.setattr(click, 'getchar', boom)


@pytest.fixture
def no_picker(monkeypatch):
    """Fail if the interactive picker is opened at all."""

    def boom(*args, **kwargs):
        raise AssertionError('opened the interactive picker')

    monkeypatch.setattr('skm.cli.interactive_multi_select', boom)


@pytest.fixture
def piped_stdin(monkeypatch):
    monkeypatch.setattr('sys.stdin', io.StringIO(''))


# --- prompts without a terminal ---


class TestPromptsWithoutTerminal:
    def test_picker_checks_everything_by_default(self, piped_stdin, no_keypress):
        assert interactive_multi_select(['a', 'b', 'c'], header='Select agents:') == [0, 1, 2]

    def test_picker_keeps_the_preselection(self, piped_stdin, no_keypress):
        assert interactive_multi_select(['a', 'b', 'c'], preselected={2, 0}) == [0, 2]

    def test_picker_says_what_it_picked(self, piped_stdin, no_keypress, capsys):
        interactive_multi_select(['claude', 'codex'], header='Select agents:')

        out = capsys.readouterr().out
        assert 'Select agents:' in out
        assert 'claude, codex' in out
        assert 'terminal' in out

    def test_override_prompt_answers_no(self, piped_stdin, no_keypress, capsys):
        assert _confirm_override('  ~/.claude/skills/foo exists. Override?') is False
        assert '--force' in capsys.readouterr().out


# --- install --cmd ---


class TestInstallCmd:
    def test_yes_skips_the_picker_and_follows_default_agents(self, tmp_path, no_picker):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        cmd = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd, '-y')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'source_cmd': cmd}]
        assert _linked(tmp_path, 'claude', 'tinyhost')
        assert _linked(tmp_path, 'codex', 'tinyhost')

    def test_long_flag_works_too(self, tmp_path, no_picker):
        cmd = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd, '--yes')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'source_cmd': cmd}]

    def test_agents_flag_still_wins_over_yes(self, tmp_path, no_picker):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        cmd = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd, '-y', '--agents-includes', 'claude')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'source_cmd': cmd, 'agents': {'includes': ['claude']}}]
        assert not _linked(tmp_path, 'codex', 'tinyhost')

    def test_without_terminal_follows_default_agents(self, tmp_path, no_keypress):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        cmd = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd)

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'source_cmd': cmd}]
        assert _linked(tmp_path, 'claude', 'tinyhost')
        assert _linked(tmp_path, 'codex', 'tinyhost')
        assert 'terminal' in result.output


# --- install <source> ---


class TestInstallSource:
    def test_yes_installs_every_skill_to_default_agents(self, tmp_path, no_picker):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        repo = _make_skill_repo(tmp_path, 'my-skills', ['skill-a', 'skill-b'])

        result = _invoke(tmp_path, 'install', str(repo), '-y')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'local_path': str(repo)}]
        assert _locked_names(tmp_path) == {'skill-a', 'skill-b'}
        assert _linked(tmp_path, 'codex', 'skill-b')

    def test_yes_with_skill_name_installs_just_that_skill(self, tmp_path, no_picker):
        repo = _make_skill_repo(tmp_path, 'my-skills', ['skill-a', 'skill-b'])

        result = _invoke(tmp_path, 'install', str(repo), 'skill-a', '-y')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'local_path': str(repo), 'skills': ['skill-a']}]
        assert _locked_names(tmp_path) == {'skill-a'}

    def test_without_terminal_installs_every_skill_to_default_agents(self, tmp_path, no_keypress):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        repo = _make_skill_repo(tmp_path, 'my-skills', ['skill-a', 'skill-b'])

        result = _invoke(tmp_path, 'install', str(repo))

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'local_path': str(repo)}]
        assert _locked_names(tmp_path) == {'skill-a', 'skill-b'}


# --- existing directories ---


class TestExistingDirectory:
    def test_without_terminal_a_real_directory_is_kept(self, tmp_path, no_keypress):
        _write_config(tmp_path, [], {'default': ['claude']})
        existing = tmp_path / 'agents' / 'claude' / 'tinyhost'
        existing.mkdir(parents=True)
        (existing / 'SKILL.md').write_text('mine')
        cmd = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd, '-y')

        assert result.exit_code == 0, result.output
        assert not existing.is_symlink()
        assert (existing / 'SKILL.md').read_text() == 'mine'
        assert '--force' in result.output
