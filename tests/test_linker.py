import errno
import shutil

import pytest

import skm.linker as linker
from skm.linker import resolve_target_agents, link_skill, unlink_skill
from skm.types import AgentSpec


def test_resolve_target_agents_all(tmp_path):
    """No includes/excludes → all agents."""
    agents = {'claude': AgentSpec(path=str(tmp_path / 'claude')), 'codex': AgentSpec(path=str(tmp_path / 'codex'))}
    result = resolve_target_agents(None, agents)
    assert set(result.keys()) == {'claude', 'codex'}


def test_resolve_target_agents_excludes(tmp_path):
    agents = {
        'claude': AgentSpec(path=str(tmp_path / 'claude')),
        'codex': AgentSpec(path=str(tmp_path / 'codex')),
        'openclaw': AgentSpec(path=str(tmp_path / 'openclaw')),
    }
    from skm.types import AgentsConfig

    cfg = AgentsConfig(excludes=['openclaw'])
    result = resolve_target_agents(cfg, agents)
    assert 'openclaw' not in result
    assert 'claude' in result


def test_resolve_target_agents_includes(tmp_path):
    agents = {
        'claude': AgentSpec(path=str(tmp_path / 'claude')),
        'codex': AgentSpec(path=str(tmp_path / 'codex')),
        'openclaw': AgentSpec(path=str(tmp_path / 'openclaw')),
    }
    from skm.types import AgentsConfig

    cfg = AgentsConfig(includes=['claude'])
    result = resolve_target_agents(cfg, agents)
    assert set(result.keys()) == {'claude'}


def test_resolve_target_agents_includes_unknown_returns_empty(tmp_path):
    agents = {
        'claude': AgentSpec(path=str(tmp_path / 'claude')),
        'codex': AgentSpec(path=str(tmp_path / 'codex')),
    }
    from skm.types import AgentsConfig

    cfg = AgentsConfig(includes=['unknown'])
    result = resolve_target_agents(cfg, agents)
    assert result == {}


def test_resolve_target_agents_excludes_unknown_is_noop(tmp_path):
    agents = {
        'claude': AgentSpec(path=str(tmp_path / 'claude')),
        'codex': AgentSpec(path=str(tmp_path / 'codex')),
    }
    from skm.types import AgentsConfig

    cfg = AgentsConfig(excludes=['unknown'])
    result = resolve_target_agents(cfg, agents)
    assert set(result.keys()) == {'claude', 'codex'}


def test_link_skill(tmp_path):
    """Link a skill dir to an agent skill dir."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    (skill_src / 'SKILL.md').write_text('---\nname: my-skill\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)))
    assert linked.is_symlink()
    assert linked.resolve() == skill_src.resolve()
    assert linked.name == 'my-skill'
    assert status == 'new'


def test_link_skill_already_linked(tmp_path):
    """Re-linking same source is idempotent."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)))
    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)))
    assert linked.is_symlink()
    assert status == 'exists'


def test_link_skill_existing_dir_raises(tmp_path):
    """Non-symlink dir at target raises FileExistsError."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)
    # Create a real directory at the target
    (agent_dir / 'my-skill').mkdir()
    (agent_dir / 'my-skill' / 'some-file.md').write_text('hello')

    with pytest.raises(FileExistsError):
        link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)))


def test_link_skill_force_overrides_dir(tmp_path):
    """force=True removes existing dir and creates symlink."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)
    # Create a real directory at the target
    (agent_dir / 'my-skill').mkdir()
    (agent_dir / 'my-skill' / 'some-file.md').write_text('hello')

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)), force=True)
    assert linked.is_symlink()
    assert linked.resolve() == skill_src.resolve()
    assert status == 'new'


def test_link_skill_force_overrides_file(tmp_path):
    """force=True removes existing file and creates symlink."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)
    # Create a regular file at the target
    (agent_dir / 'my-skill').write_text('not a symlink')

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)), force=True)
    assert linked.is_symlink()
    assert linked.resolve() == skill_src.resolve()
    assert status == 'new'


def test_link_skill_different_source_replaces(tmp_path):
    """Symlink pointing to different source gets replaced."""
    skill_src_1 = tmp_path / 'store1' / 'my-skill'
    skill_src_1.mkdir(parents=True)
    skill_src_2 = tmp_path / 'store2' / 'my-skill'
    skill_src_2.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    link_skill(skill_src_1, 'my-skill', AgentSpec(path=str(agent_dir)))
    linked, status = link_skill(skill_src_2, 'my-skill', AgentSpec(path=str(agent_dir)))
    assert linked.is_symlink()
    assert linked.resolve() == skill_src_2.resolve()
    assert status == 'replaced'


def test_link_skill_hardlink_mode_falls_back_to_reflink(monkeypatch, tmp_path):
    """Hardlink mode falls back to reflink/COW clone when source and target devices differ."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    source_file = skill_src / 'SKILL.md'
    source_file.write_text('---\nname: my-skill\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')
    monkeypatch.setattr(linker, '_clone_file_reflink', lambda src, dst: shutil.copy2(src, dst))

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))

    cloned_file = linked / 'SKILL.md'
    assert linked.is_dir() and not linked.is_symlink()
    assert status == 'new'
    assert cloned_file.read_text() == source_file.read_text()
    assert cloned_file.stat().st_ino != source_file.stat().st_ino


