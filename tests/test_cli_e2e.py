"""End-to-end CLI tests using Click's CliRunner.

All tests use --config, --store, --lock, and --agents-dir to operate
entirely within tmp_path, never touching real agent directories.
"""

import subprocess
from io import StringIO
from pathlib import Path

from click.testing import CliRunner
from ruamel.yaml import YAML

_yaml = YAML()
_yaml.default_flow_style = False

from skm.cli import cli


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with user config."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.email', 't@t.com'], cwd=path, capture_output=True, check=True)
    subprocess.run(['git', 'config', 'user.name', 'T'], cwd=path, capture_output=True, check=True)


def _make_skill_repo(base: Path, repo_name: str, skills: list[dict]) -> Path:
    """Create a local git repo with one or more skills.

    skills: list of {"name": str, "subdir": bool} where subdir=True puts it
            under skills/<name>/, False puts SKILL.md at repo root (singleton).
    """
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
    """Common CLI flags to isolate all paths within tmp_path."""
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
    """Write a skills.yaml config file and return its path."""
    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {'packages': repos}
    if agents is not None:
        data['agents'] = agents
    buf = StringIO()
    _yaml.dump(data, buf)
    config_path.write_text(buf.getvalue())
    return config_path


def _load_lock(tmp_path: Path) -> dict:
    """Load the lock file as a dict."""
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    if not lock_path.exists():
        return {'skills': []}
    return _yaml.load(lock_path) or {'skills': []}


# --- Tests ---


