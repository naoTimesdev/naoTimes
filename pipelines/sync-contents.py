#!/usr/bin/env python3
"""Copy the bot source from the development repo into the public mirror checkout.

The public repository is a curated mirror: internal notes (``docs/``), deployment
helpers and secrets are intentionally not published. Managed directories are
replaced wholesale so files deleted in the dev repo also disappear from the
mirror, and files that the dev repo no longer uses are removed explicitly.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEV_REPO_DIR = Path(__file__).absolute().parent.parent
DEFAULT_TARGET = DEV_REPO_DIR / "private"
BASE_BRANCH = "rewrite"

# Root files copied as-is. Every entry must exist in the dev repo.
ROOT_FILES = (
    ".deepsource.toml",
    ".gitignore",
    ".python-version",
    "bot.py",
    "config.json.example",
    "crowdin.yml",
    "cryptodata.json",
    "currencydata.json",
    "pyproject.toml",
    "renovate.json",
    "ruff.toml",
    "streaming_lists.json.gz",
    "uv.lock",
)

# Source path -> destination path, for files that are renamed in the mirror.
MAPPED_FILES = {
    "README.prod.md": "README.md",
}

# Directories replaced wholesale on every sync.
MANAGED_DIRECTORIES = (
    "cogs",
    "i18n",
    "naotimes",
    "pipelines",
    "tests",
)

# Workflows published to the mirror. Other files under .github are left alone.
MANAGED_WORKFLOWS = {
    ".github/workflows/lint.yml": ".github/workflows/lint.yml",
}

# Mirror files that the current dev repo no longer uses.
LEGACY_PATHS = (
    ".flake8",
    ".github/workflows/ci.yml",
    ".pre-commit-config.yaml",
    "constraints.txt",
    "requirements-dev.txt",
    "requirements.txt",
)

IGNORE_PATTERNS = ("__pycache__", "*.pyc", "*.pyo", ".DS_Store")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Synchronize the public mirror checkout.")
    parser.add_argument("-b", "--branch-name", required=True, help="Target branch name (for logging)")
    parser.add_argument("-D", "--dry-run", action="store_true", help="Print the actions without changing files")
    parser.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_TARGET,
        help="Path to the public repo checkout (default: <dev repo>/private)",
    )
    return parser.parse_args()


def _run_git(target: Path, *args: str, dry_run: bool) -> None:
    print("$ git " + " ".join(args))
    if dry_run:
        return
    subprocess.run(["git", *args], cwd=target, check=True)


def _copy_file(source: Path, target: Path, dry_run: bool) -> None:
    print(f"> copy {source.relative_to(DEV_REPO_DIR)} -> {target}")
    if dry_run:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_directory(source: Path, target: Path, dry_run: bool) -> None:
    print(f"> copy {source.relative_to(DEV_REPO_DIR)}/ -> {target}/")
    if dry_run:
        return
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))


def _missing_sources() -> list[str]:
    missing = [name for name in ROOT_FILES if not (DEV_REPO_DIR / name).is_file()]
    missing += [name for name in MAPPED_FILES if not (DEV_REPO_DIR / name).is_file()]
    missing += [name for name in MANAGED_WORKFLOWS if not (DEV_REPO_DIR / name).is_file()]
    missing += [name for name in MANAGED_DIRECTORIES if not (DEV_REPO_DIR / name).is_dir()]
    return missing


def main() -> int:
    args = parse_args()
    target = args.target.absolute()
    dry_run: bool = args.dry_run

    print(f"-- Syncing {DEV_REPO_DIR} -> {target} (branch {args.branch_name})")
    if not target.is_dir():
        print(f"Target checkout does not exist: {target}", file=sys.stderr)
        return 1

    missing = _missing_sources()
    if missing:
        print("Missing source files/directories: " + ", ".join(missing), file=sys.stderr)
        return 1

    _run_git(target, "fetch", "origin", BASE_BRANCH, dry_run=dry_run)
    _run_git(target, "reset", "--hard", f"origin/{BASE_BRANCH}", dry_run=dry_run)
    _run_git(target, "clean", "-fd", dry_run=dry_run)

    for directory in MANAGED_DIRECTORIES:
        _copy_directory(DEV_REPO_DIR / directory, target / directory, dry_run)
    for name in ROOT_FILES:
        _copy_file(DEV_REPO_DIR / name, target / name, dry_run)
    for source_name, target_name in MAPPED_FILES.items():
        _copy_file(DEV_REPO_DIR / source_name, target / target_name, dry_run)
    for source_name, target_name in MANAGED_WORKFLOWS.items():
        _copy_file(DEV_REPO_DIR / source_name, target / target_name, dry_run)

    for legacy in LEGACY_PATHS:
        path = target / legacy
        print(f"> remove {legacy}")
        if not dry_run and path.exists():
            path.unlink()

    print("-- Synchronization complete")
    print(
        f"-- {len(ROOT_FILES) + len(MAPPED_FILES) + len(MANAGED_WORKFLOWS)} root files, "
        f"{len(MANAGED_DIRECTORIES)} directories"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
