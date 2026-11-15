"""Dynamic skills: a `source_cmd` package whose SKILL.md is a command's stdout.

Every test drives the command as `cat <tmp>/out.md`, so rewriting out.md
simulates the upstream CLI changing its output.
"""

import hashlib
import shlex
from io import StringIO
from pathlib import Path

import pytest
from click.testing import CliRunner
from pydantic import ValidationError
from ruamel.yaml import YAML

from skm.cli import cli
from skm.dynamic import dynamic_skill_dir, generate_dynamic_skill, load_dynamic_skill, render_source_cmd
from skm.types import SkillRepoConfig

_yaml = YAML()
_yaml.default_flow_style = False


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


def _write_config(tmp_path: Path, packages: list[dict], agents: dict | None = None) -> Path:
    config_path = _config_path(tmp_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict = {'packages': packages}
    if agents is not None:
        data['agents'] = agents
    buf = StringIO()
    _yaml.dump(data, buf)
    config_path.write_text(buf.getvalue())
    return config_path


def _load_config(tmp_path: Path) -> dict:
    return _yaml.load(_config_path(tmp_path))


def _lock_entries(tmp_path: Path) -> dict[str, dict]:
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    if not lock_path.exists():
        return {}
    data = _yaml.load(lock_path) or {}
    return {s['name']: s for s in data.get('skills', [])}


def _skill_md(name: str, body: str = 'v1') -> str:
    return f'---\nname: {name}\ndescription: generated {name}\n---\n# {name}\n{body}\n'


def _cat_cmd(tmp_path: Path, name: str = 'tinyhost', body: str = 'v1') -> tuple[str, Path]:
    """Write out.md and return (command that prints it, out.md path)."""
    out = tmp_path / 'out.md'
    out.write_text(_skill_md(name, body))
    return f'cat {shlex.quote(str(out))}', out


def _write_skill(skill_dir: Path, name: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test skill {name}\n---\n# {name}\n')


DEFAULT_AGENTS = {'default': ['claude', 'codex']}


# --- config ---


class TestConfig:
    def test_source_cmd_alone_is_valid(self):
        pkg = SkillRepoConfig(source_cmd='tinyhost skill')
        assert pkg.is_dynamic
        assert not pkg.is_local
        assert pkg.source_key == 'tinyhost skill'

    def test_repo_and_local_packages_are_not_dynamic(self):
        assert not SkillRepoConfig(repo='https://github.com/a/b').is_dynamic
        assert not SkillRepoConfig(local_path='/tmp/x').is_dynamic

    def test_source_cmd_with_repo_is_rejected(self):
        with pytest.raises(ValidationError, match='exactly one'):
            SkillRepoConfig(source_cmd='tinyhost skill', repo='https://github.com/a/b')

    def test_source_cmd_with_local_path_is_rejected(self):
        with pytest.raises(ValidationError, match='exactly one'):
            SkillRepoConfig(source_cmd='tinyhost skill', local_path='/tmp/x')

    @pytest.mark.parametrize(
        'extra',
        [{'skills': ['a']}, {'skills_excludes': ['a']}, {'skills_dir': 'skills'}, {'clone_strategy': 'shallow'}],
    )
    def test_source_cmd_with_skill_selection_is_rejected(self, extra):
        with pytest.raises(ValidationError, match='source_cmd'):
            SkillRepoConfig(source_cmd='tinyhost skill', **extra)

    @pytest.mark.parametrize('cmd', ['', '   '])
    def test_empty_source_cmd_is_rejected(self, cmd):
        with pytest.raises(ValidationError):
            SkillRepoConfig(source_cmd=cmd)

    def test_source_cmd_accepts_agents_filter(self):
        pkg = SkillRepoConfig(source_cmd='tinyhost skill', agents={'includes': ['claude']})
        assert pkg.agents.includes == ['claude']


# --- generation ---


class TestGenerate:
    def test_dir_is_named_after_the_command(self, tmp_path):
        cmd = 'tinyhost skill'
        digest = hashlib.sha256(cmd.encode()).hexdigest()[:8]
        assert dynamic_skill_dir(tmp_path, cmd) == tmp_path / '_dynamic' / f'tinyhost-skill-{digest}'

    def test_dir_slug_keeps_only_alphanumerics_and_is_capped(self, tmp_path):
        cmd = "FOO=1 /usr/bin/my_tool --print 'skill' | " + 'x' * 80
        name = dynamic_skill_dir(tmp_path, cmd).name
        slug, digest = name.rsplit('-', 1)
        assert len(digest) == 8
        assert slug.startswith('foo-1-usr-bin-my-tool-print-skill')
        assert len(slug) <= 40
        assert not slug.startswith('-') and not slug.endswith('-')

    def test_different_commands_get_different_dirs(self, tmp_path):
        assert dynamic_skill_dir(tmp_path, 'a skill') != dynamic_skill_dir(tmp_path, 'a  skill')

    def test_writes_stdout_as_skill_md(self, tmp_path):
        cmd, out = _cat_cmd(tmp_path)
        dest = dynamic_skill_dir(tmp_path / 'store', cmd)

        changed = generate_dynamic_skill(cmd, dest)

        assert changed
        assert (dest / 'SKILL.md').read_text() == out.read_text()
        skill = load_dynamic_skill(dest)
        assert skill.name == 'tinyhost'
        assert skill.path == dest
        assert skill.relative_path == '.'

    def test_leading_whitespace_is_stripped(self, tmp_path):
        out = tmp_path / 'out.md'
        out.write_text('\n\n  ' + _skill_md('tinyhost'))
        text = render_source_cmd(f'cat {shlex.quote(str(out))}')
        assert text.startswith('---\nname: tinyhost')

    def test_unchanged_output_is_not_rewritten(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        dest = dynamic_skill_dir(tmp_path / 'store', cmd)
        generate_dynamic_skill(cmd, dest)
        inode = (dest / 'SKILL.md').stat().st_ino

        assert generate_dynamic_skill(cmd, dest) is False
        assert (dest / 'SKILL.md').stat().st_ino == inode

    def test_changed_output_is_rewritten_in_place(self, tmp_path):
        cmd, out = _cat_cmd(tmp_path)
        dest = dynamic_skill_dir(tmp_path / 'store', cmd)
        generate_dynamic_skill(cmd, dest)
        inode = (dest / 'SKILL.md').stat().st_ino
        out.write_text(_skill_md('tinyhost', 'v2'))

        assert generate_dynamic_skill(cmd, dest) is True
        assert 'v2' in (dest / 'SKILL.md').read_text()
        assert (dest / 'SKILL.md').stat().st_ino == inode

    def test_runs_through_sh(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        text = render_source_cmd(f'{cmd} | sed "s/v1/piped/"')
        assert 'piped' in text

    def test_output_without_frontmatter_is_rejected(self, tmp_path):
        dest = tmp_path / 'store' / 'x'
        with pytest.raises(ValueError, match='frontmatter'):
            generate_dynamic_skill('echo "# just markdown"', dest)
        assert not dest.exists()

    def test_output_without_name_is_rejected(self, tmp_path):
        out = tmp_path / 'out.md'
        out.write_text('---\ndescription: nameless\n---\n')
        with pytest.raises(ValueError, match="'name'"):
            render_source_cmd(f'cat {shlex.quote(str(out))}')

    @pytest.mark.parametrize('name', ['../escape', 'a/b', '.hidden', '-flag', 'has space'])
    def test_unsafe_skill_name_is_rejected(self, tmp_path, name):
        cmd, _ = _cat_cmd(tmp_path, name=name)
        dest = tmp_path / 'store' / 'x'
        with pytest.raises(ValueError, match='name'):
            generate_dynamic_skill(cmd, dest)
        assert not dest.exists()

    def test_failing_command_reports_stderr(self, tmp_path):
        with pytest.raises(Exception, match='boom-on-stderr'):
            render_source_cmd('echo boom-on-stderr >&2; exit 3')

    def test_slow_command_times_out(self, tmp_path, monkeypatch):
        import subprocess

        monkeypatch.setattr('skm.dynamic.SOURCE_CMD_TIMEOUT', 0.3)
        with pytest.raises(subprocess.TimeoutExpired):
            render_source_cmd('sleep 5')

    def test_command_gets_no_stdin_and_runs_in_home(self, tmp_path):
        out = tmp_path / 'out.md'
        out.write_text(_skill_md('tinyhost', 'BODY'))
        # `cat -` would hang on an inherited terminal; with no stdin it reads EOF.
        text = render_source_cmd(f'cat - {shlex.quote(str(out))}; echo "cwd=$(pwd)"')
        assert f'cwd={Path.home()}' in text


# --- install ---


class TestInstall:
    def test_links_generated_skill_to_agents(self, tmp_path):
        cmd, out = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        dest = dynamic_skill_dir(tmp_path / 'store', cmd)
        for agent in ('claude', 'codex'):
            link = tmp_path / 'agents' / agent / 'tinyhost'
            assert link.is_symlink()
            assert link.resolve() == dest.resolve()
            assert (link / 'SKILL.md').read_text() == out.read_text()

    def test_lock_records_the_command(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)

        assert _invoke(tmp_path, 'install').exit_code == 0

        entry = _lock_entries(tmp_path)['tinyhost']
        assert entry['source_cmd'] == cmd
        assert entry['repo'] is None
        assert entry['local_path'] is None
        assert entry['commit'] is None
        assert entry['skill_path'] == '.'
        assert len(entry['linked_to']) == 2

    def test_respects_package_agents_filter(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd, 'agents': {'includes': ['claude']}}], DEFAULT_AGENTS)

        assert _invoke(tmp_path, 'install').exit_code == 0

        assert (tmp_path / 'agents' / 'claude' / 'tinyhost').is_symlink()
        assert not (tmp_path / 'agents' / 'codex' / 'tinyhost').exists()

    def test_second_install_does_not_rerun_the_command(self, tmp_path):
        cmd, out = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)
        assert _invoke(tmp_path, 'install').exit_code == 0
        out.write_text(_skill_md('tinyhost', 'v2'))

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'up to date' in result.output
        generated = dynamic_skill_dir(tmp_path / 'store', cmd) / 'SKILL.md'
        assert 'v1' in generated.read_text()

    def test_failing_command_warns_and_installs_the_rest(self, tmp_path):
        other = tmp_path / 'src' / 'other'
        _write_skill(other, 'other')
        _write_config(
            tmp_path,
            [{'source_cmd': 'no-such-cli-skm-test skill'}, {'local_path': str(other)}],
            DEFAULT_AGENTS,
        )

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'Warning' in result.output
        assert 'no-such-cli-skm-test skill' in result.output
        assert (tmp_path / 'agents' / 'claude' / 'other').is_symlink()
        entries = _lock_entries(tmp_path)
        assert list(entries) == ['other']

    def test_failed_command_is_retried_on_next_install(self, tmp_path):
        out = tmp_path / 'out.md'
        cmd = f'cat {shlex.quote(str(out))}'
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)
        assert _invoke(tmp_path, 'install').exit_code == 0
        assert 'tinyhost' not in _lock_entries(tmp_path)
        out.write_text(_skill_md('tinyhost'))

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'tinyhost' in _lock_entries(tmp_path)

    def test_invalid_output_warns_and_skips(self, tmp_path):
        _write_config(tmp_path, [{'source_cmd': 'echo not a skill'}], DEFAULT_AGENTS)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'Warning' in result.output
        assert 'frontmatter' in result.output
        assert _lock_entries(tmp_path) == {}

    def test_dropping_the_package_removes_its_links(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        other = tmp_path / 'src' / 'other'
        _write_skill(other, 'other')
        _write_config(tmp_path, [{'source_cmd': cmd}, {'local_path': str(other)}], DEFAULT_AGENTS)
        assert _invoke(tmp_path, 'install').exit_code == 0
        _write_config(tmp_path, [{'local_path': str(other)}], DEFAULT_AGENTS)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert not (tmp_path / 'agents' / 'claude' / 'tinyhost').exists()
        assert 'tinyhost' not in _lock_entries(tmp_path)

    def test_local_source_with_same_name_wins(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)
        dev = tmp_path / 'src' / 'dev'
        _write_skill(dev, 'tinyhost')
        sources = tmp_path / 'config' / 'local_sources'
        sources.mkdir(parents=True)
        (sources / 'dev').symlink_to(dev)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'Local source overrides' in result.output
        assert Path((tmp_path / 'agents' / 'claude' / 'tinyhost').readlink()) == sources / 'dev'
        entry = _lock_entries(tmp_path)['tinyhost']
        assert entry['source_cmd'] is None
        assert entry['local_path'] is not None

    def test_two_dynamic_packages_survive_a_direct_install(self, tmp_path):
        """Saving skills.yaml must keep each dynamic package (they used to share one key)."""
        a = tmp_path / 'a.md'
        a.write_text(_skill_md('alpha'))
        b = tmp_path / 'b.md'
        b.write_text(_skill_md('beta'))
        cmd_a = f'cat {a}'
        cmd_b = f'cat {b}'
        config_path = _config_path(tmp_path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            'agents:\n'
            '  default: [claude, codex]\n'
            'packages:\n'
            f'  - source_cmd: {cmd_a}  # alpha comment\n'
            f'  - source_cmd: {cmd_b}  # beta comment\n'
            '    agents:\n'
            '      includes: [claude]\n'
        )
        other = tmp_path / 'src' / 'other'
        _write_skill(other, 'other')

        result = _invoke(tmp_path, 'install', str(other), 'other', '--agents-includes', 'claude')

        assert result.exit_code == 0, result.output
        packages = _load_config(tmp_path)['packages']
        assert packages[0] == {'source_cmd': cmd_a}
        assert packages[1] == {'source_cmd': cmd_b, 'agents': {'includes': ['claude']}}
        assert packages[2]['local_path'] == str(other)
        text = config_path.read_text()
        assert '# alpha comment' in text
        assert '# beta comment' in text


# --- update ---


class TestUpdate:
    def _install(self, tmp_path: Path, agents: dict | None = None) -> tuple[str, Path]:
        cmd, out = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], agents or DEFAULT_AGENTS)
        result = _invoke(tmp_path, 'install')
        assert result.exit_code == 0, result.output
        return cmd, out

    def test_changed_output_is_regenerated(self, tmp_path):
        cmd, out = self._install(tmp_path)
        out.write_text(_skill_md('tinyhost', 'v2'))

        result = _invoke(tmp_path, 'update', 'tinyhost')

        assert result.exit_code == 0, result.output
        assert 'v2' in (tmp_path / 'agents' / 'claude' / 'tinyhost' / 'SKILL.md').read_text()

    def test_unchanged_output_is_up_to_date(self, tmp_path):
        self._install(tmp_path)

        result = _invoke(tmp_path, 'update', 'tinyhost')

        assert result.exit_code == 0, result.output
        assert 'Already up to date' in result.output

    def test_update_all_includes_dynamic_skills(self, tmp_path):
        cmd, out = self._install(tmp_path)
        out.write_text(_skill_md('tinyhost', 'v2'))

        result = _invoke(tmp_path, 'update', '--all')

        assert result.exit_code == 0, result.output
        assert 'v2' in (tmp_path / 'agents' / 'claude' / 'tinyhost' / 'SKILL.md').read_text()

    def test_renamed_skill_replaces_the_old_links(self, tmp_path):
        cmd, out = self._install(tmp_path)
        out.write_text(_skill_md('tinyhost2', 'v2'))

        result = _invoke(tmp_path, 'update', 'tinyhost')

        assert result.exit_code == 0, result.output
        for agent in ('claude', 'codex'):
            assert not (tmp_path / 'agents' / agent / 'tinyhost').exists()
            assert (tmp_path / 'agents' / agent / 'tinyhost2').is_symlink()
        entries = _lock_entries(tmp_path)
        assert 'tinyhost' not in entries
        assert entries['tinyhost2']['source_cmd'] == cmd

    def test_materialized_copy_is_refreshed(self, tmp_path):
        cmd, out = self._install(tmp_path, {'default': ['claude', 'openclaw']})
        copy = tmp_path / 'agents' / 'openclaw' / 'tinyhost'
        assert copy.is_dir() and not copy.is_symlink()
        out.write_text(_skill_md('tinyhost', 'v2'))

        result = _invoke(tmp_path, 'update', 'tinyhost')

        assert result.exit_code == 0, result.output
        assert 'v2' in (copy / 'SKILL.md').read_text()

    def test_failing_command_is_an_error(self, tmp_path):
        cmd, out = self._install(tmp_path)
        out.unlink()

        result = _invoke(tmp_path, 'update', 'tinyhost')

        assert result.exit_code != 0
        assert 'Command failed' in result.output
        # The previously generated skill stays installed.
        assert (tmp_path / 'agents' / 'claude' / 'tinyhost' / 'SKILL.md').exists()


