"""BDD tests for `skm install <source> [skill_name]` — direct source arguments.

All tests use --config, --store, --lock, and --agents-dir to operate
entirely within tmp_path, never touching real agent directories.
"""

import subprocess
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from ruamel.yaml import YAML

from skm.cli import cli

_yaml = YAML()
_yaml.default_flow_style = False


def _yaml_dump(data) -> str:
    buf = StringIO()
    _yaml.dump(data, buf)
    return buf.getvalue()


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 't@t.com'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.name', 'T'], cwd=path, capture_output=True, check=True)


def _make_skill_repo(base: Path, repo_name: str, skills: list[dict]) -> Path:
    repo = base / repo_name
    _init_git_repo(repo)
    for skill in skills:
        name = skill['name']
        if skill.get('subdir', True):
            skill_dir = repo / 'skills' / name
        else:
            skill_dir = repo
        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test skill {name}\n---\n# {name}\n')
    subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
    subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True, check=True)
    return repo


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


def _write_config(tmp_path: Path, repos: list[dict], agents: dict | None = None) -> Path:
    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {'packages': repos}
    if agents is not None:
        data['agents'] = agents
    config_path.write_text(_yaml_dump(data))
    return config_path


def _load_config(tmp_path: Path) -> dict:
    config_path = tmp_path / 'config' / 'skills.yaml'
    if not config_path.exists():
        return {}
    return _yaml.load(config_path) or {}


def _load_lock(tmp_path: Path) -> dict:
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    if not lock_path.exists():
        return {'skills': []}
    return _yaml.load(lock_path) or {'skills': []}


class TestInstallFromLocalPath:
    """Scenario: skm install <local_path> with interactive selection."""

    def test_install_local_path_all_skills_all_agents(self, tmp_path):
        """All skills selected, all agents selected → config updated, skills installed."""
        repo = _make_skill_repo(
            tmp_path,
            'my-skills',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
            ],
        )
        # No config file exists yet

        # Mock interactive_multi_select: first call selects all skills, second selects all agents
        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.side_effect = [
                [0, 1],  # select all skills
                [0, 1, 2, 3, 4],  # select all agents
            ]
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output
        assert 'skill-a' in result.output
        assert 'skill-b' in result.output
        assert 'added 2 skills' in result.output

        # Config file should be created
        config = _load_config(tmp_path)
        assert len(config['packages']) == 1
        assert config['packages'][0]['local_path'] == str(repo)

        # Lock file should have both skills
        lock = _load_lock(tmp_path)
        names = {s['name'] for s in lock['skills']}
        assert names == {'skill-a', 'skill-b'}

    def test_install_local_path_subset_skills(self, tmp_path):
        """Only some skills selected interactively."""
        repo = _make_skill_repo(
            tmp_path,
            'my-skills',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
                {'name': 'skill-c'},
            ],
        )

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.side_effect = [
                [0, 2],  # select skill-a and skill-c only
                [0, 1, 2, 3, 4],  # all agents
            ]
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        assert set(pkg['skills']) == {'skill-a', 'skill-c'}


class TestInstallFromSourceWithSkillName:
    """Scenario: skm install <source> <skill_name>."""

    def test_install_specific_skill(self, tmp_path):
        """Single skill specified by name, no interactive prompt for skills."""
        repo = _make_skill_repo(
            tmp_path,
            'my-skills',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
            ],
        )

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.return_value = [0, 1, 2, 3, 4]  # agents selection only
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo), 'skill-a'])

        assert result.exit_code == 0, result.output
        assert 'skill-a' in result.output
        assert 'added 1 skill' in result.output

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        assert pkg['skills'] == ['skill-a']

    def test_install_nonexistent_skill_name(self, tmp_path):
        """Skill name not found in source → error."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo), 'no-such'])

        assert result.exit_code != 0
        assert 'not found' in result.output.lower()


class TestInstallWithAgentsFlags:
    """Scenario: --agents-includes / --agents-excludes flags."""

    def test_agents_excludes_skips_interactive(self, tmp_path):
        """--agents-excludes sets agents config directly, no interactive prompt."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.return_value = [0]  # skill selection
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    *_cli_args(tmp_path),
                    'install',
                    str(repo),
                    '--agents-excludes',
                    'openclaw,standard',
                ],
            )

        assert result.exit_code == 0, result.output

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        assert pkg['agents']['excludes'] == ['openclaw', 'standard']

        # Only claude and codex should have symlinks
        assert (tmp_path / 'agents' / 'claude' / 'skill-a').is_symlink()
        assert (tmp_path / 'agents' / 'codex' / 'skill-a').is_symlink()
        assert not (tmp_path / 'agents' / 'openclaw' / 'skill-a').exists()

    def test_agents_includes(self, tmp_path):
        """--agents-includes limits to specific agents."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.return_value = [0]  # skill selection
            runner = CliRunner()
            result = runner.invoke(
                cli,
                [
                    *_cli_args(tmp_path),
                    'install',
                    str(repo),
                    '--agents-includes',
                    'claude',
                ],
            )

        assert result.exit_code == 0, result.output

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        assert pkg['agents']['includes'] == ['claude']

    def test_both_includes_and_excludes_error(self, tmp_path):
        """Both --agents-includes and --agents-excludes → error."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                *_cli_args(tmp_path),
                'install',
                str(repo),
                '--agents-includes',
                'claude',
                '--agents-excludes',
                'openclaw',
            ],
        )

        assert result.exit_code != 0
        assert 'Cannot specify both' in result.output

    def test_agents_includes_unknown_agent_continues_silently(self, tmp_path):
        """Unknown agent in --agents-includes should keep old silent filter behavior."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        _write_config(tmp_path, [], agents={'default': ['claude']})

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                *_cli_args(tmp_path),
                'install',
                str(repo),
                'skill-a',
                '--agents-includes',
                'codex',
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'unknown agents ignored' not in result.output.lower()

    def test_agents_excludes_unknown_agent_continues_silently(self, tmp_path):
        """Unknown agent in --agents-excludes should keep old silent filter behavior."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        _write_config(tmp_path, [], agents={'default': ['claude']})

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                *_cli_args(tmp_path),
                'install',
                str(repo),
                'skill-a',
                '--agents-excludes',
                'codex',
            ],
        )

        assert result.exit_code == 0, result.output
        assert 'unknown agents ignored' not in result.output.lower()


