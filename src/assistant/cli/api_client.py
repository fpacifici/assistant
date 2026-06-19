"""Simple CLI client for the Assistant REST API."""

from __future__ import annotations

import argparse
import json
import sys

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
_NO_CONTENT = 204


def _print_response(response: httpx.Response) -> None:
    if response.status_code == _NO_CONTENT:
        print(f"Status: {response.status_code} No Content")  # noqa: T201
        return
    print(f"Status: {response.status_code}")  # noqa: T201
    try:
        print(json.dumps(response.json(), indent=2))  # noqa: T201
    except Exception:
        print(response.text)  # noqa: T201


def cmd_create_user(args: argparse.Namespace) -> None:
    response = httpx.post(
        f"{args.base_url}/user",
        json={
            "email": args.email,
            "firstname": args.firstname,
            "lastname": args.lastname,
        },
    )
    _print_response(response)


def cmd_get_user(args: argparse.Namespace) -> None:
    response = httpx.get(f"{args.base_url}/user/{args.uid}")
    _print_response(response)


def cmd_update_user(args: argparse.Namespace) -> None:
    body: dict[str, str] = {}
    if args.email:
        body["email"] = args.email
    if args.firstname:
        body["firstname"] = args.firstname
    if args.lastname:
        body["lastname"] = args.lastname
    response = httpx.patch(
        f"{args.base_url}/user/{args.uid}",
        json=body,
    )
    _print_response(response)


def cmd_create_notebook(args: argparse.Namespace) -> None:
    response = httpx.post(
        f"{args.base_url}/notebook",
        json={"name": args.name},
        headers={"X-User-Id": args.user_id},
    )
    _print_response(response)


def cmd_list_notebooks(args: argparse.Namespace) -> None:
    response = httpx.get(
        f"{args.base_url}/notebook",
        headers={"X-User-Id": args.user_id},
        params={"offset": args.offset, "limit": args.limit},
    )
    _print_response(response)


def cmd_get_notebook(args: argparse.Namespace) -> None:
    response = httpx.get(
        f"{args.base_url}/notebook/{args.notebook_id}",
    )
    _print_response(response)


def cmd_delete_notebook(args: argparse.Namespace) -> None:
    response = httpx.delete(
        f"{args.base_url}/notebook/{args.notebook_id}",
    )
    _print_response(response)


def cmd_create_note(args: argparse.Namespace) -> None:
    response = httpx.post(
        f"{args.base_url}/notebook/{args.notebook_id}/note",
        json={"title": args.title},
        headers={"X-User-Id": args.user_id},
    )
    _print_response(response)


def cmd_list_notes(args: argparse.Namespace) -> None:
    response = httpx.get(
        f"{args.base_url}/notebook/{args.notebook_id}/note",
        params={"offset": args.offset, "limit": args.limit},
    )
    _print_response(response)


def cmd_get_note(args: argparse.Namespace) -> None:
    response = httpx.get(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}",
    )
    _print_response(response)


def cmd_delete_note(args: argparse.Namespace) -> None:
    response = httpx.delete(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}",
    )
    _print_response(response)


def cmd_create_node(args: argparse.Namespace) -> None:
    body: dict[str, str] = {"payload": args.payload}
    if args.after_node_id:
        body["after_node_id"] = args.after_node_id
    if args.before_node_id:
        body["before_node_id"] = args.before_node_id
    response = httpx.post(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}/node",
        json=body,
        headers={"X-User-Id": args.user_id},
    )
    _print_response(response)


def cmd_update_node(args: argparse.Namespace) -> None:
    response = httpx.patch(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}/node/{args.node_id}",
        json={
            "type": "update",
            "payload": args.payload,
            "expected_version": args.expected_version,
        },
    )
    _print_response(response)


