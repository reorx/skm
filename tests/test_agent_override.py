"""Behavior coverage for shared agent configuration across CLI commands."""
import subprocess

import pytest
from click.testing import CliRunner

from skm.cli import cli
from test_cli_e2e import _cli_args, _write_config, _make_skill_repo, _load_lock


def invoke(tmp_path, *args, isolated=True):
    flags = _cli_args(tmp_path)
    if not isolated:
        flags = flags[:-2]
    result = CliRunner().invoke(cli, [*flags, *args])
    assert result.exit_code == 0, result.output
    return result.output


@pytest.mark.parametrize('override', [
    {'typo': {'path': '/unused'}}, {'claude': {'install_mode': 'copy'}},
    {'claude': {'path': ''}}, {'claude': {'path': '  '}}, {'claude': {'mode': 'symlink'}},
])
def test_invalid_override_has_no_install_side_effects(tmp_path, override):
    _write_config(tmp_path, [], {'override': override})
    result = CliRunner().invoke(cli, [*_cli_args(tmp_path), 'install'])
    assert result.exit_code != 0
    assert 'Invalid config' in result.output
    assert not (tmp_path / 'agents').exists()


@pytest.mark.parametrize('includes,ignored', [(['claude', 'openclaw'], 'openclaw'), (['claud'], 'claud'), (['claude'], None)])
def test_includes_warning_preserves_config(tmp_path, includes, ignored):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    path = _write_config(tmp_path, [{'local_path': str(repo), 'agents': {'includes': includes}}], {'default': ['claude']})
    before = path.read_text()
    output = invoke(tmp_path, 'install')
    assert ('ignored:' in output) == bool(ignored)
    if ignored:
        assert f'ignored: {ignored}' in output
        assert str(repo) in output
    assert path.read_text() == before


@pytest.mark.parametrize('defaults,selection', [(['claude', 'standard'], None), (['claude', 'standard'], [1]), (None, None)])
def test_picker_follows_defaults(tmp_path, monkeypatch, defaults, selection):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    _write_config(tmp_path, [], {'default': defaults} if defaults else None)
    expected = ['standard', 'claude'] if defaults else ['standard', 'claude', 'codex', 'openclaw', 'pi']
    def select(items, header, preselected=None):
        assert items == expected
        assert preselected is None
        return list(range(len(items))) if selection is None else selection
    monkeypatch.setattr('skm.cli.interactive_multi_select', select)
    invoke(tmp_path, 'install', str(repo), 'demo')
    from skm.config import load_config, save_config
    config = load_config(tmp_path / 'config/skills.yaml')
    if selection is None:
        assert config.packages[0].agents is None
        if defaults:
            config.agents.default.append('codex')
            save_config(config, tmp_path / 'config/skills.yaml')
            invoke(tmp_path, 'install')
            assert (tmp_path / 'agents/codex/demo').is_symlink()
    else:
        assert config.packages[0].agents.includes == ['claude']
        assert not (tmp_path / 'agents/standard/demo').exists()


@pytest.mark.parametrize('command', ['install', 'direct', 'update', 'unchanged'])
def test_override_migration(tmp_path, monkeypatch, command):
    monkeypatch.setenv('HOME', str(tmp_path))
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    packages = [{'repo': str(repo)}] if command in ('update', 'unchanged') else [{'local_path': str(repo)}]
    def config_at(path):
        _write_config(tmp_path, packages, {'default': ['claude'], 'override': {'claude': {'path': path}}})
    config_at('~/old')
    invoke(tmp_path, 'install', isolated=False)
    assert (tmp_path / 'old/demo').is_symlink()
    (tmp_path / 'old/manual').mkdir()
    old_lock = _load_lock(tmp_path)
    for args in [('list',), ('list', '--all')]:
        assert 'claude' in invoke(tmp_path, *args, isolated=False)
    config_at('~/new')
    if command == 'update':
        (repo / 'new.txt').write_text('change')
        subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', 'change'], cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr('skm.cli.interactive_multi_select', lambda items, **kwargs: list(range(len(items))))
    args = ('install', str(repo)) if command == 'direct' else ('update', 'demo') if command in ('update', 'unchanged') else ('install',)
    output = invoke(tmp_path, *args, isolated=False)
    if command == 'unchanged':
        assert 'Already up to date' in output
        assert _load_lock(tmp_path) == old_lock
        assert (tmp_path / 'old/demo').is_symlink()
        invoke(tmp_path, 'install', isolated=False)
    else:
        assert 'agent config changed' in output
    assert not (tmp_path / 'old/demo').is_symlink()
    assert (tmp_path / 'old/manual').is_dir()
    assert (tmp_path / 'new/demo').is_symlink()
    assert _load_lock(tmp_path)['skills'][0]['linked_to'] == ['~/new/demo']


