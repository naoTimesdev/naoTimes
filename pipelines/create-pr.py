import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

DEV_REPO_DIR = Path(__file__).absolute().parent.parent

PR_BODY = """This PR is created automatically using a custom auto-sync actions.
Please review the content before merging to master branch."""

BASE_BRANCH = "rewrite"

parser = argparse.ArgumentParser()
parser.add_argument("-b", "--branch-name", action="store", help="Branch name", required=True)
args = parser.parse_args()

branch_name: str = args.branch_name
GITHUB_TOKEN_SYNC = os.environ.get("GITHUB_TOKEN_SYNC")

if GITHUB_TOKEN_SYNC is None:
    print("No GitHub token provided, aborting")
    print("Either provide it as an argument or set the GITHUB_TOKEN_SYNC environment variable")
    sys.exit(1)


def create_into_list(list_data: list[str]) -> str:
    cleaned_data = ["- " + x.strip() for x in list_data]
    return "\n".join(cleaned_data)


def create_pr(branch_name: str, date: str, pr_body: str):
    res = requests.post(
        "https://api.github.com/repos/naoTimesdev/naoTimes/pulls",
        json={"head": branch_name, "base": BASE_BRANCH, "title": f"[auto-sync] {date}", "body": pr_body},
        headers={
            "Authorization": f"token {GITHUB_TOKEN_SYNC}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    return res.status_code < 400


MAIN_REPO_DIR = DEV_REPO_DIR / "private"
os.chdir(MAIN_REPO_DIR)

print("-- Preparing PR creation")
current_time = datetime.now(tz=UTC)
strftime = current_time.strftime("%Y-%m-%d %H:%M UTC")
print(f"-- Current time: {strftime}")


def _git_changed_files(diff_filter: str) -> list[str]:
    command = f"git diff --name-only --diff-filter={diff_filter} origin/{BASE_BRANCH}...HEAD"
    return [line for line in os.popen(command).read().splitlines() if line.strip()]


print(f"-- Getting changed files against origin/{BASE_BRANCH}")
modified_files = _git_changed_files("MR")
print(f"-- Modified files: {modified_files}")
print("-- Getting added files")
added_files = _git_changed_files("A")
print(f"-- Added files: {added_files}")
print("-- Getting deleted files")
deleted_files = _git_changed_files("D")
print(f"-- Deleted files: {deleted_files}")

if not modified_files and not added_files and not deleted_files:
    print("-- No changes detected, aborting")
    sys.exit(1)

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
    sys.exit(1)
print("-- Done, PR created successfully!")