# --- list / remove / check-updates ---


class TestOtherCommands:
    def _install(self, tmp_path: Path) -> str:
        cmd, _ = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd}], DEFAULT_AGENTS)
        result = _invoke(tmp_path, 'install')
        assert result.exit_code == 0, result.output
        return cmd

    def test_list_shows_the_command(self, tmp_path):
        cmd = self._install(tmp_path)

        result = _invoke(tmp_path, 'list')

        assert result.exit_code == 0, result.output
        assert f'cmd: {cmd}' in result.output
        assert 'repo:' not in result.output

    def test_list_all_shows_the_command(self, tmp_path):
        cmd = self._install(tmp_path)

        result = _invoke(tmp_path, 'list', '--all')

        assert result.exit_code == 0, result.output
        assert cmd in result.output

    def test_remove_deletes_links_lock_entry_and_package(self, tmp_path):
        self._install(tmp_path)

        result = _invoke(tmp_path, 'remove', 'tinyhost')

        assert result.exit_code == 0, result.output
        assert not (tmp_path / 'agents' / 'claude' / 'tinyhost').exists()
        assert _lock_entries(tmp_path) == {}
        assert _load_config(tmp_path)['packages'] == []

    def test_check_updates_skips_dynamic_skills(self, tmp_path):
        self._install(tmp_path)

        result = _invoke(tmp_path, 'check-updates')

        assert result.exit_code == 0, result.output
        assert 'Skipping dynamic skill: tinyhost (run skm update tinyhost to regenerate)' in result.output


