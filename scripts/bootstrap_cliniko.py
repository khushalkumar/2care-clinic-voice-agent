#!/usr/bin/env python3
import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from typing import NoReturn

from app.infrastructure.pms.cliniko import ClinikoConfig, ClinikoTransport
from app.infrastructure.pms.cliniko_bootstrap import inspect_trial


def parse_args(arguments: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect the designated Cliniko trial setup.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect the trial setup without changing records (the default).",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Reserved for the mutation phase after the live write contract is verified.",
    )
    return parser.parse_args(arguments)


def _required_setting(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


async def main() -> None:
    args = parse_args()
    if args.apply:
        _apply_not_available()

    client = ClinikoTransport(
        ClinikoConfig(
            api_key=_required_setting("CLINIKO_API_KEY"),
            shard=_required_setting("CLINIKO_SHARD"),
            user_agent=_required_setting("CLINIKO_USER_AGENT"),
        )
    )
    try:
        report = await inspect_trial(client)
    finally:
        await client.aclose()
    print(json.dumps(report, indent=2, sort_keys=True))


def _apply_not_available() -> NoReturn:
    raise SystemExit(
        "--apply is unavailable until the live Cliniko appointment-write contract is verified. "
        "No records were changed."
    )


if __name__ == "__main__":
    asyncio.run(main())
