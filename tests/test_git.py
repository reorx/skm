import subprocess
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