def cmd_merge_node(args: argparse.Namespace) -> None:
    response = httpx.patch(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}/node/{args.node_id}",
        json={
            "type": "merge",
            "source_node_id": args.source_node_id,
            "expected_version": args.expected_version,
            "source_expected_version": args.source_expected_version,
        },
    )
    _print_response(response)


def cmd_split_node(args: argparse.Namespace) -> None:
    response = httpx.post(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}/node/{args.node_id}/split",
        json={
            "offset": args.offset,
            "expected_version": args.expected_version,
        },
        headers={"X-User-Id": args.user_id},
    )
    _print_response(response)


def cmd_delete_node(args: argparse.Namespace) -> None:
    response = httpx.delete(
        f"{args.base_url}/notebook/{args.notebook_id}/note/{args.note_id}/node/{args.node_id}",
    )
    _print_response(response)


def _register_user_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser("create-user")
    p.add_argument("--email", required=True)
    p.add_argument("--firstname", required=True)
    p.add_argument("--lastname", required=True)
    p.set_defaults(func=cmd_create_user)

    p = subparsers.add_parser("get-user")
    p.add_argument("uid")
    p.set_defaults(func=cmd_get_user)

    p = subparsers.add_parser("update-user")
    p.add_argument("uid")
    p.add_argument("--email")
    p.add_argument("--firstname")
    p.add_argument("--lastname")
    p.set_defaults(func=cmd_update_user)


def _register_notebook_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser("create-notebook")
    p.add_argument("--name", required=True)
    p.add_argument("--user-id", required=True)
    p.set_defaults(func=cmd_create_notebook)

    p = subparsers.add_parser("list-notebooks")
    p.add_argument("--user-id", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list_notebooks)

    p = subparsers.add_parser("get-notebook")
    p.add_argument("notebook_id")
    p.set_defaults(func=cmd_get_notebook)

    p = subparsers.add_parser("delete-notebook")
    p.add_argument("notebook_id")
    p.set_defaults(func=cmd_delete_notebook)


def _register_note_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser("create-note")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--user-id", required=True)
    p.set_defaults(func=cmd_create_note)

    p = subparsers.add_parser("list-notes")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list_notes)

    p = subparsers.add_parser("get-note")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.set_defaults(func=cmd_get_note)

    p = subparsers.add_parser("delete-note")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.set_defaults(func=cmd_delete_note)


def _register_node_commands(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    p = subparsers.add_parser("create-node")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.add_argument("--payload", required=True)
    p.add_argument("--user-id", required=True)
    p.add_argument("--after-node-id")
    p.add_argument("--before-node-id")
    p.set_defaults(func=cmd_create_node)

    p = subparsers.add_parser("update-node")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.add_argument("--node-id", required=True)
    p.add_argument("--payload", required=True)
    p.add_argument("--expected-version", type=int, required=True)
    p.set_defaults(func=cmd_update_node)

    p = subparsers.add_parser("merge-node")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.add_argument("--node-id", required=True, help="Target node (survives)")
    p.add_argument("--source-node-id", required=True, help="Source node (absorbed)")
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--source-expected-version", type=int, required=True)
    p.set_defaults(func=cmd_merge_node)

    p = subparsers.add_parser("split-node")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.add_argument("--node-id", required=True)
    p.add_argument("--offset", type=int, required=True)
    p.add_argument("--expected-version", type=int, required=True)
    p.add_argument("--user-id", required=True)
    p.set_defaults(func=cmd_split_node)

    p = subparsers.add_parser("delete-node")
    p.add_argument("--notebook-id", required=True)
    p.add_argument("--note-id", required=True)
    p.add_argument("--node-id", required=True)
    p.set_defaults(func=cmd_delete_node)


def main() -> int:
    """Run the API client CLI."""
    parser = argparse.ArgumentParser(
        description="Assistant API client",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _register_user_commands(subparsers)
    _register_notebook_commands(subparsers)
    _register_note_commands(subparsers)
    _register_node_commands(subparsers)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
