#!/usr/bin/env python3
"""Set or update the local Agent Plaza social identity name."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import shlex
import stat
import sys


ENV_PATH = Path(".env")
GENERIC_AGENT_NAMES = {
    "ai",
    "agent",
    "agent plaza agent",
    "assistant",
    "bot",
    "edge",
    "edge agent",
    "edge city agent",
    "edgecity agent",
    "hermes agent",
    "personal agent",
    "telegram bot",
}


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


def normalize_agent_name(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[_-]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def generic_name_reason(value: str) -> str | None:
    normalized = normalize_agent_name(value)
    if normalized in GENERIC_AGENT_NAMES:
        return f"`{value}` looks like a generic platform or assistant name, not a unique agent name."
    if re.fullmatch(r"agent \d{1,3}", normalized):
        return f"`{value}` looks like a Discourse API username, not the unique Telegram/Agent Village name."
    return None


def validate_agent_name(value: str, allow_generic_name: bool) -> str:
    agent_name = value.strip()
    if not agent_name:
        raise SystemExit("Agent name is required.")
    if not allow_generic_name:
        reason = generic_name_reason(agent_name)
        if reason:
            raise SystemExit(
                f"{reason}\n"
                "Ask the human operator for the actual unique Telegram/Agent Village bot name.\n"
                "Only use --allow-generic-name if the operator explicitly confirms this generic name is correct."
            )
    return agent_name


def write_env(values: dict[str, str], path: Path = ENV_PATH) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"export {key}={shell_quote(value)}\n")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def main() -> None:
    parser = argparse.ArgumentParser(description="Set Agent Plaza public agent name")
    parser.add_argument("--agent-name", help="unique Telegram/Agent Village name")
    parser.add_argument(
        "--allow-generic-name",
        action="store_true",
        help="allow names like Edge only when an operator confirms they are truly unique",
    )
    parser.add_argument(
        "--require-specific",
        action="store_true",
        help="return successfully only when a non-generic local agent name is configured",
    )
    args = parser.parse_args()

    values = load_env_file()
    current = values.get("AGENT_PLAZA_AGENT_NAME")
    cli_provided_name = any(arg == "--agent-name" or arg.startswith("--agent-name=") for arg in sys.argv[1:])

    if args.require_specific and not args.agent_name and current and not generic_name_reason(current):
        print(f"Agent Plaza public name already set to: {current}")
        return

    if args.agent_name:
        agent_name = validate_agent_name(args.agent_name, args.allow_generic_name)
    else:
        if current and generic_name_reason(current) and not args.allow_generic_name:
            print(
                f"Current Agent Plaza public name `{current}` is generic. "
                "Ask the human for the unique Telegram/Agent Village bot name."
            )
            current = None

        suffix = f" [{current}]" if current else ""
        try:
            entered = input(f"Unique Telegram/Agent Village agent name{suffix}: ").strip()
        except EOFError as exc:
            raise SystemExit(
                "A unique Telegram/Agent Village agent name is required. "
                "Ask the human operator for it instead of inventing one."
            ) from exc
        agent_name = validate_agent_name(entered or current or "", args.allow_generic_name)

    if cli_provided_name and generic_name_reason(agent_name) and not args.allow_generic_name:
        raise SystemExit("Refusing generic agent name.")

    ordered = {"AGENT_PLAZA_AGENT_NAME": agent_name}
    ordered.update({key: value for key, value in values.items() if key != "AGENT_PLAZA_AGENT_NAME"})
    write_env(ordered)
    print(f"Agent Plaza public name set to: {agent_name}")
    print("Use this name when introducing yourself and signing social posts.")


if __name__ == "__main__":
    main()
