"""Validate the host, immutable images and root-owned Secret inputs for Beta."""

from __future__ import annotations

import argparse
import ipaddress
import re
import stat
from pathlib import Path
from urllib.parse import unquote, urlsplit

IMAGE_PATTERN = re.compile(r"[^\s@]+@sha256:[0-9a-f]{64}")
ENV_NAME_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*")
DNS_LABEL_PATTERN = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?")
SCRIPT_VALUE_NAMES = {
    "NORA_BACKUP_STAGE_DIR",
    "NORA_COMPOSE_PROJECT",
    "NORA_MINIO_DATA_DIR",
    "NORA_POSTGRES_ADMIN_USER",
    "NORA_POSTGRES_DATA_DIR",
    "NORA_POSTGRES_DB",
}
DIRECT_SECRET_NAMES = {
    "DATABASE_URL",
    "DATABASE_ADMIN_URL",
    "POSTGRES_PASSWORD",
    "POSTGRES_APP_PASSWORD",
    "AUTH_RATE_LIMIT_SECRET",
    "ARTIFACT_STORAGE_ACCESS_KEY",
    "ARTIFACT_STORAGE_SECRET_KEY",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "ARTIFACT_BACKUP_ACCESS_KEY",
    "ARTIFACT_BACKUP_SECRET_KEY",
}
FILE_GROUPS = {
    "NORA_DATABASE_URL_FILE": 10001,
    "NORA_DATABASE_ADMIN_URL_FILE": 10001,
    "NORA_POSTGRES_PASSWORD_FILE": 70,
    "NORA_POSTGRES_APP_PASSWORD_FILE": 10001,
    "NORA_AUTH_RATE_LIMIT_SECRET_FILE": 10001,
    "NORA_ARTIFACT_ACCESS_KEY_FILE": 10001,
    "NORA_ARTIFACT_SECRET_KEY_FILE": 10001,
    "NORA_MINIO_ROOT_USER_FILE": 10001,
    "NORA_MINIO_ROOT_PASSWORD_FILE": 10001,
    "NORA_ARTIFACT_BACKUP_ACCESS_KEY_FILE": 10001,
    "NORA_ARTIFACT_BACKUP_SECRET_KEY_FILE": 10001,
}
DATA_OWNERS = {
    "NORA_POSTGRES_DATA_DIR": 70,
    "NORA_MINIO_DATA_DIR": 10001,
    "NORA_BACKUP_STAGE_DIR": 10001,
}


def read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in raw_line:
            raise ValueError(f"invalid env line {line_number}")
        name, raw_value = raw_line.split("=", 1)
        name = name.strip()
        if ENV_NAME_PATTERN.fullmatch(name) is None:
            raise ValueError(f"invalid env name on line {line_number}")
        if name in values:
            raise ValueError(f"duplicate env name on line {line_number}")
        if name in {"NORA_PUBLIC_ORIGIN", "NORA_WEB_PORT"} and raw_value != raw_value.strip():
            raise ValueError(f"{name} must not contain surrounding whitespace")
        if name == "NORA_WEB_PORT" and re.fullmatch(r"[0-9]+", raw_value) is None:
            raise ValueError("NORA_WEB_PORT must contain only decimal digits")
        value = raw_value.strip()
        if value[:1] == value[-1:] and value.startswith(("'", '"')):
            value = value[1:-1]
        values[name] = value
    return values


