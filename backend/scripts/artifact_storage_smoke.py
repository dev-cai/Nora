"""Verify the runtime Artifact identity with a temporary private object."""

from __future__ import annotations

import hashlib
import io
import os
import secrets
from pathlib import Path

from minio import Minio


def _secret(name: str) -> str:
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        return Path(file_name).read_text(encoding="utf-8").rstrip("\r\n")
    return os.environ[name]


def main() -> None:
    payload = secrets.token_bytes(64)
    key = f"release-smoke/{secrets.token_hex(16)}"
    bucket = os.environ["ARTIFACT_STORAGE_BUCKET"]
    client = Minio(
        os.environ["ARTIFACT_STORAGE_ENDPOINT"],
        access_key=_secret("ARTIFACT_STORAGE_ACCESS_KEY"),
        secret_key=_secret("ARTIFACT_STORAGE_SECRET_KEY"),
        secure=os.getenv("ARTIFACT_STORAGE_SECURE", "false").lower() == "true",
    )
    try:
        client.put_object(bucket, key, io.BytesIO(payload), length=len(payload))
        response = client.get_object(bucket, key)
        try:
            restored = response.read()
        finally:
            response.close()
            response.release_conn()
        if hashlib.sha256(restored).digest() != hashlib.sha256(payload).digest():
            raise RuntimeError("Artifact smoke object did not round-trip")
    finally:
        client.remove_object(bucket, key)
    print("artifact_storage_smoke=passed")


if __name__ == "__main__":
    main()