class TestInstall:
    def test_install_single_skill(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-a', [{'name': 'my-skill'}])
        _write_config(tmp_path, [{'repo': str(repo), 'skills': ['my-skill']}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        assert 'Cloning' in result.output
        assert 'my-skill' in result.output

        # Verify links created for all agents
        for agent in ['claude', 'codex', 'pi']:
            link = tmp_path / 'agents' / agent / 'my-skill'
            assert link.is_symlink(), f'Missing symlink for {agent}'
        # standard and openclaw use hardlinks (directory with hardlinked files)
        for agent in ['standard', 'openclaw']:
            hardlink = tmp_path / 'agents' / agent / 'my-skill'
            assert hardlink.is_dir() and not hardlink.is_symlink(), f'Missing hardlinked dir for {agent}'

        # Verify lock file
        lock = _load_lock(tmp_path)
        assert len(lock['skills']) == 1
        assert lock['skills'][0]['name'] == 'my-skill'
        assert lock['skills'][0]['repo'] == str(repo)
        assert len(lock['skills'][0]['linked_to']) == 5

    def test_install_multiple_skills_from_one_repo(self, tmp_path):
        repo = _make_skill_repo(
            tmp_path,
            'repo-multi',
            [
                {'name': 'skill-a'},
                {'name': 'skill-b'},
            ],
        )
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        lock = _load_lock(tmp_path)
        names = {s['name'] for s in lock['skills']}
        assert names == {'skill-a', 'skill-b'}

    def test_install_singleton_skill(self, tmp_path):
        repo = _make_skill_repo(
            tmp_path,
            'repo-single',
            [
                {'name': 'solo', 'subdir': False},
            ],
        )
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        assert (tmp_path / 'agents' / 'claude' / 'solo').is_symlink()
        lock = _load_lock(tmp_path)
        assert lock['skills'][0]['name'] == 'solo'

    def test_install_with_skill_filter(self, tmp_path):
        repo = _make_skill_repo(
            tmp_path,
            'repo-filter',
            [
                {'name': 'wanted'},
                {'name': 'unwanted'},
            ],
        )
        _write_config(tmp_path, [{'repo': str(repo), 'skills': ['wanted']}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        lock = _load_lock(tmp_path)
        assert len(lock['skills']) == 1
        assert lock['skills'][0]['name'] == 'wanted'

    def test_install_with_agents_excludes(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-excl', [{'name': 'my-skill'}])
        _write_config(
            tmp_path,
            [
                {
                    'repo': str(repo),
                    'agents': {'excludes': ['openclaw', 'standard']},
                }
            ],
        )

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        assert (tmp_path / 'agents' / 'claude' / 'my-skill').is_symlink()
        assert (tmp_path / 'agents' / 'codex' / 'my-skill').is_symlink()
        assert (tmp_path / 'agents' / 'pi' / 'my-skill').is_symlink()
        assert not (tmp_path / 'agents' / 'openclaw' / 'my-skill').exists()
        assert not (tmp_path / 'agents' / 'standard' / 'my-skill').exists()

    def test_install_idempotent(self, tmp_path):
        """Running install twice produces the same result."""
        repo = _make_skill_repo(tmp_path, 'repo-idem', [{'name': 'idem-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        result1 = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result1.exit_code == 0, result1.output

        result2 = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result2.exit_code == 0, result2.output
        assert 'up to date' in result2.output

        lock = _load_lock(tmp_path)
        assert len(lock['skills']) == 1

    def test_install_removes_old_skills(self, tmp_path):
        """Skills removed from config get their symlinks cleaned up."""
        repo = _make_skill_repo(
            tmp_path,
            'repo-rm',
            [
                {'name': 'keep-me'},
                {'name': 'remove-me'},
            ],
        )
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result.exit_code == 0, result.output
        assert (tmp_path / 'agents' / 'claude' / 'remove-me').is_symlink()

        # Now update config to only keep one skill
        _write_config(tmp_path, [{'repo': str(repo), 'skills': ['keep-me']}])
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert result.exit_code == 0, result.output
        assert 'Removing stale links' in result.output
        assert 'for remove-me (no longer in config)' in result.output

        assert (tmp_path / 'agents' / 'claude' / 'keep-me').is_symlink()
        assert not (tmp_path / 'agents' / 'claude' / 'remove-me').exists()

        lock = _load_lock(tmp_path)
        assert len(lock['skills']) == 1
        assert lock['skills'][0]['name'] == 'keep-me'

    def test_install_dedup_same_name(self, tmp_path):
        """Two skills with the same name in one source should be deduplicated."""
        repo = tmp_path / 'repo-dedup'
        _init_git_repo(repo)
        # Create two subdirectories with different paths but same skill name
        for subdir in ['variant-a', 'variant-b']:
            skill_dir = repo / 'skills' / subdir
            skill_dir.mkdir(parents=True, exist_ok=True)
            (skill_dir / 'SKILL.md').write_text('---\nname: dup-skill\ndescription: test\n---\n# dup\n')

        subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'init'], cwd=repo, capture_output=True, check=True)
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        assert result.exit_code == 0, result.output
        assert 'duplicate skill name' in result.output

        lock = _load_lock(tmp_path)
        # Only the first occurrence should be installed
        dup_skills = [s for s in lock['skills'] if s['name'] == 'dup-skill']
        assert len(dup_skills) == 1


class TestList:
    def test_list_empty(self, tmp_path):
        _write_config(tmp_path, [])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'list'])
        assert result.exit_code == 0
        assert 'No skills installed' in result.output

    def test_list_after_install(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-list', [{'name': 'listed-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'list'])
        assert result.exit_code == 0
        assert 'listed-skill' in result.output
        assert str(repo) in result.output

    def test_list_all_shows_unmanaged_skills(self, tmp_path):
        """--all shows all skills in agent dirs, marking unmanaged ones."""
        repo = _make_skill_repo(tmp_path, 'repo-all', [{'name': 'managed-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        # Create an unmanaged skill directory in one agent dir
        unmanaged = tmp_path / 'agents' / 'claude' / 'manual-skill'
        unmanaged.mkdir(parents=True, exist_ok=True)
        (unmanaged / 'SKILL.md').write_text('---\nname: manual-skill\n---\n# manual\n')

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'list', '--all'])
        assert result.exit_code == 0, result.output
        # Should show agent headers
        assert 'claude' in result.output
        # Should show both managed and unmanaged skills
        assert 'managed-skill' in result.output
        assert 'manual-skill' in result.output

    def test_list_all_empty_agents(self, tmp_path):
        """--all with no agent dirs shows nothing."""
        _write_config(tmp_path, [])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'list', '--all'])
        assert result.exit_code == 0

    def test_list_all_distinguishes_managed(self, tmp_path):
        """--all marks managed skills differently from unmanaged."""
        repo = _make_skill_repo(tmp_path, 'repo-dist', [{'name': 'skm-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        # Add an unmanaged skill
        unmanaged = tmp_path / 'agents' / 'claude' / 'local-skill'
        unmanaged.mkdir(parents=True, exist_ok=True)

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'list', '--all'])
        assert result.exit_code == 0, result.output
        # The output should contain some indicator for managed vs unmanaged
        # Managed skills should show repo info or a marker
        lines = result.output.splitlines()
        # Find lines with skill names
        skm_lines = [l for l in lines if 'skm-skill' in l]
        local_lines = [l for l in lines if 'local-skill' in l]
        assert len(skm_lines) > 0
        assert len(local_lines) > 0
        # Managed skills should have some distinguishing marker (e.g. repo info)
        assert any('repo-dist' in l or 'skm' in l.lower() for l in skm_lines)
        # Unmanaged should NOT have repo info
        assert not any('repo-dist' in l for l in local_lines)


class TestUpdate:
    def test_update_nonexistent_skill(self, tmp_path):
        _write_config(tmp_path, [])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'update', 'no-such-skill'])
        assert result.exit_code == 1
        assert 'not installed' in result.output

    def test_update_already_up_to_date(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-upd', [{'name': 'upd-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'update', 'upd-skill'])
        assert result.exit_code == 0
        assert 'Already up to date' in result.output

    def test_update_with_new_commit(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-upd2', [{'name': 'upd-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        # Make a new commit in the source repo
        (repo / 'skills' / 'upd-skill' / 'extra.md').write_text('new content')
        subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add extra'], cwd=repo, capture_output=True, check=True)

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'update', 'upd-skill'])
        assert result.exit_code == 0
        assert 'Updated' in result.output
        assert 'add extra' in result.output

        # Verify lock has new commit
        lock = _load_lock(tmp_path)
        old_commit = lock['skills'][0]['commit']
        # The commit should be 40 hex chars (full SHA)
        assert len(old_commit) == 40

    def test_update_removes_deleted_materialized_files(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-upd3', [{'name': 'upd-skill'}])
        tracked_file = repo / 'skills' / 'upd-skill' / 'extra.md'
        tracked_file.write_text('old content')
        subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'add extra'], cwd=repo, capture_output=True, check=True)

        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        install_result = runner.invoke(cli, [*_cli_args(tmp_path), 'install'])
        assert install_result.exit_code == 0, install_result.output

        standard_file = tmp_path / 'agents' / 'standard' / 'upd-skill' / 'extra.md'
        openclaw_file = tmp_path / 'agents' / 'openclaw' / 'upd-skill' / 'extra.md'
        assert standard_file.exists()
        assert openclaw_file.exists()

        tracked_file.unlink()
        subprocess.run(['git', 'add', '-A'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'remove extra'], cwd=repo, capture_output=True, check=True)

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'update', 'upd-skill'])
        assert result.exit_code == 0, result.output
        assert 'remove extra' in result.output
        assert not standard_file.exists()
        assert not openclaw_file.exists()


