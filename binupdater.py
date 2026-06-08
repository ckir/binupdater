#!/usr/bin/env python3
"""binupdater — keep GitHub-released binaries up to date."""

import argparse
import sys

import cli


def main():
    parser = argparse.ArgumentParser(
        prog="binupdater",
        description="Keep GitHub-released binaries up to date.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    p_add = sub.add_parser("add", help="Add a new tool to track")
    p_add.add_argument("url", help="GitHub repository URL")
    p_add.add_argument("--name", help="Override the tool name (defaults to repo name)")
    p_add.add_argument(
        "--force",
        action="store_true",
        help="Re-add and overwrite existing configuration",
    )

    p_update = sub.add_parser("update", help="Update tracked tools")
    p_update.add_argument(
        "tools", nargs="*", metavar="TOOL", help="Tools to update (default: all)"
    )
    p_update.add_argument(
        "--check",
        action="store_true",
        help="Report available updates without installing",
    )

    sub.add_parser("list", help="List tracked tools and their versions")

    p_remove = sub.add_parser("remove", help="Stop tracking a tool")
    p_remove.add_argument("tool", help="Tool name")

    args = parser.parse_args()
    try:
        cmd_func = {
            "add": cli.cmd_add,
            "update": cli.cmd_update,
            "list": cli.cmd_list,
            "remove": cli.cmd_remove,
        }[args.command]
        cmd_func(args)
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)


if __name__ == "__main__":
    main()