def test_materialize_and_list_agents_dir(tmp_path):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    _write_config(tmp_path, [{'local_path': str(repo)}], {'default': ['standard'], 'override': {'standard': {'install_mode': 'materialize'}}})
    invoke(tmp_path, 'install')
    target = tmp_path / 'agents/standard/demo'
    assert target.is_dir() and not target.is_symlink()
    assert 'agents: standard' in invoke(tmp_path, 'list')


@pytest.mark.parametrize('broken', ['agents:\n  override:\n    typo: {}\npackages: []\n', 'packages: ['])
def test_list_bad_config_warns_and_falls_back(tmp_path, broken):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    config = _write_config(tmp_path, [{'local_path': str(repo)}], {'default': ['claude']})
    invoke(tmp_path, 'install')
    config.write_text(broken)
    for args in [('list',), ('list', '--all')]:
        output = invoke(tmp_path, *args)
        assert 'Warning: failed to load config' in output
        assert 'demo' in output and 'claude' in output
    result = CliRunner().invoke(cli, [*_cli_args(tmp_path), 'install'])
    assert result.exit_code != 0
    assert 'Invalid config' in result.output


@pytest.mark.parametrize('change', ['default', 'includes', 'excludes'])
def test_update_removes_deselected_agent(tmp_path, change):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    package = {'repo': str(repo)}
    _write_config(tmp_path, [package], {'default': ['claude', 'codex']})
    invoke(tmp_path, 'install')
    defaults = ['claude', 'codex']
    if change == 'default':
        defaults = ['claude']
    else:
        package['agents'] = {change: ['claude'] if change == 'includes' else ['codex']}
    _write_config(tmp_path, [package], {'default': defaults})
    (repo / 'change.txt').write_text('new commit')
    subprocess.run(['git', 'add', '.'], cwd=repo, check=True, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'change'], cwd=repo, check=True, capture_output=True)
    invoke(tmp_path, 'update', 'demo')
    assert not (tmp_path / 'agents/codex/demo').exists()
    assert (tmp_path / 'agents/claude/demo').is_symlink()
    assert _load_lock(tmp_path)['skills'][0]['linked_to'] == [str(tmp_path / 'agents/claude/demo')]


def test_direct_includes_warning(tmp_path):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    _write_config(tmp_path, [], {'default': ['claude']})
    output = invoke(tmp_path, 'install', str(repo), 'demo', '--agents-includes', 'claude,openclaw')
    assert 'ignored: openclaw' in output
    assert (tmp_path / 'agents/claude/demo').is_symlink()
    assert not (tmp_path / 'agents/openclaw').exists()


def test_list_recognizes_nondefault_but_all_scans_defaults(tmp_path):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    _write_config(tmp_path, [{'local_path': str(repo)}], {'default': ['claude', 'codex']})
    invoke(tmp_path, 'install')
    _write_config(tmp_path, [{'local_path': str(repo)}], {'default': ['claude']})
    assert 'agents: claude, codex' in invoke(tmp_path, 'list')
    assert '[codex]' not in invoke(tmp_path, 'list', '--all')


def test_update_warns_ignored_includes_even_if_current(tmp_path):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    _write_config(tmp_path, [{'repo': str(repo), 'agents': {'includes': ['claude', 'typo']}}], {'default': ['claude']})
    invoke(tmp_path, 'install')
    output = invoke(tmp_path, 'update', 'demo')
    assert 'ignored: typo' in output
    assert 'Already up to date' in output


def test_invalid_direct_config_does_not_clone(tmp_path, monkeypatch):
    _write_config(tmp_path, [], {'override': {'unknown': {}}})
    def unexpected_clone(*args, **kwargs):
        pytest.fail('Invalid configuration must be rejected before cloning')
    monkeypatch.setattr('skm.git.clone_or_pull', unexpected_clone)
    result = CliRunner().invoke(cli, [*_cli_args(tmp_path), 'install', 'https://example.com/unused.git'])
    assert result.exit_code != 0
    assert 'Invalid config' in result.output
    assert 'Unknown agents' in result.output


def test_install_mode_roundtrip(tmp_path):
    repo = _make_skill_repo(tmp_path, 'repo', [{'name': 'demo'}])
    target = tmp_path / 'agents/standard/demo'
    for mode in ['symlink', 'materialize', 'symlink']:
        _write_config(tmp_path, [{'local_path': str(repo)}], {'default': ['standard'], 'override': {'standard': {'install_mode': mode}}})
        invoke(tmp_path, 'install')
        assert target.is_dir()
        assert target.is_symlink() == (mode == 'symlink')
