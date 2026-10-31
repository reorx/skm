"""BDD tests for device-local skill sources (`skm install --local <dir>`).

Local sources are symlinks under `<config dir>/local_sources/`. They are never
written to skills.yaml, so a shared config repo can stay identical across
devices while each device installs its own extra skills.

All tests use --config, --store, --lock, and --agents-dir to operate
entirely within tmp_path, never touching real agent directories.
"""

from io import StringIO
from pathlib import Path

from click.testing import CliRunner
from ruamel.yaml import YAML

from skm.cli import cli

_yaml = YAML()
_yaml.default_flow_style = False


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


def _sources_dir(tmp_path: Path) -> Path:
    return tmp_path / 'config' / 'local_sources'


def _write_config(tmp_path: Path, packages: list[dict]) -> Path:
    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    buf = StringIO()
    _yaml.dump({'packages': packages}, buf)
    config_path.write_text(buf.getvalue())
    return config_path


def _load_lock(tmp_path: Path) -> dict:
    lock_path = tmp_path / 'config' / 'skills-lock.yaml'
    if not lock_path.exists():
        return {}
    return _yaml.load(lock_path) or {}


def _lock_entries(tmp_path: Path) -> dict[str, dict]:
    return {s['name']: s for s in _load_lock(tmp_path).get('skills', [])}


def _write_skill(skill_dir: Path, name: str) -> None:
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / 'SKILL.md').write_text(f'---\nname: {name}\ndescription: test skill {name}\n---\n# {name}\n')


def _make_singleton(base: Path, dir_name: str, skill_name: str | None = None) -> Path:
    """A directory that is itself a skill (SKILL.md at its root)."""
    path = base / dir_name
    _write_skill(path, skill_name or dir_name)
    return path


def _make_package(base: Path, dir_name: str, skill_names: list[str]) -> Path:
    """A directory holding several skills under skills/<name>/."""
    path = base / dir_name
    for name in skill_names:
        _write_skill(path / 'skills' / name, name)
    return path


def _invoke(tmp_path: Path, *args: str):
    return CliRunner().invoke(cli, [*_cli_args(tmp_path), *args])