def validate_environment(values: dict[str, str], *, check_host: bool) -> list[str]:
    errors: list[str] = []
    for name in DIRECT_SECRET_NAMES:
        if values.get(name):
            errors.append(f"{name} must not be stored in the environment file")
    for name in ("NORA_API_IMAGE", "NORA_WEB_IMAGE"):
        if not IMAGE_PATTERN.fullmatch(values.get(name, "")):
            errors.append(f"{name} must be an OCI image reference pinned by sha256 digest")
    for name in (
        "NORA_PROVIDER",
        "NORA_REGION",
        "NORA_BACKUP_DESTINATION_ID",
        "NORA_MONTHLY_BUDGET",
        "NORA_BUDGET_ALERT",
    ):
        if not values.get(name) or values[name].lower() in {"unset", "example", "unknown"}:
            errors.append(f"{name} must record the real Beta environment before promotion")
    origin_error = validate_public_origin(values.get("NORA_PUBLIC_ORIGIN", ""))
    if origin_error is not None:
        errors.append(origin_error)
    port_error = validate_web_port(values.get("NORA_WEB_PORT", ""))
    if port_error is not None:
        errors.append(port_error)
    paths = {
        name: Path(values.get(name, ""))
        for name in (*FILE_GROUPS, *DATA_OWNERS, "NORA_JWT_KEY_RING_DIR")
    }
    if any(not path.is_absolute() for path in paths.values()):
        errors.append("all Secret and data paths must be absolute")
    data_paths = [str(paths[name]) for name in DATA_OWNERS]
    if len(set(data_paths)) != len(data_paths):
        errors.append("PostgreSQL, MinIO and backup staging paths must be distinct")
    secret_paths = [str(paths[name]) for name in FILE_GROUPS]
    if len(set(secret_paths)) != len(secret_paths):
        errors.append(
            "each runtime, management and backup identity must use a distinct Secret file"
        )
    if not check_host:
        return errors
    for name, expected_group in FILE_GROUPS.items():
        errors.extend(_validate_secret_file(name, paths[name], expected_group))
    errors.extend(_validate_key_ring(paths["NORA_JWT_KEY_RING_DIR"]))
    for name, expected_owner in DATA_OWNERS.items():
        errors.extend(_validate_data_directory(name, paths[name], expected_owner))
    errors.extend(_validate_database_identities(values, paths))
    return errors


def validate_public_origin(value: str) -> str | None:
    if value != value.strip():
        return "NORA_PUBLIC_ORIGIN must not contain surrounding whitespace"
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return "NORA_PUBLIC_ORIGIN must be a valid HTTPS origin"
    if parsed.scheme != "https" or not hostname:
        return "NORA_PUBLIC_ORIGIN must be a valid HTTPS origin"
    if parsed.username is not None or parsed.password is not None:
        return "NORA_PUBLIC_ORIGIN must not contain user information"
    if parsed.path not in {"", "/"}:
        return "NORA_PUBLIC_ORIGIN must not contain a path"
    if parsed.query:
        return "NORA_PUBLIC_ORIGIN must not contain a query"
    if parsed.fragment:
        return "NORA_PUBLIC_ORIGIN must not contain a fragment"
    normalized_host = hostname.rstrip(".").lower()
    try:
        ascii_host = normalized_host.encode("idna").decode("ascii")
    except UnicodeError:
        return "NORA_PUBLIC_ORIGIN must use a valid DNS hostname"
    labels = ascii_host.split(".")
    if (
        len(ascii_host) > 253
        or any(not 1 <= len(label) <= 63 for label in labels)
        or any(DNS_LABEL_PATTERN.fullmatch(label) is None for label in labels)
    ):
        return "NORA_PUBLIC_ORIGIN must use a valid DNS hostname"
    if ascii_host == "localhost":
        return "NORA_PUBLIC_ORIGIN must not use localhost"
    if ascii_host == "example.com" or ascii_host.endswith(".example.com"):
        return "NORA_PUBLIC_ORIGIN must not use example.com"
    try:
        ipaddress.ip_address(ascii_host)
    except ValueError:
        pass
    else:
        return "NORA_PUBLIC_ORIGIN must use a DNS hostname, not an IP address"
    return None


def validate_web_port(value: str) -> str | None:
    if re.fullmatch(r"[0-9]+", value) is None:
        return "NORA_WEB_PORT must be a decimal integer from 1024 to 65535"
    port = int(value)
    if not 1024 <= port <= 65535:
        return "NORA_WEB_PORT must be a decimal integer from 1024 to 65535"
    return None


def _validate_secret_file(name: str, path: Path, expected_group: int) -> list[str]:
    try:
        details = path.lstat()
    except OSError:
        return [f"{name} must identify an existing Secret file"]
    errors: list[str] = []
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISREG(details.st_mode):
        errors.append(f"{name} must be a regular non-symlink file")
    if details.st_uid != 0 or details.st_gid != expected_group:
        errors.append(f"{name} must be owned by root:{expected_group}")
    if stat.S_IMODE(details.st_mode) != 0o440:
        errors.append(f"{name} must have mode 0440")
    if details.st_size < 1 or details.st_size > 16 * 1024:
        errors.append(f"{name} must contain 1-16384 bytes")
    return errors


