import asyncio
import os
import shutil
import socket
import subprocess
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def postgres_server(tmp_path_factory: pytest.TempPathFactory) -> Iterator[tuple[Path, int]]:
    configured_pg_bin = os.environ.get("PG_BIN")
    if configured_pg_bin:
        pg_bin = Path(configured_pg_bin)
    elif shutil.which("pg_config"):
        pg_bin = Path(
            subprocess.run(
                ["pg_config", "--bindir"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
    else:
        pg_bin = Path("/opt/homebrew/opt/postgresql@16/bin")
    required = ("initdb", "pg_ctl", "createdb", "dropdb")
    missing = [name for name in required if not (pg_bin / name).exists()]
    if missing:
        pytest.fail(f"PostgreSQL test binaries missing: {', '.join(missing)}")

    data_dir = tmp_path_factory.mktemp("postgres") / "data"
    log_file = data_dir.parent / "postgres.log"
    port = _free_port()
    subprocess.run(
        [str(pg_bin / "initdb"), "-A", "trust", "--no-locale", "-E", "UTF8", str(data_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            str(pg_bin / "pg_ctl"),
            "-D",
            str(data_dir),
            "-l",
            str(log_file),
            "-o",
            f"-h 127.0.0.1 -p {port}",
            "start",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        yield pg_bin, port
    finally:
        subprocess.run(
            [str(pg_bin / "pg_ctl"), "-D", str(data_dir), "stop", "-m", "fast"],
            check=True,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture
def database_url(postgres_server: tuple[Path, int]) -> Iterator[str]:
    pg_bin, port = postgres_server
    database = f"voice_agent_test_{uuid4().hex}"
    common = ["-h", "127.0.0.1", "-p", str(port), "-U", os.environ.get("USER", "postgres")]
    subprocess.run([str(pg_bin / "createdb"), *common, database], check=True, capture_output=True)
    try:
        yield f"postgresql+asyncpg://{common[-1]}@127.0.0.1:{port}/{database}"
    finally:
        subprocess.run(
            [str(pg_bin / "dropdb"), *common, "--force", database],
            check=True,
            capture_output=True,
        )


def _upgrade(database_url: str) -> None:
    config = Config(Path(__file__).parents[2] / "alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


@pytest.fixture
async def migrated_database_url(database_url: str) -> str:
    await asyncio.to_thread(_upgrade, database_url)
    return database_url
