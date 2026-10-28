from skm.commands import list_cmd
from skm.lock import save_lock
from skm.types import InstalledSkill, LockFile, ResolvedAgent


def test_run_list_shows_agents_from_compact_lock_paths(monkeypatch, tmp_path, capsys):
    home = tmp_path / 'home'
    monkeypatch.setenv('HOME', str(home))
    agents = {
        'standard': ResolvedAgent(path=str(home / '.agents/skills')),
        'claude': ResolvedAgent(path=str(home / '.config/claude/skills')),
    }

    lock_path = tmp_path / 'skills-lock.yaml'
    save_lock(
        LockFile(
            skills=[
                InstalledSkill(
                    name='my-skill',
                    repo='https://example.com/repo.git',
                    commit='abc1234',
                    skill_path='skills/my-skill',
                    linked_to=[
                        '~/.agents/skills/my-skill',
                        '~/.config/claude/skills/my-skill',
                    ],
                )
            ]
        ),
        lock_path,
    )

    list_cmd.run_list(lock_path, agents)

    output = capsys.readouterr().out
    assert 'my-skill' in output
    assert 'agents: claude, standard' in output
