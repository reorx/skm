import subprocess

import click
import pytest
from skm.git import clone_or_pull, get_head_commit, repo_url_to_dirname


def test_repo_url_to_dirname():
    assert repo_url_to_dirname("https://github.com/vercel-labs/agent-skills") == "github.com_vercel-labs_agent-skills"
    assert repo_url_to_dirname("http://github.com/better-auth/skills") == "github.com_better-auth_skills"


def test_clone_and_get_commit(tmp_path):
    """Create a local git repo, clone it, and check commit."""
    # Set up a source repo
    src = tmp_path / "source"
    src.mkdir()
    subprocess.run(["git", "init"], cwd=src, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=src, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=src, capture_output=True)
    (src / "README.md").write_text("hello")
    subprocess.run(["git", "add", "."], cwd=src, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=src, capture_output=True)

    # Clone it
    dest = tmp_path / "dest"
    clone_or_pull(str(src), dest)
    assert (dest / "README.md").exists()

    commit = get_head_commit(dest)
    assert len(commit) == 40  # full SHA

    # Pull again (should not error)
    clone_or_pull(str(src), dest)


def test_clone_uses_partial_clone_by_default(tmp_path, monkeypatch):
    calls = []

    def fake_run_cmd(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr("skm.git.run_cmd", fake_run_cmd)

    dest = tmp_path / "store" / "repo"
    clone_or_pull("https://github.com/example/repo", dest)

    assert calls == [
        (
            ["git", "clone", "--filter=blob:none", "https://github.com/example/repo", str(dest)],
            {},
        )
    ]


def test_clone_uses_depth_for_shallow_strategy(tmp_path, monkeypatch):
    calls = []

    def fake_run_cmd(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="")

    monkeypatch.setattr("skm.git.run_cmd", fake_run_cmd)

    dest = tmp_path / "store" / "repo"
    clone_or_pull("https://github.com/example/repo", dest, clone_strategy="shallow")

    assert calls == [
        (
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--depth",
                "1",
                "https://github.com/example/repo",
                str(dest),
            ],
            {},
        )
    ]


@pytest.mark.network
def test_clone_real_repo(tmp_path):
    """Clone a real GitHub repo successfully."""
    dest = tmp_path / "firecrawl-cli"
    clone_or_pull("https://github.com/firecrawl/cli", dest)
    assert (dest / ".git").exists()

    commit = get_head_commit(dest)
    assert len(commit) == 40


@pytest.mark.network
def test_clone_nonexistent_repo(tmp_path):
    """Cloning a non-existent repo raises click.ClickException with stderr info."""
    dest = tmp_path / "bad-clone"
    with pytest.raises(click.ClickException) as exc_info:
        clone_or_pull("https://github.com/this-org-does-not-exist-skm-test/nonexistent-repo-xyz", dest)
    assert "stderr:" in exc_info.value.message
