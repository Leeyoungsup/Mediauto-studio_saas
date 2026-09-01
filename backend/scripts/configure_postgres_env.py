#!/usr/bin/env python3
"""Create or validate the local PostgreSQL deployment environment file."""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import stat
from pathlib import Path
from urllib.parse import quote


def _parse_env(path_env: Path) -> dict[str, str]:
    dict_values: dict[str, str] = {}
    if not path_env.is_file():
        return dict_values
    for str_line in path_env.read_text(encoding="utf-8").splitlines():
        str_line = str_line.strip()
        if not str_line or str_line.startswith("#") or "=" not in str_line:
            continue
        str_key, str_value = str_line.split("=", 1)
        dict_values[str_key.strip()] = str_value.strip()
    return dict_values


def _validate(dict_values: dict[str, str], path_env: Path) -> None:
    if dict_values.get("DATABASE_BACKEND", "").lower() != "postgresql":
        raise ValueError(f"DATABASE_BACKEND=postgresql is required in {path_env}")
    if not dict_values.get("POSTGRES_URI"):
        raise ValueError(f"POSTGRES_URI is required in {path_env}")
    str_deployment = dict_values.get("POSTGRES_DEPLOYMENT", "docker").lower()
    if str_deployment not in {"docker", "native", "external"}:
        raise ValueError("POSTGRES_DEPLOYMENT must be 'docker', 'native', or 'external'")
    if str_deployment in {"docker", "native"}:
        for str_key in ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_PORT"):
            if not dict_values.get(str_key):
                raise ValueError(f"{str_key} is required for Docker PostgreSQL")


def configure(path_env: Path, str_mode: str) -> tuple[dict[str, str], bool]:
    """Return validated values and whether a new owner-only file was created."""
    dict_existing = _parse_env(path_env)
    if dict_existing:
        _validate(dict_existing, path_env)
        return dict_existing, False

    if str_mode == "external":
        str_uri = os.environ.get("POSTGRES_URI", "").strip()
        if not str_uri:
            raise ValueError("POSTGRES_URI is required for external PostgreSQL")
        dict_values = {
            "POSTGRES_DEPLOYMENT": "external",
            "POSTGRES_URI": str_uri,
            "DATABASE_BACKEND": "postgresql",
        }
    else:
        str_database = os.environ.get("POSTGRES_DB", "medicus_studio").strip()
        str_user = os.environ.get("POSTGRES_USER", "mediauto").strip()
        str_password = os.environ.get("POSTGRES_PASSWORD", "").strip() or secrets.token_hex(24)
        str_port = os.environ.get("POSTGRES_PORT", "5432").strip()
        if not str_database or not str_user or not str_password or not str_port.isdigit():
            raise ValueError("Invalid Docker PostgreSQL database, user, password, or port")
        str_uri = (
            "postgresql+asyncpg://"
            f"{quote(str_user, safe='')}:{quote(str_password, safe='')}"
            f"@127.0.0.1:{str_port}/{quote(str_database, safe='')}"
        )
        dict_values = {
            "POSTGRES_DEPLOYMENT": str_mode,
            "POSTGRES_DB": str_database,
            "POSTGRES_USER": str_user,
            "POSTGRES_PASSWORD": str_password,
            "POSTGRES_PORT": str_port,
            "POSTGRES_URI": str_uri,
            "DATABASE_BACKEND": "postgresql",
        }

    path_env.parent.mkdir(parents=True, exist_ok=True)
    str_contents = "\n".join(f"{str_key}={str_value}" for str_key, str_value in dict_values.items()) + "\n"
    path_env.write_text(str_contents, encoding="utf-8")
    if os.name != "nt":
        path_env.chmod(stat.S_IRUSR | stat.S_IWUSR)
    _validate(dict_values, path_env)
    return dict_values, True


async def _check_connection(str_uri: str) -> None:
    import asyncpg

    str_asyncpg_uri = str_uri.replace("postgresql+asyncpg://", "postgresql://", 1)
    obj_connection = await asyncpg.connect(str_asyncpg_uri)
    try:
        await obj_connection.fetchval("SELECT 1")
    finally:
        await obj_connection.close()


def main() -> int:
    obj_parser = argparse.ArgumentParser(description=__doc__)
    obj_parser.add_argument("--env-file", required=True)
    obj_parser.add_argument("--mode", choices=("docker", "native", "external"), default="docker")
    obj_parser.add_argument("--check-connection", action="store_true")
    obj_args = obj_parser.parse_args()
    try:
        dict_values, bool_created = configure(Path(obj_args.env_file).resolve(), obj_args.mode)
        if obj_args.check_connection:
            asyncio.run(_check_connection(dict_values["POSTGRES_URI"]))
    except Exception as obj_error:
        print(f"[ERROR] PostgreSQL environment configuration failed: {obj_error}")
        return 1
    print(
        "[OK] PostgreSQL environment "
        + ("created with protected credentials." if bool_created else "validated.")
    )
    if obj_args.check_connection:
        print("[OK] PostgreSQL ping succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
