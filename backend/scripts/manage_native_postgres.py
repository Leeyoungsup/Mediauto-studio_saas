#!/usr/bin/env python3
"""Initialize and manage a user-owned native PostgreSQL service on Linux."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import tempfile
import time
from pathlib import Path


RE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _run(list_command: list[str], *, dict_env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(list_command, check=True, text=True, env=dict_env)


def _validate_identifier(str_value: str, str_label: str) -> None:
    if not RE_IDENTIFIER.fullmatch(str_value):
        raise ValueError(f"Invalid PostgreSQL {str_label}: {str_value!r}")


def _write_managed_config(path_data: Path, int_port: int) -> None:
    path_main = path_data / "postgresql.conf"
    path_managed = path_data / "mediauto.conf"
    str_include = "include_if_exists = 'mediauto.conf'"
    str_main = path_main.read_text(encoding="utf-8")
    if str_include not in str_main:
        with path_main.open("a", encoding="utf-8") as obj_file:
            obj_file.write(f"\n# MeDIAuto managed settings\n{str_include}\n")
    path_managed.write_text(
        "# Managed by manage_native_postgres.py\n"
        "listen_addresses = '127.0.0.1'\n"
        f"port = {int_port}\n"
        "password_encryption = 'scram-sha-256'\n",
        encoding="utf-8",
    )


def _write_user_service(path_unit: Path, path_postgres: Path, path_pg_ctl: Path, path_data: Path) -> None:
    path_unit.parent.mkdir(parents=True, exist_ok=True)
    path_unit.write_text(
        "[Unit]\n"
        "Description=MeDIAuto Native PostgreSQL\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        f"ExecStart={path_postgres} -D {path_data}\n"
        f"ExecReload={path_pg_ctl} reload -D {path_data}\n"
        f"ExecStop={path_pg_ctl} stop -D {path_data} -m fast\n"
        "Restart=on-failure\n"
        "RestartSec=5\n"
        "TimeoutStopSec=120\n\n"
        "[Install]\n"
        "WantedBy=default.target\n",
        encoding="utf-8",
    )


def initialize(
    *, path_bin: Path, path_data: Path, path_unit: Path, int_port: int,
    str_user: str, str_password: str, str_database: str,
) -> None:
    _validate_identifier(str_user, "user")
    _validate_identifier(str_database, "database")
    if not 1 <= int_port <= 65535:
        raise ValueError("PostgreSQL port must be between 1 and 65535")
    if not str_password:
        raise ValueError("PostgreSQL password is required")

    path_initdb = path_bin / "initdb"
    path_postgres = path_bin / "postgres"
    path_pg_ctl = path_bin / "pg_ctl"
    path_pg_isready = path_bin / "pg_isready"
    path_createdb = path_bin / "createdb"
    for path_binary in (path_initdb, path_postgres, path_pg_ctl, path_pg_isready, path_createdb):
        if not path_binary.is_file():
            raise FileNotFoundError(f"PostgreSQL binary not found: {path_binary}")

    path_data.parent.mkdir(parents=True, exist_ok=True)
    if not (path_data / "PG_VERSION").is_file():
        path_data.mkdir(mode=0o700, exist_ok=True)
        int_fd, str_password_file = tempfile.mkstemp(prefix=".pg-password-", dir=path_data.parent)
        path_password_file = Path(str_password_file)
        try:
            os.fchmod(int_fd, stat.S_IRUSR | stat.S_IWUSR)
            with os.fdopen(int_fd, "w", encoding="utf-8") as obj_file:
                obj_file.write(str_password)
            _run([
                str(path_initdb), "-D", str(path_data), "--username", str_user,
                "--pwfile", str(path_password_file), "--auth-local=trust",
                "--auth-host=scram-sha-256", "--encoding=UTF8",
            ])
        finally:
            path_password_file.unlink(missing_ok=True)

    _write_managed_config(path_data, int_port)
    _write_user_service(path_unit, path_postgres, path_pg_ctl, path_data)
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "enable", path_unit.stem])
    _run(["systemctl", "--user", "restart", path_unit.stem])

    for _ in range(60):
        obj_ready = subprocess.run(
            [str(path_pg_isready), "-h", "127.0.0.1", "-p", str(int_port), "-U", str_user],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if obj_ready.returncode == 0:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Native PostgreSQL did not become ready within 60 seconds")

    dict_env = dict(os.environ)
    dict_env["PGPASSWORD"] = str_password
    obj_exists = subprocess.run(
        [
            str(path_bin / "psql"), "-h", "127.0.0.1", "-p", str(int_port),
            "-U", str_user, "-d", "postgres", "-Atc",
            f"SELECT 1 FROM pg_database WHERE datname = '{str_database}'",
        ],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        env=dict_env,
    )
    if obj_exists.stdout.strip() != "1":
        _run([
            str(path_createdb), "-h", "127.0.0.1", "-p", str(int_port),
            "-U", str_user, str_database,
        ], dict_env=dict_env)


def main() -> int:
    obj_parser = argparse.ArgumentParser(description=__doc__)
    obj_parser.add_argument("--bin-dir", required=True)
    obj_parser.add_argument("--data-dir", required=True)
    obj_parser.add_argument("--unit-file", required=True)
    obj_parser.add_argument("--port", required=True, type=int)
    obj_parser.add_argument("--user", required=True)
    obj_parser.add_argument("--password", default=os.environ.get("POSTGRES_PASSWORD", ""))
    obj_parser.add_argument("--database", required=True)
    obj_args = obj_parser.parse_args()
    try:
        initialize(
            path_bin=Path(obj_args.bin_dir).resolve(),
            path_data=Path(obj_args.data_dir).resolve(),
            path_unit=Path(obj_args.unit_file).resolve(),
            int_port=obj_args.port,
            str_user=obj_args.user,
            str_password=obj_args.password,
            str_database=obj_args.database,
        )
    except Exception as obj_error:
        print(f"[ERROR] Native PostgreSQL setup failed: {obj_error}")
        return 1
    print(f"[OK] Native PostgreSQL is ready on 127.0.0.1:{obj_args.port}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
