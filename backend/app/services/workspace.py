from __future__ import annotations

import os
import subprocess
from pathlib import Path

from app.models.git_config import GitConfig
from app.models.project import Project
from app.models.user import User


WORKSPACE_ROOT = Path("/workspace")


async def ensure_workspace(
    user: User, project: Project, git_config: GitConfig
) -> Path:
    """Ensure the user's workspace has the project repo cloned/pulled.

    Returns the repo path inside the workspace.
    """
    user_dir = WORKSPACE_ROOT / user.id
    repo_dir = user_dir / "repo"

    # Setup SSH if needed
    if git_config.auth_type == "ssh" and git_config.credentials_encrypted:
        ssh_dir = user_dir / ".ssh"
        ssh_dir.mkdir(parents=True, exist_ok=True)
        key_path = ssh_dir / "id_ed25519"
        key_path.write_text(git_config.credentials_encrypted)
        key_path.chmod(0o600)

        # Write SSH config
        ssh_config = ssh_dir / "config"
        if not ssh_config.exists():
            ssh_config.write_text("StrictHostKeyChecking no\n")

    # Setup git config
    gitconfig_path = user_dir / ".gitconfig"
    if not gitconfig_path.exists():
        _run_git(
            ["config", "--file", str(gitconfig_path), "user.name", user.display_name],
            cwd=str(user_dir),
        )
        _run_git(
            ["config", "--file", str(gitconfig_path), "user.email", user.email],
            cwd=str(user_dir),
        )

    env = _git_env(git_config, user_dir)

    if repo_dir.exists() and (repo_dir / ".git").exists():
        # Pull latest
        _run_git(["fetch", "--all"], cwd=str(repo_dir), env=env)
        _run_git(
            ["checkout", git_config.default_branch],
            cwd=str(repo_dir),
            env=env,
        )
        _run_git(["pull", "--ff-only"], cwd=str(repo_dir), env=env)
    else:
        # Fresh clone
        repo_dir.mkdir(parents=True, exist_ok=True)
        _run_git(
            ["clone", git_config.repo_url, str(repo_dir)],
            cwd=str(user_dir),
            env=env,
        )
        _run_git(
            ["checkout", git_config.default_branch],
            cwd=str(repo_dir),
            env=env,
        )

    return repo_dir


def _git_env(git_config: GitConfig, user_dir: Path) -> dict:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = f"ssh -i {user_dir}/.ssh/id_ed25519 -o StrictHostKeyChecking=no"
    env["HOME"] = str(user_dir)
    env["GIT_TERMINAL_PROMPT"] = "0"
    if git_config.auth_type == "https" and git_config.credentials_encrypted:
        # Use credentials in URL for HTTPS
        pass  # Credentials are embedded in repo_url
    return env


def _run_git(args: list[str], cwd: str, env: dict | None = None) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()