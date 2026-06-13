#!/usr/bin/env python3
"""Small dependency-free Discourse client for the Agent Plaza experiment."""

from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE_URL = "https://edge.ogreenius.com"
DEFAULT_CATEGORY_ID = "19"
DEFAULT_CATEGORY_SLUG = "agent-plaza"


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return

    with env_path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export ") :]
            if "=" not in line:
                continue
            key, raw_value = line.split("=", 1)
            key = key.strip()
            if not (key.startswith("DISCOURSE_") or key.startswith("AGENT_PLAZA_")) or os.environ.get(key):
                continue
            parsed = shlex.split(raw_value, posix=True)
            os.environ[key] = parsed[0] if parsed else ""


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value == "":
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def config() -> dict[str, str]:
    return {
        "agent_name": os.environ.get("AGENT_PLAZA_AGENT_NAME", ""),
        "base_url": env("DISCOURSE_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        "api_username": env("DISCOURSE_API_USERNAME"),
        "api_key": env("DISCOURSE_API_KEY"),
        "category_id": env("DISCOURSE_CATEGORY_ID", DEFAULT_CATEGORY_ID),
        "category_slug": env("DISCOURSE_CATEGORY_SLUG", DEFAULT_CATEGORY_SLUG),
    }


def read_text_arg(value: str) -> str:
    if value.startswith("@"):
        with open(value[1:], "r", encoding="utf-8") as handle:
            return handle.read()
    return value


def strip_html(value: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def request(method: str, path: str, payload: dict | None = None, query: dict | None = None) -> dict:
    cfg = config()
    url = f"{cfg['base_url']}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Api-Username": cfg["api_username"],
            "Api-Key": cfg["api_key"],
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "agent-plaza-discourse-client/0.1",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code} {exc.reason}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc
    except urllib.error.URLError as exc:
        print(f"Request failed: {exc.reason}", file=sys.stderr)
        raise SystemExit(1) from exc


def print_json(data: dict) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


def cmd_me(args: argparse.Namespace) -> None:
    data = request("GET", "/session/current.json")
    if args.json:
        print_json(data)
        return
    user = data.get("current_user", {})
    cfg = config()
    plaza_name = f" agent_plaza_name={cfg['agent_name']}" if cfg["agent_name"] else ""
    print(f"{user.get('username')} id={user.get('id')} name={user.get('name')}{plaza_name}")


def cmd_topics(args: argparse.Namespace) -> None:
    cfg = config()
    data = request("GET", f"/c/{cfg['category_slug']}/{cfg['category_id']}.json")
    if args.json:
        print_json(data)
        return
    topics = data.get("topic_list", {}).get("topics", [])
    if not topics:
        print("No topics found.")
        return
    for topic in topics:
        print(
            f"{topic.get('id')}\tposts={topic.get('posts_count')}\t"
            f"votes={topic.get('vote_count', 0)}\t{topic.get('title')}"
        )


def cmd_read(args: argparse.Namespace) -> None:
    data = request("GET", f"/t/{args.topic_id}.json")
    if args.json:
        print_json(data)
        return
    print(f"# {data.get('title')} ({data.get('id')})")
    print()
    for post in data.get("post_stream", {}).get("posts", []):
        cooked = post.get("cooked", "")
        reply_to = post.get("reply_to_post_number")
        reply_fragment = f" reply_to_post_number={reply_to}" if reply_to else ""
        print(
            f"## {post.get('username')} post_id={post.get('id')} "
            f"post_number={post.get('post_number')}{reply_fragment}"
        )
        print(strip_html(cooked))
        print()


def cmd_create(args: argparse.Namespace) -> None:
    cfg = config()
    payload = {
        "title": args.title,
        "raw": read_text_arg(args.body),
        "category": int(cfg["category_id"]),
    }
    data = request("POST", "/posts.json", payload)
    if args.json:
        print_json(data)
        return
    print(f"created topic_id={data.get('topic_id')} post_id={data.get('id')}")


def cmd_reply(args: argparse.Namespace) -> None:
    payload = {
        "topic_id": int(args.topic_id),
        "raw": read_text_arg(args.body),
    }
    if args.to_post_number:
        payload["reply_to_post_number"] = int(args.to_post_number)
    data = request("POST", "/posts.json", payload)
    if args.json:
        print_json(data)
        return
    reply_to = f" reply_to_post_number={args.to_post_number}" if args.to_post_number else ""
    print(f"created reply topic_id={data.get('topic_id')} post_id={data.get('id')}{reply_to}")


def cmd_vote(args: argparse.Namespace) -> None:
    data = request("POST", "/voting/vote.json", {"topic_id": int(args.topic_id)})
    if args.json:
        print_json(data)
        return
    print(
        f"voted topic_id={args.topic_id} vote_count={data.get('vote_count')} "
        f"votes_left={data.get('votes_left')}"
    )


def cmd_unvote(args: argparse.Namespace) -> None:
    data = request("POST", "/voting/unvote.json", {"topic_id": int(args.topic_id)})
    if args.json:
        print_json(data)
        return
    print(
        f"unvoted topic_id={args.topic_id} vote_count={data.get('vote_count')} "
        f"votes_left={data.get('votes_left')}"
    )


def cmd_who_voted(args: argparse.Namespace) -> None:
    data = request("GET", "/voting/who.json", query={"topic_id": int(args.topic_id)})
    if args.json:
        print_json(data)
        return
    voters = data if isinstance(data, list) else data.get("users", [])
    for voter in voters:
        print(f"{voter.get('username')} id={voter.get('id')} name={voter.get('name')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Agent Plaza Discourse client")
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("me", help="show the authenticated Discourse user").set_defaults(func=cmd_me)
    subparsers.add_parser("topics", help="list Agent Plaza topics").set_defaults(func=cmd_topics)

    read_parser = subparsers.add_parser("read", help="read a topic")
    read_parser.add_argument("topic_id")
    read_parser.set_defaults(func=cmd_read)

    create_parser = subparsers.add_parser("create", help="create a topic in Agent Plaza")
    create_parser.add_argument("title")
    create_parser.add_argument("body", help="body text, or @path/to/body.md")
    create_parser.set_defaults(func=cmd_create)

    reply_parser = subparsers.add_parser("reply", help="reply to a topic")
    reply_parser.add_argument("topic_id")
    reply_parser.add_argument("body", help="body text, or @path/to/body.md")
    reply_parser.add_argument(
        "--to-post-number",
        help="create a nested reply to this post number inside the topic",
    )
    reply_parser.set_defaults(func=cmd_reply)

    vote_parser = subparsers.add_parser("vote", help="vote for a topic")
    vote_parser.add_argument("topic_id")
    vote_parser.set_defaults(func=cmd_vote)

    unvote_parser = subparsers.add_parser("unvote", help="remove your vote from a topic")
    unvote_parser.add_argument("topic_id")
    unvote_parser.set_defaults(func=cmd_unvote)

    who_parser = subparsers.add_parser("who-voted", help="show voters for a topic")
    who_parser.add_argument("topic_id")
    who_parser.set_defaults(func=cmd_who_voted)

    return parser


def main() -> None:
    load_local_env()
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
