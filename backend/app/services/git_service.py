from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BranchInfo:
    name: str
    is_remote: bool
    last_commit_sha: str
    last_commit_message: str
    last_commit_date: datetime | None
    ahead_of_main: int | None = None
    behind_main: int | None = None


@dataclass
class CommitInfo:
    sha: str
    message: str
    author_name: str
    author_email: str
    date: datetime


class GitError(RuntimeError):
    pass


class GitService:
    def __init__(self, repo_path: str | Path):
        self.repo = Path(repo_path)

    def _run(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.repo,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise GitError(result.stderr.strip())
            return result.stdout.strip()
        except subprocess.TimeoutExpired:
            raise GitError("Git command timed out")

    def list_branches(self) -> list[BranchInfo]:
        out = self._run("branch", "--format=%(refname:short)|%(objectname:short)|%(subject)|%(creatordate:iso-strict)")
        branches = []
        for line in out.split("\n"):
            if not line:
                continue
            parts = line.split("|", 3)
            name = parts[0]
            date = None
            try:
                date = datetime.fromisoformat(parts[3]) if len(parts) > 3 else None
            except (ValueError, IndexError):
                pass
            branches.append(BranchInfo(
                name=name,
                is_remote=False,
                last_commit_sha=parts[1] if len(parts) > 1 else "",
                last_commit_message=parts[2] if len(parts) > 2 else "",
                last_commit_date=date,
            ))
        # Get ahead/behind for non-main branches
        for b in branches:
            if b.name != "main" and not b.is_remote:
                try:
                    ahead = self._run("rev-list", "--count", f"main..{b.name}")
                    behind = self._run("rev-list", "--count", f"{b.name}..main")
                    b.ahead_of_main = int(ahead)
                    b.behind_main = int(behind)
                except GitError:
                    pass
        return branches

    def create_branch(self, name: str, source: str = "main") -> None:
        self._run("checkout", source)
        self._run("checkout", "-b", name)
        self._run("push", "-u", "origin", name)

    def delete_branch(self, name: str) -> None:
        self._run("branch", "-D", name)
        try:
            self._run("push", "origin", "--delete", name)
        except GitError:
            pass

    def list_commits(self, branch: str = "HEAD", limit: int = 50) -> list[CommitInfo]:
        out = self._run(
            "log", branch, f"-{limit}",
            "--format=%H|%an|%ae|%aI|%s",
        )
        commits = []
        for line in out.split("\n"):
            if not line:
                continue
            parts = line.split("|", 4)
            commits.append(CommitInfo(
                sha=parts[0],
                author_name=parts[1],
                author_email=parts[2],
                date=datetime.fromisoformat(parts[3]),
                message=parts[4] if len(parts) > 4 else "",
            ))
        return commits

    def get_diff(self, base: str, head: str) -> str:
        return self._run("diff", f"{base}..{head}")

    def merge(self, source: str, target: str) -> str:
        self._run("checkout", target)
        out = self._run("merge", source, "--no-ff", "-m", f"Merge {source} into {target}")
        self._run("push", "origin", target)
        return out

    def push(self, branch: str) -> None:
        self._run("push", "origin", branch)

    def current_branch(self) -> str:
        return self._run("rev-parse", "--abbrev-ref", "HEAD")