def test_link_skill_reuses_existing_materialized_copy(monkeypatch, tmp_path):
    """Hardlink mode accepts an existing managed reflink-style copy on reinstall."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    skill_file = skill_src / 'SKILL.md'
    skill_file.write_text('---\nname: my-skill\ndescription: before\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')
    monkeypatch.setattr(linker, '_clone_file_reflink', lambda src, dst: shutil.copy2(src, dst))

    skill_file.write_text('---\nname: my-skill\ndescription: after\n---\n')
    link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))
    skill_file.write_text('---\nname: my-skill\ndescription: after\n---\n')
    (skill_src / 'extra.md').write_text('new content')
    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))
    assert linked.is_dir() and not linked.is_symlink()
    assert status == 'exists'
    assert (linked / 'SKILL.md').read_text() == skill_file.read_text()
    assert (linked / 'extra.md').read_text() == 'new content'


def test_link_skill_materialized_copy_warns_about_stale_files(monkeypatch, tmp_path, capsys):
    """Reinstalling a managed materialized copy should warn about stale files without removing them."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    (skill_src / 'SKILL.md').write_text('---\nname: my-skill\n---\n')
    stale_source = skill_src / 'stale.md'
    stale_source.write_text('old content')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')
    monkeypatch.setattr(linker, '_clone_file_reflink', lambda src, dst: shutil.copy2(src, dst))

    link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))
    stale_source.unlink()

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))

    assert linked.is_dir() and not linked.is_symlink()
    assert status == 'exists'
    assert (linked / 'stale.md').exists()
    assert 'contains stale files that were not removed' in capsys.readouterr().out


def test_link_skill_reflink_mode_falls_back_to_copy(monkeypatch, tmp_path):
    """Unsupported reflink errors fall back to a plain copy."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    source_file = skill_src / 'SKILL.md'
    source_file.write_text('---\nname: my-skill\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')

    def _raise_unsupported(_src, _dst):
        raise OSError(errno.ENOTSUP, 'no reflink here')

    monkeypatch.setattr(linker, '_clone_file_reflink', _raise_unsupported)

    linked, status = link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))

    copied_file = linked / 'SKILL.md'
    assert linked.is_dir() and not linked.is_symlink()
    assert status == 'new'
    assert copied_file.read_text() == source_file.read_text()
    assert copied_file.stat().st_ino != source_file.stat().st_ino


def test_link_skill_reflink_mode_preserves_unhandled_oserror(monkeypatch, tmp_path):
    """Unexpected reflink errors should not be swallowed."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    (skill_src / 'SKILL.md').write_text('---\nname: my-skill\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')

    def _raise_unexpected(_src, _dst):
        raise OSError(errno.EIO, 'disk error')

    monkeypatch.setattr(linker, '_clone_file_reflink', _raise_unexpected)

    with pytest.raises(OSError, match='disk error'):
        link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir), install_mode='materialize'))


def test_link_skill_materialized_force_overrides_file(monkeypatch, tmp_path):
    """force=True should replace an existing plain file with a materialized copy."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    source_file = skill_src / 'SKILL.md'
    source_file.write_text('---\nname: my-skill\n---\n')

    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)
    (agent_dir / 'my-skill').write_text('plain file')

    monkeypatch.setattr(linker, '_select_materialization_mode', lambda *_args: 'reflink')
    monkeypatch.setattr(linker, '_clone_file_reflink', lambda src, dst: shutil.copy2(src, dst))

    linked, status = link_skill(
        skill_src,
        'my-skill',
        AgentSpec(path=str(agent_dir), install_mode='materialize'),
        force=True,
    )

    copied_file = linked / 'SKILL.md'
    assert linked.is_dir() and not linked.is_symlink()
    assert status == 'replaced'
    assert copied_file.read_text() == source_file.read_text()


def test_select_materialization_mode_uses_reflink_across_devices(monkeypatch, tmp_path):
    class _Stat:
        def __init__(self, st_dev):
            self.st_dev = st_dev

    class _FakePath:
        def __init__(self, name, st_dev):
            self._name = name
            self._stat = _Stat(st_dev)

        def stat(self):
            return self._stat

        def __str__(self):
            return self._name

    src_a = _FakePath('src-a', 11)
    target_dir = _FakePath('target', 22)
    monkeypatch.setattr(linker, 'reflink_supported', lambda: True)

    assert linker._select_materialization_mode(src_a, target_dir) == 'reflink'


def test_select_materialization_mode_uses_copy_without_fcntl(monkeypatch, tmp_path):
    class _Stat:
        def __init__(self, st_dev):
            self.st_dev = st_dev

    class _FakePath:
        def __init__(self, name, st_dev):
            self._name = name
            self._stat = _Stat(st_dev)

        def stat(self):
            return self._stat

        def __str__(self):
            return self._name

    src_path = _FakePath('src', 11)
    target_dir = _FakePath('target', 22)
    monkeypatch.setattr(linker, 'reflink_supported', lambda: False)

    assert linker._select_materialization_mode(src_path, target_dir) == 'copy'


def test_unlink_skill(tmp_path):
    """Unlink removes the symlink."""
    skill_src = tmp_path / 'store' / 'my-skill'
    skill_src.mkdir(parents=True)
    agent_dir = tmp_path / 'agent' / 'skills'
    agent_dir.mkdir(parents=True)

    link_skill(skill_src, 'my-skill', AgentSpec(path=str(agent_dir)))
    target = agent_dir / 'my-skill'
    assert target.is_symlink()

    unlink_skill('my-skill', str(agent_dir))
    assert not target.exists()