class TestInstallLocal:
    def test_links_dir_into_local_sources_and_installs_it(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        link = _sources_dir(tmp_path) / 'my-skill'
        assert link.is_symlink()
        assert Path(link.readlink()) == skill.resolve()
        installed = tmp_path / 'agents' / 'claude' / 'my-skill'
        assert installed.is_symlink()
        assert (installed / 'SKILL.md').exists()

    def test_lock_records_the_local_source_link_as_local_path(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        entry = _lock_entries(tmp_path)['my-skill']
        assert Path(entry['local_path']).expanduser() == _sources_dir(tmp_path) / 'my-skill'
        assert entry['repo'] is None

    def test_local_sources_dir_ignores_itself_in_git(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        assert (_sources_dir(tmp_path) / '.gitignore').read_text() == '*\n'

    def test_does_not_write_skills_yaml(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        assert not (tmp_path / 'config' / 'skills.yaml').exists()

    def test_leaves_existing_skills_yaml_untouched(self, tmp_path):
        shared = _make_singleton(tmp_path / 'src', 'shared-skill')
        config_path = _write_config(tmp_path, [{'local_path': str(shared)}])
        before = config_path.read_text()
        local = _make_singleton(tmp_path / 'src', 'device-skill')

        result = _invoke(tmp_path, 'install', '--local', str(local))

        assert result.exit_code == 0, result.output
        assert config_path.read_text() == before

    def test_keeps_skills_from_other_sources_in_lock(self, tmp_path):
        shared = _make_singleton(tmp_path / 'src', 'shared-skill')
        _write_config(tmp_path, [{'local_path': str(shared)}])
        assert _invoke(tmp_path, 'install').exit_code == 0
        local = _make_singleton(tmp_path / 'src', 'device-skill')

        result = _invoke(tmp_path, 'install', '--local', str(local))

        assert result.exit_code == 0, result.output
        assert set(_lock_entries(tmp_path)) == {'shared-skill', 'device-skill'}

    def test_installs_every_skill_of_a_package_dir(self, tmp_path):
        pkg = _make_package(tmp_path / 'src', 'my-pkg', ['alpha', 'beta'])

        result = _invoke(tmp_path, 'install', '--local', str(pkg))

        assert result.exit_code == 0, result.output
        assert (_sources_dir(tmp_path) / 'my-pkg').is_symlink()
        assert (tmp_path / 'agents' / 'claude' / 'alpha').is_symlink()
        assert (tmp_path / 'agents' / 'claude' / 'beta').is_symlink()

    def test_relative_path_is_linked_as_absolute(self, tmp_path, monkeypatch):
        _make_singleton(tmp_path / 'src', 'my-skill')
        monkeypatch.chdir(tmp_path)

        result = _invoke(tmp_path, 'install', '--local', 'src/my-skill')

        assert result.exit_code == 0, result.output
        link = _sources_dir(tmp_path) / 'my-skill'
        assert Path(link.readlink()).is_absolute()
        assert (tmp_path / 'agents' / 'claude' / 'my-skill' / 'SKILL.md').exists()

    def test_same_dir_twice_reuses_the_existing_link(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')
        assert _invoke(tmp_path, 'install', '--local', str(skill)).exit_code == 0

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        entries = [p.name for p in _sources_dir(tmp_path).iterdir() if not p.name.startswith('.')]
        assert entries == ['my-skill']

    def test_name_clash_with_another_dir_gets_a_suffix(self, tmp_path):
        first = _make_package(tmp_path / 'proj-a', 'skills', ['alpha'])
        second = _make_package(tmp_path / 'proj-b', 'skills', ['beta'])
        assert _invoke(tmp_path, 'install', '--local', str(first)).exit_code == 0

        result = _invoke(tmp_path, 'install', '--local', str(second))

        assert result.exit_code == 0, result.output
        sources = _sources_dir(tmp_path)
        assert Path((sources / 'skills').readlink()) == first.resolve()
        assert Path((sources / 'skills-2').readlink()) == second.resolve()
        assert (tmp_path / 'agents' / 'claude' / 'alpha').is_symlink()
        assert (tmp_path / 'agents' / 'claude' / 'beta').is_symlink()

    def test_dir_without_skills_fails_and_creates_no_link(self, tmp_path):
        empty = tmp_path / 'src' / 'empty'
        empty.mkdir(parents=True)

        result = _invoke(tmp_path, 'install', '--local', str(empty))

        assert result.exit_code != 0
        assert 'No skills found' in result.output
        assert not (_sources_dir(tmp_path) / 'empty').exists()

    def test_dir_already_in_skills_yaml_is_not_linked(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')
        _write_config(tmp_path, [{'local_path': str(skill)}])

        result = _invoke(tmp_path, 'install', '--local', str(skill))

        assert result.exit_code == 0, result.output
        assert 'skills.yaml' in result.output
        assert not (_sources_dir(tmp_path) / 'my-skill').exists()

    def test_rejects_source_argument_together_with_local(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill), 'https://github.com/foo/bar')

        assert result.exit_code != 0
        assert '--local' in result.output

    def test_rejects_agent_filters_together_with_local(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')

        result = _invoke(tmp_path, 'install', '--local', str(skill), '--agents-includes', 'claude')

        assert result.exit_code != 0
        assert '--local' in result.output


class TestInstallFromConfigWithLocalSources:
    def test_installs_local_sources_alongside_config_packages(self, tmp_path):
        shared = _make_singleton(tmp_path / 'src', 'shared-skill')
        _write_config(tmp_path, [{'local_path': str(shared)}])
        sources = _sources_dir(tmp_path)
        sources.mkdir(parents=True)
        (sources / 'device-skill').symlink_to(_make_singleton(tmp_path / 'src', 'device-skill'))

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert (tmp_path / 'agents' / 'claude' / 'shared-skill').is_symlink()
        assert (tmp_path / 'agents' / 'claude' / 'device-skill').is_symlink()
        assert set(_lock_entries(tmp_path)) == {'shared-skill', 'device-skill'}

    def test_second_install_is_up_to_date(self, tmp_path):
        _write_config(tmp_path, [])
        skill = _make_singleton(tmp_path / 'src', 'device-skill')
        assert _invoke(tmp_path, 'install', '--local', str(skill)).exit_code == 0

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'up to date' in result.output

    def test_deleting_the_local_source_link_removes_its_skills(self, tmp_path):
        _write_config(tmp_path, [])
        skill = _make_singleton(tmp_path / 'src', 'device-skill')
        assert _invoke(tmp_path, 'install', '--local', str(skill)).exit_code == 0
        (_sources_dir(tmp_path) / 'device-skill').unlink()

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert not (tmp_path / 'agents' / 'claude' / 'device-skill').exists()
        assert not (tmp_path / 'agents' / 'claude' / 'device-skill').is_symlink()
        assert 'device-skill' not in _lock_entries(tmp_path)

    def test_dangling_link_is_skipped_with_a_warning(self, tmp_path):
        _write_config(tmp_path, [])
        sources = _sources_dir(tmp_path)
        sources.mkdir(parents=True)
        (sources / 'gone').symlink_to(tmp_path / 'does-not-exist')
        (sources / 'device-skill').symlink_to(_make_singleton(tmp_path / 'src', 'device-skill'))

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'gone' in result.output
        assert (tmp_path / 'agents' / 'claude' / 'device-skill').is_symlink()

    def test_local_source_already_in_config_is_installed_once(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'my-skill')
        _write_config(tmp_path, [{'local_path': str(skill)}])
        sources = _sources_dir(tmp_path)
        sources.mkdir(parents=True)
        (sources / 'my-skill').symlink_to(skill)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        entries = [s for s in _load_lock(tmp_path)['skills'] if s['name'] == 'my-skill']
        assert len(entries) == 1
        assert Path(entries[0]['local_path']).expanduser() == skill

    def test_works_without_skills_yaml(self, tmp_path):
        skill = _make_singleton(tmp_path / 'src', 'device-skill')
        assert _invoke(tmp_path, 'install', '--local', str(skill)).exit_code == 0

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'device-skill' in _lock_entries(tmp_path)

    def test_missing_skills_yaml_without_local_sources_still_errors(self, tmp_path):
        result = _invoke(tmp_path, 'install')

        assert result.exit_code != 0
        assert 'not found' in result.output


class TestRemoveLocalSourceSkill:
    def test_removing_the_last_skill_drops_the_local_source(self, tmp_path):
        _write_config(tmp_path, [])
        skill = _make_singleton(tmp_path / 'src', 'device-skill')
        assert _invoke(tmp_path, 'install', '--local', str(skill)).exit_code == 0

        result = _invoke(tmp_path, 'remove', 'device-skill')

        assert result.exit_code == 0, result.output
        assert not (_sources_dir(tmp_path) / 'device-skill').is_symlink()
        assert skill.is_dir(), 'the source directory itself must never be deleted'
        assert not (tmp_path / 'agents' / 'claude' / 'device-skill').is_symlink()

        reinstall = _invoke(tmp_path, 'install')
        assert reinstall.exit_code == 0, reinstall.output
        assert not (tmp_path / 'agents' / 'claude' / 'device-skill').is_symlink()

    def test_removing_one_of_several_skills_keeps_the_source_and_warns(self, tmp_path):
        pkg = _make_package(tmp_path / 'src', 'my-pkg', ['alpha', 'beta'])
        assert _invoke(tmp_path, 'install', '--local', str(pkg)).exit_code == 0

        result = _invoke(tmp_path, 'remove', 'alpha')

        assert result.exit_code == 0, result.output
        assert (_sources_dir(tmp_path) / 'my-pkg').is_symlink()
        assert not (tmp_path / 'agents' / 'claude' / 'alpha').is_symlink()
        assert (tmp_path / 'agents' / 'claude' / 'beta').is_symlink()
        assert 'next' in result.output and 'install' in result.output


def _write_config_with_agents(tmp_path: Path, packages: list[dict], default_agents: list[str]) -> Path:
    config_path = tmp_path / 'config' / 'skills.yaml'
    config_path.parent.mkdir(parents=True, exist_ok=True)
    buf = StringIO()
    _yaml.dump({'agents': {'default': default_agents}, 'packages': packages}, buf)
    config_path.write_text(buf.getvalue())
    return config_path


def _override_line(skill: str, winner: Path, loser: Path) -> str:
    return f'{skill}: {winner} overrides {loser}'


def _link_target(tmp_path: Path, agent: str, skill: str) -> Path:
    return Path((tmp_path / 'agents' / agent / skill).readlink())


class TestLocalSourceOverrides:
    """A local source wins over a skills.yaml package that provides a skill of the same name."""

    def _setup(self, tmp_path: Path) -> tuple[Path, Path]:
        shared = _make_package(tmp_path / 'src', 'shared', ['demo', 'other'])
        _write_config_with_agents(tmp_path, [{'local_path': str(shared)}], ['claude', 'codex'])
        dev = _make_singleton(tmp_path / 'src', 'dev', 'demo')
        return shared, dev

    def _add_local_link(self, tmp_path: Path, target: Path) -> Path:
        sources = _sources_dir(tmp_path)
        sources.mkdir(parents=True, exist_ok=True)
        link = sources / target.name
        link.symlink_to(target)
        return link

    def test_full_install_links_the_local_version(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        link = self._add_local_link(tmp_path, dev)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert _link_target(tmp_path, 'claude', 'demo') == link
        assert _link_target(tmp_path, 'codex', 'demo') == link
        assert _link_target(tmp_path, 'claude', 'other') == shared / 'skills' / 'other'

    def test_full_install_reports_the_override(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        link = self._add_local_link(tmp_path, dev)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'Local source overrides' in result.output
        assert _override_line('demo', link, shared) in result.output

    def test_lock_keeps_only_the_local_entry(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        link = self._add_local_link(tmp_path, dev)

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        demos = [s for s in _load_lock(tmp_path)['skills'] if s['name'] == 'demo']
        assert len(demos) == 1
        assert Path(demos[0]['local_path']).expanduser() == link

    def test_repeated_install_is_up_to_date_and_still_reports_the_override(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        link = self._add_local_link(tmp_path, dev)
        assert _invoke(tmp_path, 'install').exit_code == 0

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert 'up to date' in result.output
        assert _override_line('demo', link, shared) in result.output

    def test_overriding_a_materialized_agent_never_prompts(self, tmp_path):
        shared = _make_package(tmp_path / 'src', 'shared', ['demo'])
        _write_config_with_agents(tmp_path, [{'local_path': str(shared)}], ['claude', 'openclaw'])
        dev = _make_singleton(tmp_path / 'src', 'dev', 'demo')
        (dev / 'notes.md').write_text('dev only\n')
        self._add_local_link(tmp_path, dev)

        first = _invoke(tmp_path, 'install')
        second = _invoke(tmp_path, 'install')

        assert first.exit_code == 0, first.output
        assert second.exit_code == 0, second.output
        assert 'Override?' not in first.output + second.output
        assert (tmp_path / 'agents' / 'openclaw' / 'demo' / 'notes.md').exists()

    def test_deleting_the_local_source_restores_the_shared_version(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        link = self._add_local_link(tmp_path, dev)
        assert _invoke(tmp_path, 'install').exit_code == 0
        link.unlink()

        result = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert _link_target(tmp_path, 'claude', 'demo') == shared / 'skills' / 'demo'
        assert 'Local source overrides' not in result.output
        demo = _lock_entries(tmp_path)['demo']
        assert Path(demo['local_path']).expanduser() == shared

    def test_install_local_takes_over_an_installed_shared_skill(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        assert _invoke(tmp_path, 'install').exit_code == 0

        result = _invoke(tmp_path, 'install', '--local', str(dev))

        assert result.exit_code == 0, result.output
        link = _sources_dir(tmp_path) / 'dev'
        assert _link_target(tmp_path, 'claude', 'demo') == link
        assert _override_line('demo', link, shared) in result.output
        demos = [s for s in _load_lock(tmp_path)['skills'] if s['name'] == 'demo']
        assert len(demos) == 1
        assert Path(demos[0]['local_path']).expanduser() == link
        assert 'other' in _lock_entries(tmp_path)

        follow_up = _invoke(tmp_path, 'install')
        assert follow_up.exit_code == 0, follow_up.output
        assert 'up to date' in follow_up.output

    def test_direct_reinstall_of_the_shared_package_keeps_the_local_version(self, tmp_path):
        shared, dev = self._setup(tmp_path)
        assert _invoke(tmp_path, 'install', '--local', str(dev)).exit_code == 0
        assert _invoke(tmp_path, 'install').exit_code == 0
        link = _sources_dir(tmp_path) / 'dev'

        result = _invoke(tmp_path, 'install', str(shared), 'demo')

        assert result.exit_code == 0, result.output
        assert _link_target(tmp_path, 'claude', 'demo') == link
        assert _override_line('demo', link, shared) in result.output
        demos = [s for s in _load_lock(tmp_path)['skills'] if s['name'] == 'demo']
        assert len(demos) == 1
        assert Path(demos[0]['local_path']).expanduser() == link

    def test_between_local_sources_the_first_entry_name_wins(self, tmp_path):
        _write_config_with_agents(tmp_path, [], ['claude'])
        first = self._add_local_link(tmp_path, _make_singleton(tmp_path / 'src', 'a-dev', 'demo'))
        second = self._add_local_link(tmp_path, _make_singleton(tmp_path / 'src', 'b-dev', 'demo'))

        result = _invoke(tmp_path, 'install')
        again = _invoke(tmp_path, 'install')

        assert result.exit_code == 0, result.output
        assert _link_target(tmp_path, 'claude', 'demo') == first
        assert _override_line('demo', first, second) in result.output
        assert 'up to date' in again.output
