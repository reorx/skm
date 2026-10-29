import pytest

from skm.utils import compact_path


@pytest.mark.parametrize('trailing_slash', ['', '/'])
@pytest.mark.parametrize(
    'suffix,expected',
    [('', '~'), ('/skills/demo', '~/skills/demo'), ('2/skills', None), ('-data/skills', None)],
)
def test_compact_path_home_boundary(tmp_path, monkeypatch, trailing_slash, suffix, expected):
    home = str(tmp_path / 'home')
    monkeypatch.setenv('HOME', home + trailing_slash)
    path = home + suffix
    assert compact_path(path) == (path if expected is None else expected)


def test_compact_path_unrelated(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path / 'home'))
    path = str(tmp_path / 'elsewhere/skills')
    assert compact_path(path) == path
