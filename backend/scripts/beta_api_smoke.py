"""Verify production API readiness and authentication boundaries without credentials."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000"


def _request(path: str, *, method: str = "GET", payload: dict[str, str] | None = None) -> int:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> None:
    for path, expected in {"/live": 200, "/ready": 200, "/auth/me": 401}.items():
        if _request(path) != expected:
            raise RuntimeError(f"Unexpected Beta API status for {path}")
    if (
        _request(
            "/auth/register",
            method="POST",
            payload={
                "username": "release-smoke",
                "email": "release-smoke@example.invalid",
                "password": "not-created-password",
            },
        )
        != 404
    ):
        raise RuntimeError("Production registration is not hidden")
    if (
        _request(
            "/auth/login",
            method="POST",
            payload={"username": "release-smoke", "password": "invalid-password"},
        )
        != 401
    ):
        raise RuntimeError("Invalid login did not preserve the authentication boundary")
    print("beta_api_smoke=passed")


if __name__ == "__main__":
    main()