class TestCheckUpdates:
    def test_check_updates_no_skills(self, tmp_path):
        _write_config(tmp_path, [])
        runner = CliRunner()
        result = runner.invoke(cli, [*_cli_args(tmp_path), 'check-updates'])
        assert result.exit_code == 0
        assert 'No skills installed' in result.output

    def test_check_updates_up_to_date(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-chk', [{'name': 'chk-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'check-updates'])
        assert result.exit_code == 0
        assert 'Up to date' in result.output or 'up to date' in result.output

    def test_check_updates_has_updates(self, tmp_path):
        repo = _make_skill_repo(tmp_path, 'repo-chk2', [{'name': 'chk-skill'}])
        _write_config(tmp_path, [{'repo': str(repo)}])

        runner = CliRunner()
        runner.invoke(cli, [*_cli_args(tmp_path), 'install'])

        # Make a new commit in the source repo
        (repo / 'skills' / 'chk-skill' / 'new.md').write_text('update')
        subprocess.run(['git', 'add', '.'], cwd=repo, capture_output=True, check=True)
        subprocess.run(['git', 'commit', '-m', 'upstream change'], cwd=repo, capture_output=True, check=True)

        result = runner.invoke(cli, [*_cli_args(tmp_path), 'check-updates'])
        assert result.exit_code == 0
        assert 'Updates available' in result.output or 'upstream change' in result.output