class TestInstallUpsertConfig:
    """Scenario: existing package in config gets updated."""

    def test_merge_new_skills_into_existing(self, tmp_path):
        """Existing package with explicit skills list → new skills merged, no duplicates."""
        repo = _make_skill_repo(
            tmp_path,
            'my-skills',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
                {'name': 'skill-c'},
            ],
        )
        # Pre-existing config with skill-a only
        _write_config(tmp_path, [{'local_path': str(repo), 'skills': ['skill-a']}])

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.side_effect = [
                [0, 1],  # select skill-a (already exists) and skill-b
                [0, 1, 2, 3, 4],  # all agents
            ]
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        # Should have union of old + new, no duplicates
        assert set(pkg['skills']) == {'skill-a', 'skill-b'}

    def test_existing_package_skills_none_with_installed_skill(self, tmp_path):
        """Existing package with skills: None + specific skill already linked → no-op."""
        repo = _make_skill_repo(
            tmp_path,
            'my-skills',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
            ],
        )
        # Install all skills first (skills: None)
        _write_config(tmp_path, [{'local_path': str(repo)}])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result.exit_code == 0, result.output

        # Now try to install a specific skill that's already installed
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo), 'skill-a'])

        assert result.exit_code == 0, result.output
        assert 'already installed' in result.output.lower()

    def test_existing_package_skills_none_with_new_skill(self, tmp_path):
        """Existing package with skills: None + specific skill NOT linked → updates and reinstalls."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        # Install with skills: None
        _write_config(tmp_path, [{'local_path': str(repo)}])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result.exit_code == 0, result.output

        # Add a new skill to the repo
        new_skill_dir = repo / 'skills' / 'skill-b'
        new_skill_dir.mkdir(parents=True, exist_ok=True)
        (new_skill_dir / 'SKILL.md').write_text('---\nname: skill-b\ndescription: test\n---\n# skill-b\n')
        subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add skill-b'], cwd=repo, capture_output=True, check=True)

        # Install the new specific skill
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo), 'skill-b'])

        assert result.exit_code == 0, result.output
        assert 'skill-b' in result.output


class TestInstallMultiSelectCancelled:
    """Scenario: user cancels interactive selection."""

    def test_skill_selection_cancelled(self, tmp_path):
        """Cancelling skill multi-select → no config changes."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.return_value = None  # cancelled
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output
        assert 'cancelled' in result.output.lower() or 'abort' in result.output.lower()
        # Config should NOT exist
        assert not (tmp_path / 'config' / 'skills.yaml').exists()

    def test_agents_selection_cancelled(self, tmp_path):
        """Cancelling agent multi-select → no config changes."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.side_effect = [
                [0],  # skills selected
                None,  # agents cancelled
            ]
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output
        assert 'cancelled' in result.output.lower() or 'abort' in result.output.lower()
        assert not (tmp_path / 'config' / 'skills.yaml').exists()


class TestConfigAutoCreation:
    """Scenario: config file doesn't exist."""

    def test_config_auto_created(self, tmp_path):
        """Installing from source with no config file → config auto-created."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        # No _write_config call — config doesn't exist

        with patch('skm.cli.interactive_multi_select') as mock_select:
            mock_select.side_effect = [
                [0],  # select skill
                [0, 1, 2, 3, 4],  # select all agents
            ]
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output

        config = _load_config(tmp_path)
        assert 'packages' in config
        assert len(config['packages']) == 1

    def test_agent_prompt_is_limited_to_default_agents(self, tmp_path):
        """Interactive agent selection should only show default agents."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        _write_config(tmp_path, [], agents={'default': ['claude']})

        calls = []

        def _select(options, **kwargs):
            calls.append((options, kwargs))
            if len(calls) == 1:
                return [0]
            return [0]

        with patch('skm.cli.interactive_multi_select', side_effect=_select):
            runner = CliRunner()
            result = runner.invoke(cli, [*_cli_args(tmp_path), 'install', str(repo)])

        assert result.exit_code == 0, result.output

        assert calls[1][0] == ['claude']

        config = _load_config(tmp_path)
        pkg = config['packages'][0]
        assert 'agents' not in pkg

        assert (tmp_path / 'agents' / 'claude' / 'skill-a').exists()
        assert not (tmp_path / 'agents' / 'codex' / 'skill-a').exists()


class TestInstallWithoutSource:
    """Scenario: skm install (no source) — existing behavior unchanged."""

    def test_install_from_config_unchanged(self, tmp_path):
        """No source arg → installs from config as before."""
        repo = _make_skill_repo(tmp_path, 'my-skills', [{'name': 'skill-a'}])
        _write_config(tmp_path, [{'local_path': str(repo)}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        assert 'skill-a' in result.output
        assert 'added 1 skill' in result.output
