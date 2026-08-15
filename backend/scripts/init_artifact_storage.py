"""Create the private Artifact bucket and least-privilege runtime accounts."""

from __future__ import annotations

import os
import time
from pathlib import Path

from minio import Minio
from minio.credentials.providers import StaticProvider
from minio.error import S3Error
from minio.minioadmin import MinioAdmin, MinioAdminException


def main() -> None:
    endpoint = os.environ["ARTIFACT_STORAGE_ENDPOINT"]
    root_user = _secret("MINIO_ROOT_USER")
    root_password = _secret("MINIO_ROOT_PASSWORD")
    app_user = _secret("ARTIFACT_STORAGE_ACCESS_KEY")
    app_password = _secret("ARTIFACT_STORAGE_SECRET_KEY")
    backup_user = _secret("ARTIFACT_BACKUP_ACCESS_KEY")
    backup_password = _secret("ARTIFACT_BACKUP_SECRET_KEY")
    bucket = os.environ["ARTIFACT_STORAGE_BUCKET"]
    client = Minio(endpoint, access_key=root_user, secret_key=root_password, secure=False)
    _wait_for_storage(client)
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)

    admin = MinioAdmin(
        endpoint=endpoint,
        credentials=StaticProvider(root_user, root_password),
        secure=False,
    )
    _ensure_policy(
        admin,
        "nora-artifact-rw",
        app_user,
        app_password,
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket}"],
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                },
            ],
        },
    )
    _ensure_policy(
        admin,
        "nora-artifact-backup-read",
        backup_user,
        backup_password,
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetBucketLocation", "s3:ListBucket"],
                    "Resource": [f"arn:aws:s3:::{bucket}"],
                },
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                },
            ],
        },
    )


def _ensure_policy(
    admin: MinioAdmin,
    policy_name: str,
    username: str,
    password: str,
    policy: dict[str, object],
) -> None:
    try:
        admin.policy_add(policy_name, policy=policy)
    except MinioAdminException as exc:
        if "already exists" not in str(exc).lower():
            raise
    try:
        admin.user_add(username, password)
    except MinioAdminException as exc:
        if "already exists" not in str(exc).lower():
            raise
    admin.policy_set(policy_name, user=username)


def _wait_for_storage(client: Minio) -> None:
    for _ in range(30):
        try:
            client.list_buckets()
            return
        except S3Error:
            time.sleep(1)
    raise RuntimeError("MinIO did not become ready")


def _secret(name: str) -> str:
    file_name = os.getenv(f"{name}_FILE")
    if file_name:
        return Path(file_name).read_text(encoding="utf-8").rstrip("\r\n")
    return os.environ[name]


if __name__ == "__main__":
    main()