# --- install --cmd ---


class TestInstallCmd:
    def test_saves_package_and_installs(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)

        result = _invoke(tmp_path, 'install', '--cmd', cmd, '--agents-includes', 'claude')

        assert result.exit_code == 0, result.output
        assert _load_config(tmp_path)['packages'] == [{'source_cmd': cmd, 'agents': {'includes': ['claude']}}]
        assert (tmp_path / 'agents' / 'claude' / 'tinyhost').is_symlink()
        assert not (tmp_path / 'agents' / 'codex' / 'tinyhost').exists()
        assert _lock_entries(tmp_path)['tinyhost']['source_cmd'] == cmd

    def test_failing_command_leaves_config_untouched(self, tmp_path):
        result = _invoke(tmp_path, 'install', '--cmd', 'no-such-cli-skm-test skill', '--agents-includes', 'claude')

        assert result.exit_code != 0
        assert 'Command failed' in result.output
        assert not _config_path(tmp_path).exists()
        assert _lock_entries(tmp_path) == {}

    def test_invalid_output_leaves_config_untouched(self, tmp_path):
        _write_config(tmp_path, [], DEFAULT_AGENTS)
        before = _config_path(tmp_path).read_text()

        result = _invoke(tmp_path, 'install', '--cmd', 'echo nope', '--agents-includes', 'claude')

        assert result.exit_code != 0
        assert 'frontmatter' in result.output
        assert _config_path(tmp_path).read_text() == before

    def test_existing_package_keeps_its_agents(self, tmp_path):
        cmd, _ = _cat_cmd(tmp_path)
        _write_config(tmp_path, [{'source_cmd': cmd, 'agents': {'includes': ['codex']}}], DEFAULT_AGENTS)
        before = _config_path(tmp_path).read_text()

        result = _invoke(tmp_path, 'install', '--cmd', cmd)

        assert result.exit_code == 0, result.output
        assert _config_path(tmp_path).read_text() == before
        assert (tmp_path / 'agents' / 'codex' / 'tinyhost').is_symlink()
        assert not (tmp_path / 'agents' / 'claude' / 'tinyhost').exists()

    @pytest.mark.parametrize('extra', [['https://github.com/a/b'], ['--local', '.']])
    def test_cannot_combine_with_source_or_local(self, tmp_path, extra):
        result = _invoke(tmp_path, 'install', '--cmd', 'tinyhost skill', *extra)

        assert result.exit_code != 0
        assert '--cmd' in result.output
