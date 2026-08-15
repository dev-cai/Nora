"""Non-HTTP operator entry point for the single Beta owner lifecycle."""

import argparse
import asyncio
import json
import stat
from pathlib import Path
from typing import Sequence

from app.application.identity import IdentityManagementService
from app.domain.base.exceptions import NoraError
from app.infrastructure.auth import Argon2PasswordHasher
from app.infrastructure.config import Settings
from app.infrastructure.database import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyIdentityManagementRepository,
    create_database_engine,
    create_session_factory,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nora-identity")
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap = commands.add_parser("bootstrap-owner")
    bootstrap.add_argument("--request-id", required=True)
    bootstrap.add_argument("--username-file", type=Path, required=True)
    bootstrap.add_argument("--email-file", type=Path, required=True)
    bootstrap.add_argument("--password-file", type=Path, required=True)
    recover = commands.add_parser("recover-owner")
    recover.add_argument("--request-id", required=True)
    recover.add_argument("--password-file", type=Path, required=True)
    return parser


def _read_secret(path: Path) -> str:
    mode = path.stat().st_mode
    if not stat.S_ISREG(mode) or mode & 0o077:
        raise ValueError("credential files must be regular and owner-readable only")
    value = path.read_text(encoding="utf-8").rstrip("\r\n")
    if not value:
        raise ValueError("credential files must not be empty")
    return value


async def _run(arguments: argparse.Namespace) -> dict[str, object]:
    settings = Settings()
    if settings.database_url is None:
        raise ValueError("DATABASE_URL is required")
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with factory() as session:
            service = IdentityManagementService(
                SqlAlchemyIdentityManagementRepository(
                    session, SqlAlchemyAuditEventRepository(session)
                ),
                Argon2PasswordHasher(),
            )
            if arguments.command == "bootstrap-owner":
                result = await service.bootstrap_owner(
                    arguments.request_id,
                    _read_secret(arguments.username_file),
                    _read_secret(arguments.email_file),
                    _read_secret(arguments.password_file),
                )
            else:
                result = await service.recover_credentials(
                    arguments.request_id, _read_secret(arguments.password_file)
                )
        return {
            "status": result.status.value,
            "request_id": arguments.request_id,
            "user_id": str(result.user_id) if result.user_id is not None else None,
            "session_version": result.session_version,
        }
    finally:
        await engine.dispose()


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        output = asyncio.run(_run(arguments))
    except (NoraError, OSError, ValueError):
        print(json.dumps({"status": "failed", "request_id": arguments.request_id}))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
