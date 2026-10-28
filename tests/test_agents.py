from pathlib import Path

import pytest

from skm.agents import resolve_agents
from skm.types import GlobalAgentsConfig, BUILTIN_AGENTS
from skm.commands.list_cmd import _agent_name_from_link


@pytest.mark.parametrize('env,override,cli_dir,expected', [
    (None, None, None, '~/.pi/agent/skills'),
    ('', None, None, '~/.pi/agent/skills'),
    ('~/pi-home', None, None, '~/pi-home/skills'),
    ('~/pi-home', '~/custom', None, '~/custom'),
    ('~/pi-home', '~/custom', '~/test', '~/test/pi'),
])
def test_path_priority(tmp_path, monkeypatch, env, override, cli_dir, expected):
    monkeypatch.setenv('HOME', str(tmp_path))
    monkeypatch.delenv('PI_CODING_AGENT_DIR', raising=False)
    if env is not None:
        monkeypatch.setenv('PI_CODING_AGENT_DIR', env)
    config = GlobalAgentsConfig(default=['pi'], override={'pi': {'path': override, 'install_mode': 'materialize'}})
    resolved = resolve_agents(config, cli_dir)
    assert list(resolved) == ['pi']
    assert resolved['pi'].path == str(Path(expected).expanduser())
    assert resolved['pi'].install_mode == 'materialize'


def test_runtime_environment_and_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    for name, spec in BUILTIN_AGENTS.items():
        if spec.env_var:
            monkeypatch.delenv(spec.env_var, raising=False)
        agent = resolve_agents(None)[name]
        assert agent.path == str(Path(spec.path).expanduser())
        assert agent.install_mode == ('materialize' if name == 'openclaw' else 'symlink')
        if spec.env_var:
            monkeypatch.setenv(spec.env_var, '~/custom')
            assert resolve_agents(None)[name].path == str(tmp_path / 'custom/skills')


def test_all_agents_and_exact_parent(monkeypatch, tmp_path):
    monkeypatch.setenv('HOME', str(tmp_path))
    config = GlobalAgentsConfig(default=['claude'])
    agents = resolve_agents(config, default_only=False)
    assert _agent_name_from_link('~/.agents/skills-extra/demo', agents) is None
    assert _agent_name_from_link('~/.agents/skills/demo', agents) == 'standard'
    assert resolve_agents(GlobalAgentsConfig(default=[])) == {}


def test_path_override_keeps_builtin_mode(tmp_path):
    config = GlobalAgentsConfig(override={'openclaw': {'path': str(tmp_path)}})
    agent = resolve_agents(config)['openclaw']
    assert agent.path == str(tmp_path)
    assert agent.install_mode == 'materialize'
