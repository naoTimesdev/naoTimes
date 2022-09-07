import os
import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import requests

DEV_REPO_DIR = Path(__file__).absolute().parent.parent
TOP_PARENT_DIR = DEV_REPO_DIR.parent

PR_BODY = """This PR is created automatically using a custom auto-sync actions.
Please review the content before merging to master branch."""

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--branch-name", action="store", help="Branch name", required=True)
args = parser.parse_args()

branch_name: str = args.branch_name
GITHUB_TOKEN_SYNC = os.environ.get("GITHUB_TOKEN_SYNC")

if GITHUB_TOKEN_SYNC is None:
    print("No GitHub token provided, aborting")
    print("Either provide it as an argument or set the GITHUB_TOKEN_SYNC environment variable")
    exit(1)


def create_into_list(list_data: List[str]) -> str:
    cleaned_data = ["- " + x.strip() for x in list_data]
    return "\n".join(cleaned_data)


def create_pr(branch_name: str, date: str, pr_body: str):
    res = requests.post(
        "https://api.github.com/repos/noaione/naoTimes/pulls",
        json={"head": branch_name, "base": "rewrite", "title": f"[auto-sync] {date}", "body": pr_body},
        headers={
            "Authorization": f"token {GITHUB_TOKEN_SYNC}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    return res.status_code < 400


MAIN_REPO_DIR = TOP_PARENT_DIR / "private"
os.chdir(MAIN_REPO_DIR)

print("-- Preparing PR creation")
current_time = datetime.now(tz=timezone.utc)
strftime = current_time.strftime("%Y-%m-%d %H:%M UTC")
print(f"-- Current time: {strftime}")

print("-- Getting modified files")
modified_files = os.popen("git diff --name-only").read().splitlines()
print(f"-- Modified files: {modified_files}")
print("-- Getting added files")
added_files = os.popen("git ls-files --others --exclude-standard").read().splitlines()
print(f"-- Added files: {added_files}")
deleted_files = os.popen("git ls-files --deleted --exclude-standard").read().splitlines()

if not modified_files and not added_files and not deleted_files:
    print("-- No changes detected, aborting")
    exit(1)

ACTUAL_PR_BODY = PR_BODY

if added_files:
    added_body = create_into_list(added_files)
    ACTUAL_PR_BODY += "\n\n**Added files**\n" + added_body
if modified_files:
    modified_body = create_into_list(modified_files)
    ACTUAL_PR_BODY += "\n\n**Modified files**\n" + modified_body
if deleted_files:
    deleted_body = create_into_list(deleted_files)
    ACTUAL_PR_BODY += "\n\n**Deleted files**\n" + deleted_body

is_success = create_pr(branch_name, strftime, ACTUAL_PR_BODY)
if not is_success:
    print("-- PR creation failed")
    exit(1)
print("-- Done, PR created successfully!")
