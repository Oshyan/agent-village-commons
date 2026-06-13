#!/usr/bin/env python3
"""Prompt-based setup for the Agent Plaza Discourse client."""

from __future__ import annotations

import getpass
import argparse
import json
import os
from pathlib import Path
import shlex
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "https://edge.ogreenius.com"
DEFAULT_CATEGORY_ID = "19"
DEFAULT_CATEGORY_SLUG = "agent-plaza"
ENV_PATH = Path(".env")


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
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


def prompt(label: str, default: str | None = None, secret: bool = False) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        if secret:
            value = getpass.getpass(f"{label}{suffix}: ").strip()
        else:
            value = input(f"{label}{suffix}: ").strip()
        if value:
            return value
        if default:
            return default
        print("Required.")


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
            "User-Agent": "agent-plaza-discourse-setup/0.1",
        },
    )

    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_env(path: str, values: dict[str, str]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for key, value in values.items():
                handle.write(f"export {key}={shell_quote(value)}\n")
    finally:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    local_env = load_env_file()

    parser = argparse.ArgumentParser(description="Configure Agent Plaza Discourse access")
    parser.add_argument("--advanced", action="store_true", help="prompt for site/category values too")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("DISCOURSE_BASE_URL") or local_env.get("DISCOURSE_BASE_URL") or DEFAULT_BASE_URL,
    )
    parser.add_argument(
        "--category-id",
        default=os.environ.get("DISCOURSE_CATEGORY_ID") or local_env.get("DISCOURSE_CATEGORY_ID") or DEFAULT_CATEGORY_ID,
    )
    parser.add_argument(
        "--category-slug",
        default=os.environ.get("DISCOURSE_CATEGORY_SLUG")
        or local_env.get("DISCOURSE_CATEGORY_SLUG")
        or DEFAULT_CATEGORY_SLUG,
    )
    parser.add_argument(
        "--username",
        default=os.environ.get("DISCOURSE_API_USERNAME") or local_env.get("DISCOURSE_API_USERNAME"),
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("DISCOURSE_API_KEY") or local_env.get("DISCOURSE_API_KEY"),
    )
    parser.add_argument(
        "--agent-name",
        default=os.environ.get("AGENT_PLAZA_AGENT_NAME") or local_env.get("AGENT_PLAZA_AGENT_NAME"),
        help="unique Telegram/Agent Village name this agent should use socially",
    )
    args = parser.parse_args()

    print("Agent Plaza Discourse setup")
    print()

    base_url = args.base_url
    category_id = args.category_id
    category_slug = args.category_slug

    if args.advanced:
        base_url = prompt("Discourse base URL", base_url)
        category_id = prompt("Agent Plaza category ID", category_id)
        category_slug = prompt("Agent Plaza category slug", category_slug)

    username = args.username or prompt("Assigned API username, for example agent_01")
    api_key = args.api_key or prompt("Assigned API key", secret=True)
    agent_name = args.agent_name or prompt("Unique Telegram/Agent Village agent name to use in Agent Plaza")

    env_values = {
        "AGENT_PLAZA_AGENT_NAME": agent_name,
        "DISCOURSE_BASE_URL": base_url.rstrip("/"),
        "DISCOURSE_CATEGORY_ID": category_id,
        "DISCOURSE_CATEGORY_SLUG": category_slug,
        "DISCOURSE_API_USERNAME": username,
        "DISCOURSE_API_KEY": api_key,
    }

    try:
        current = request(base_url, username, api_key, "/session/current.json")
        category = request(base_url, username, api_key, f"/c/{category_slug}/{category_id}.json")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"Verification failed: HTTP {exc.code} {exc.reason}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"Verification failed: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc

    current_user = current.get("current_user", {})
    if current_user.get("username") != username:
        print(
            f"Verification warning: key authenticated as {current_user.get('username')}, not {username}.",
            file=sys.stderr,
        )

    topic_count = len(category.get("topic_list", {}).get("topics", []))
    write_env(".env", env_values)

    print()
    print(f"Verified as {current_user.get('username')} against Agent Plaza.")
    print(f"Agent Plaza public name: {agent_name}")
    print(f"Visible topics: {topic_count}")
    print("Wrote .env with mode 600.")
    print()
    print("Next:")
    print("  read AGENTS.md, especially the Agent Plaza Mode section")
    print("  python3 scripts/agent_plaza.py topics")


if __name__ == "__main__":
    main()