def _validate_key_ring(path: Path) -> list[str]:
    try:
        details = path.lstat()
    except OSError:
        return ["NORA_JWT_KEY_RING_DIR must identify an existing directory"]
    errors: list[str] = []
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        return ["NORA_JWT_KEY_RING_DIR must be a regular non-symlink directory"]
    if details.st_uid != 0 or details.st_gid != 10001 or stat.S_IMODE(details.st_mode) != 0o750:
        errors.append("NORA_JWT_KEY_RING_DIR must be root:10001 with mode 0750")
    entries = list(path.iterdir())
    if not entries:
        errors.append("NORA_JWT_KEY_RING_DIR must contain at least one key")
    for entry in entries:
        errors.extend(_validate_secret_file(f"JWT key {entry.name}", entry, 10001))
    return errors


def _validate_data_directory(name: str, path: Path, expected_owner: int) -> list[str]:
    try:
        details = path.lstat()
    except OSError:
        return [f"{name} must identify an existing data directory"]
    errors: list[str] = []
    if stat.S_ISLNK(details.st_mode) or not stat.S_ISDIR(details.st_mode):
        errors.append(f"{name} must be a regular non-symlink directory")
    if details.st_uid != expected_owner or details.st_gid != expected_owner:
        errors.append(f"{name} must be owned by {expected_owner}:{expected_owner}")
    if stat.S_IMODE(details.st_mode) & 0o007:
        errors.append(f"{name} must not be accessible by others")
    return errors


def _validate_database_identities(values: dict[str, str], paths: dict[str, Path]) -> list[str]:
    try:
        runtime_url = _read_secret_text(paths["NORA_DATABASE_URL_FILE"])
        admin_url = _read_secret_text(paths["NORA_DATABASE_ADMIN_URL_FILE"])
        admin_password = _read_secret_text(paths["NORA_POSTGRES_PASSWORD_FILE"])
        app_password = _read_secret_text(paths["NORA_POSTGRES_APP_PASSWORD_FILE"])
    except (OSError, UnicodeError):
        return ["PostgreSQL identity Secret files must be readable UTF-8 text"]

    runtime = urlsplit(runtime_url)
    admin = urlsplit(admin_url)
    app_user = values.get("NORA_POSTGRES_APP_USER", "nora_app")
    admin_user = values.get("NORA_POSTGRES_ADMIN_USER", "nora_admin")
    errors: list[str] = []
    if app_user == admin_user:
        errors.append("PostgreSQL runtime and admin users must be distinct")
    if runtime.scheme != "postgresql+asyncpg" or unquote(runtime.username or "") != app_user:
        errors.append("NORA_DATABASE_URL_FILE must use the configured PostgreSQL runtime user")
    if admin.scheme != "postgresql+asyncpg" or unquote(admin.username or "") != admin_user:
        errors.append("NORA_DATABASE_ADMIN_URL_FILE must use the configured PostgreSQL admin user")
    if unquote(runtime.password or "") != app_password:
        errors.append("PostgreSQL runtime URL and application password Secret must agree")
    if unquote(admin.password or "") != admin_password:
        errors.append("PostgreSQL admin URL and initialization password Secret must agree")
    if runtime_url == admin_url:
        errors.append("PostgreSQL runtime and admin URLs must be distinct")
    return errors


def _read_secret_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").rstrip("\r\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--config-only", action="store_true")
    parser.add_argument("--get", choices=sorted(SCRIPT_VALUE_NAMES))
    arguments = parser.parse_args()
    values = read_environment(arguments.env_file)
    errors = validate_environment(values, check_host=not arguments.config_only)
    if errors:
        for error in errors:
            print(f"preflight_error={error}")
        raise SystemExit(2)
    if arguments.get is not None:
        try:
            print(values[arguments.get])
        except KeyError as exc:
            raise SystemExit(f"preflight_error={arguments.get} is required") from exc
    else:
        print("production_preflight=passed")


if __name__ == "__main__":
    main()
