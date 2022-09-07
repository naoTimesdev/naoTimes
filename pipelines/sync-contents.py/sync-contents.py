import os
import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List

DEV_REPO_DIR = Path(__file__).absolute().parent.parent
TOP_PARENT_DIR = DEV_REPO_DIR.parent

PR_BODY = """This PR is created via a script automation and CI.
It use the owner account to execute it, please ignore it.
"""

SPECIAL_FILES = [
    DEV_REPO_DIR / "requirements.txt",
    DEV_REPO_DIR / "requirements-dev.txt",
    DEV_REPO_DIR / "constraints.txt",
    DEV_REPO_DIR / "config.json.example",
    DEV_REPO_DIR / "bot.py",
    DEV_REPO_DIR / ".gitignore",
    DEV_REPO_DIR / ".flake8",
    DEV_REPO_DIR / "pyproject.toml",
]
SPECIAL_MAPPED_FILES = {"README.prod.md": "README.md"}


parser = argparse.ArgumentParser()
parser.add_argument("-b", "--branch-name", action="store", help="Branch name", required=True)
parser.add_argument("-D", "--dry-run", action="store_true", help="Dry run mode")
args = parser.parse_args()

dry_run: bool = args.dry_run
branch_name: str = args.branch_name

print("-- Preparing repository synchronization")
current_time = datetime.now(tz=timezone.utc)
strftime = current_time.strftime("%Y-%m-%d %H:%M UTC")

print(f"-- Creating branch {branch_name}")
os.chdir(DEV_REPO_DIR)

propagated_files: List[Path] = []
print("-- Propagating naotimes folder...")
for ntfiles in DEV_REPO_DIR.rglob("naotimes/**/*.py"):
    _sfile = str(ntfiles).replace("\\", "/")
    if "__pycache__" in _sfile:
        continue
    if "/private" in _sfile:
        continue
    propagated_files.append(ntfiles)
print("-- Propagating cogs folder...")
for cogsfiles in DEV_REPO_DIR.rglob("cogs/**/*.py"):
    _sfile = str(cogsfiles).replace("\\", "/")
    if "__pycache__" in _sfile:
        continue
    if "/private" in _sfile:
        continue
    propagated_files.append(cogsfiles)
print("-- Propagating pipelines folder...")
for noxfiles in DEV_REPO_DIR.rglob("pipelines/**/*.py"):
    _sfile = str(noxfiles).replace("\\", "/")
    if "__pycache__" in _sfile:
        continue
    if "/private" in _sfile:
        continue
    propagated_files.append(noxfiles)
print("-- Propagating i18n folder...")
for i18nfiles in DEV_REPO_DIR.rglob("i18n/**/*.yaml"):
    _sfile = str(i18nfiles).replace("\\", "/")
    if "__pycache__" in _sfile:
        continue
    if "/private" in _sfile:
        continue
    propagated_files.append(i18nfiles)
print("-- Propagating special files...")
propagated_files.extend(SPECIAL_FILES)


os.chdir(TOP_PARENT_DIR)
print(f"-- Directory changed to {TOP_PARENT_DIR}, cloning naoTimes main repo...")
MAIN_REPO_DIR = DEV_REPO_DIR / "private"
if MAIN_REPO_DIR.exists():
    os.chdir(MAIN_REPO_DIR)
print(f"-- Checking out {branch_name} from rewrite")
if not dry_run:
    os.system("git checkout rewrite")
    os.system("git pull origin rewrite")
else:
    print("  ∟ Dry run mode, skipping git commands")

# Delete old folder if exists
print("-- Cleaning up folder...")
if not dry_run:
    shutil.rmtree(MAIN_REPO_DIR / "naotimes", ignore_errors=True)
    shutil.rmtree(MAIN_REPO_DIR / "cogs", ignore_errors=True)
    shutil.rmtree(MAIN_REPO_DIR / "pipelines", ignore_errors=True)
    shutil.rmtree(MAIN_REPO_DIR / "i18n", ignore_errors=True)
else:
    print("-- Dry run mode, skipping removing old files")

print("-- Copying propagated files...")
for file in propagated_files:
    # Remove absolute path and resolve only the relative path
    relative_path = file.relative_to(DEV_REPO_DIR)
    target_file = MAIN_REPO_DIR / relative_path
    if not dry_run:
        try:
            target_file.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
    print(f"> Copying {file} to {target_file}")
    if not dry_run:
        shutil.copy(file, target_file)
for original, target in SPECIAL_MAPPED_FILES.items():
    from_path = DEV_REPO_DIR / original
    to_path = MAIN_REPO_DIR / target
    if not dry_run:
        try:
            to_path.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
    print(f"> Copying {from_path} to {to_path}")
    if not dry_run:
        shutil.copy(from_path, to_path)
