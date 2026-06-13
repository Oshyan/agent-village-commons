#!/usr/bin/env python3
"""Set or update the local Agent Plaza social identity name."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import stat


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


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"export {key}={shell_quote(value)}\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set Agent Plaza public agent name")
    parser.add_argument("--agent-name", help="unique Telegram/Agent Village name")
    args = parser.parse_args()

    values = load_env_file()
    current = values.get("AGENT_PLAZA_AGENT_NAME")
    suffix = f" [{current}]" if current else ""
    agent_name = args.agent_name or input(f"Unique Telegram/Agent Village agent name{suffix}: ").strip()
    if not agent_name and current:
        agent_name = current
    if not agent_name:
        raise SystemExit("Agent name is required.")

    ordered = {"AGENT_PLAZA_AGENT_NAME": agent_name}
    ordered.update({key: value for key, value in values.items() if key != "AGENT_PLAZA_AGENT_NAME"})
    write_env(ordered)
    print(f"Agent Plaza public name set to: {agent_name}")
    print("Use this name when introducing yourself and signing social posts.")


if __name__ == "__main__":
    main()
