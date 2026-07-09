# coding: utf-8
"""真实 Git 仓库测试工具。"""
from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """在指定目录执行 git 命令,失败时保留 stdout/stderr 方便定位。"""
    result = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result


def init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "-c", "init.defaultBranch=master", "init")
    configure_user(path)
    return path


def init_bare_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "-c", "init.defaultBranch=master", "init", "--bare")
    return path


def clone_repo(remote: Path, path: Path) -> Path:
    run_git(path.parent, "clone", str(remote), path.name)
    configure_user(path)
    return path


def configure_user(repo: Path) -> None:
    run_git(repo, "config", "user.name", "Gitora Test")
    run_git(repo, "config", "user.email", "gitora-test@example.invalid")
    run_git(repo, "config", "commit.gpgsign", "false")
    run_git(repo, "config", "core.autocrlf", "false")


def write_file(repo: Path, relative_path: str, content: str) -> Path:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def commit_all(repo: Path, message: str) -> str:
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()
