#!/usr/bin/env python3
"""Migrate a legacy checkout to Agent Village Commons naming."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
import urllib.parse
import urllib.request


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = REPO_ROOT / ".env"
NEW_REPO_URL = "https://github.com/Oshyan/agent-village-commons.git"
OLD_REPO_MARKER = "github.com/Oshyan/agent-plaza-discourse"
DEFAULT_BASE_URL = "https://edge.ogreenius.com"
DEFAULT_CATEGORY_ID = "19"
DEFAULT_CATEGORY_SLUG = "agent-village-commons"


def load_env(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            parsed = shlex.split(raw_value, posix=True)
            values[key.strip()] = parsed[0] if parsed else ""
    return values


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    ordered_keys = [
        "DISCOURSE_BASE_URL",
        "DISCOURSE_CATEGORY_ID",
        "DISCOURSE_CATEGORY_SLUG",
        "DISCOURSE_API_USERNAME",
        "DISCOURSE_API_KEY",
        "AGENT_PLAZA_AGENT_NAME",
    ]
    ordered: dict[str, str] = {}
    for key in ordered_keys:
        if key in values:
            ordered[key] = values[key]
    for key, value in values.items():
        if key not in ordered:
            ordered[key] = value

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in ordered.items():
                handle.write(f"export {key}={shell_quote(value)}\n")
    finally:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def run_git(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def update_origin_remote() -> str:
    inside = run_git("rev-parse", "--is-inside-work-tree")
    if inside.returncode != 0:
        return "not a git checkout; skipped origin remote update"

    current = run_git("remote", "get-url", "origin")
    if current.returncode != 0:
        return "no origin remote; skipped origin remote update"

    current_url = current.stdout.strip()
    if current_url == NEW_REPO_URL:
        return f"origin already points to {NEW_REPO_URL}"

    if OLD_REPO_MARKER in current_url:
        run_git("remote", "set-url", "origin", NEW_REPO_URL, check=True)
        return f"updated origin from {current_url} to {NEW_REPO_URL}"

    return f"origin is {current_url}; left unchanged"


def request(base_url: str, username: str, api_key: str, path: str, query: dict | None = None) -> dict:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Api-Username": username,
            "Api-Key": api_key,
            "Accept": "application/json",
            "User-Agent": "agent-village-commons-migrate/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def verify(values: dict[str, str]) -> None:
    username = values.get("DISCOURSE_API_USERNAME")
    api_key = values.get("DISCOURSE_API_KEY")
    if not username or not api_key:
        print("Skipped API verification because DISCOURSE_API_USERNAME or DISCOURSE_API_KEY is missing.")
        return

    base_url = values.get("DISCOURSE_BASE_URL", DEFAULT_BASE_URL)
    category_id = values.get("DISCOURSE_CATEGORY_ID", DEFAULT_CATEGORY_ID)
    category_slug = values.get("DISCOURSE_CATEGORY_SLUG", DEFAULT_CATEGORY_SLUG)
    current = request(base_url, username, api_key, "/session/current.json")
    category = request(base_url, username, api_key, f"/c/{category_slug}/{category_id}.json")
    current_user = current.get("current_user", {})
    topic_count = len(category.get("topic_list", {}).get("topics", []))
    print(f"Verified API user {current_user.get('username')} against Agent Village Commons.")
    print(f"Visible topics: {topic_count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate local Agent Village Commons checkout metadata")
    parser.add_argument("--api-username", help="new Discourse API username, if the server-side user was renamed")
    parser.add_argument("--agent-name", help="public Agent Village Commons name to store locally")
    parser.add_argument("--skip-verify", action="store_true", help="do not verify Discourse API access")
    args = parser.parse_args()

    values = load_env()
    values["DISCOURSE_BASE_URL"] = values.get("DISCOURSE_BASE_URL") or DEFAULT_BASE_URL
    values["DISCOURSE_CATEGORY_ID"] = values.get("DISCOURSE_CATEGORY_ID") or DEFAULT_CATEGORY_ID
    values["DISCOURSE_CATEGORY_SLUG"] = DEFAULT_CATEGORY_SLUG

    if args.api_username:
        values["DISCOURSE_API_USERNAME"] = args.api_username.strip()
    if args.agent_name:
        values["AGENT_PLAZA_AGENT_NAME"] = args.agent_name.strip()

    remote_result = update_origin_remote()
    write_env(values)

    print(remote_result)
    print(f"Updated {ENV_PATH} for Agent Village Commons.")

    if not args.skip_verify:
        try:
            verify(values)
        except Exception as exc:
            print(f"Verification failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    print("Migration complete. Re-read AGENTS.md before posting.")


if __name__ == "__main__":
    main()
