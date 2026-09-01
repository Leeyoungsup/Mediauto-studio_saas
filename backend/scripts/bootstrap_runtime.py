#!/usr/bin/env python3
"""Prepare and validate a fresh MeDIAuto Studio checkout.

This script does not contain model binaries. It can install model files from an
operator-provided directory/ZIP/TAR bundle and creates the initial administrator
on an empty DB. The deployment defaults can be overridden with environment
variables.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path


PATH_BACKEND = Path(__file__).resolve().parent.parent
PATH_MODEL_MANIFEST = PATH_BACKEND / "model_manifest.json"
LIST_RUNTIME_DIRS = (
    "uploads",
    "tiles",
    "ai_results",
    "annotations",
    "cell_annotation",
    "dicom_cache",
    "model",
)
STR_PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$")
DICT_DEFAULT_BOOTSTRAP_ADMIN = {
    "MEDIAUTO_BOOTSTRAP_ADMIN_ID": "admin",
    "MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD": "urban12!@",
    "MEDIAUTO_BOOTSTRAP_ADMIN_NAME": "Administrator",
    "MEDIAUTO_BOOTSTRAP_ADMIN_DEPARTMENT": "",
}


def _log(str_level: str, str_message: str) -> None:
    print(f"[{str_level}] {str_message}")


def _admin_bootstrap_values() -> tuple[bool, str, str, str, str]:
    tuple_keys = tuple(DICT_DEFAULT_BOOTSTRAP_ADMIN)
    bool_explicit = any(str_key in os.environ for str_key in tuple_keys)
    dict_values = {
        str_key: os.environ.get(str_key, str_default)
        for str_key, str_default in DICT_DEFAULT_BOOTSTRAP_ADMIN.items()
    }
    return (
        bool_explicit,
        dict_values["MEDIAUTO_BOOTSTRAP_ADMIN_ID"].strip().lower(),
        dict_values["MEDIAUTO_BOOTSTRAP_ADMIN_PASSWORD"],
        dict_values["MEDIAUTO_BOOTSTRAP_ADMIN_NAME"].strip(),
        dict_values["MEDIAUTO_BOOTSTRAP_ADMIN_DEPARTMENT"].strip(),
    )


def _load_model_manifest() -> list[dict]:
    with PATH_MODEL_MANIFEST.open("r", encoding="utf-8") as obj_file:
        dict_manifest = json.load(obj_file)
    return list(dict_manifest.get("models") or [])


def _prepare_runtime() -> object:
    if str(PATH_BACKEND) not in sys.path:
        sys.path.insert(0, str(PATH_BACKEND))

    # Importing settings creates backend/.secrets.json with mode 0600 when it
    # does not exist.  Existing secrets are never replaced.
    from app.config import settings

    dict_paths = {
        "uploads": Path(settings.UPLOAD_DIR),
        "tiles": Path(settings.TILES_DIR),
        "ai_results": Path(settings.AI_RESULTS_DIR),
        "annotations": Path(settings.ANNOTATIONS_DIR),
        "dicom_cache": Path(settings.DICOM_CACHE_DIR),
        "model": Path(settings.MODEL_DIR),
        "cell_annotation": PATH_BACKEND / "cell_annotation",
    }
    for str_name in LIST_RUNTIME_DIRS:
        path_target = dict_paths[str_name]
        path_target.mkdir(parents=True, exist_ok=True)
        int_access_mode = os.R_OK | os.X_OK if str_name == "model" else os.R_OK | os.W_OK | os.X_OK
        if not os.access(path_target, int_access_mode):
            str_requirement = "readable" if str_name == "model" else "writable"
            raise PermissionError(f"Runtime directory is not {str_requirement}: {path_target}")
    _log("OK", "Runtime directories and persistent secrets are ready.")
    return settings


def _find_source_file(path_source: Path, str_filename: str) -> Path | None:
    for path_candidate in (
        path_source / str_filename,
        path_source / "model" / str_filename,
        path_source / "backend" / "model" / str_filename,
    ):
        if path_candidate.is_file():
            return path_candidate
    return None


def _copy_model_directory(
    path_source: Path,
    path_model_dir: Path,
    list_models: list[dict],
    bool_force: bool,
) -> int:
    int_copied = 0
    for dict_model in list_models:
        str_filename = str(dict_model["filename"])
        path_input = _find_source_file(path_source, str_filename)
        path_output = path_model_dir / str_filename
        if path_input is None or (path_output.is_file() and path_output.stat().st_size > 0 and not bool_force):
            continue
        path_temp = path_output.with_name(f".{path_output.name}.installing")
        shutil.copy2(path_input, path_temp)
        os.replace(path_temp, path_output)
        int_copied += 1
    return int_copied


def _copy_model_archive(
    path_source: Path,
    path_model_dir: Path,
    list_models: list[dict],
    bool_force: bool,
) -> int:
    set_expected = {str(item["filename"]) for item in list_models}
    dict_members: dict[str, tuple[object, int]] = {}
    if zipfile.is_zipfile(path_source):
        with zipfile.ZipFile(path_source) as obj_archive:
            for obj_info in obj_archive.infolist():
                str_name = Path(obj_info.filename).name
                if str_name in set_expected and not obj_info.is_dir():
                    dict_members.setdefault(str_name, (obj_info, int(obj_info.file_size)))
            return _write_archive_models(
                path_model_dir,
                dict_members,
                lambda obj_info: obj_archive.open(obj_info, "r"),
                bool_force,
            )
    if tarfile.is_tarfile(path_source):
        with tarfile.open(path_source, "r:*") as obj_archive:
            for obj_info in obj_archive.getmembers():
                str_name = Path(obj_info.name).name
                if str_name in set_expected and obj_info.isfile():
                    dict_members.setdefault(str_name, (obj_info, int(obj_info.size)))
            return _write_archive_models(
                path_model_dir,
                dict_members,
                lambda obj_info: obj_archive.extractfile(obj_info),
                bool_force,
            )
    raise ValueError(f"Unsupported model bundle (use a directory, ZIP, TAR, or TAR.GZ): {path_source}")


def _write_archive_models(
    path_model_dir: Path,
    dict_members: dict[str, tuple[object, int]],
    fn_open_member,
    bool_force: bool,
) -> int:
    int_copied = 0
    for str_filename, (obj_info, int_expected_size) in dict_members.items():
        path_output = path_model_dir / str_filename
        if path_output.is_file() and path_output.stat().st_size > 0 and not bool_force:
            continue
        with tempfile.NamedTemporaryFile(dir=path_model_dir, prefix=".model-", delete=False) as obj_temp:
            path_temp = Path(obj_temp.name)
            obj_source = fn_open_member(obj_info)
            if obj_source is None:
                path_temp.unlink(missing_ok=True)
                continue
            with obj_source:
                shutil.copyfileobj(obj_source, obj_temp, length=8 * 1024 * 1024)
        if path_temp.stat().st_size != int_expected_size:
            path_temp.unlink(missing_ok=True)
            raise IOError(f"Incomplete model extracted from bundle: {str_filename}")
        os.replace(path_temp, path_output)
        int_copied += 1
    return int_copied


def _install_model_bundle(
    str_source: str,
    path_model_dir: Path,
    list_models: list[dict],
    bool_force: bool,
) -> None:
    if not str_source:
        return
    path_source = Path(str_source).expanduser().resolve()
    if not path_source.exists():
        raise FileNotFoundError(f"Model source does not exist: {path_source}")
    if path_source.is_dir():
        int_copied = _copy_model_directory(path_source, path_model_dir, list_models, bool_force)
    else:
        int_copied = _copy_model_archive(path_source, path_model_dir, list_models, bool_force)
    _log("OK", f"Installed {int_copied} model file(s) from {path_source}.")


def _check_models(path_model_dir: Path, list_models: list[dict]) -> tuple[list[dict], list[dict]]:
    list_missing_required = []
    list_missing_optional = []
    for dict_model in list_models:
        path_model = path_model_dir / str(dict_model["filename"])
        if path_model.is_file() and path_model.stat().st_size > 0:
            continue
        if bool(dict_model.get("required", True)):
            list_missing_required.append(dict_model)
        else:
            list_missing_optional.append(dict_model)
    if not list_missing_required:
        _log("OK", "All required AI model files are present.")
    else:
        _log("WARN", f"{len(list_missing_required)} required AI model file(s) are missing:")
        for dict_model in list_missing_required:
            print(f"       - {dict_model['filename']} ({dict_model['feature']})")
    for dict_model in list_missing_optional:
        _log("INFO", f"Optional model missing: {dict_model['filename']} ({dict_model['feature']})")
    return list_missing_required, list_missing_optional


def _check_native_dependencies() -> list[str]:
    list_errors = []
    for str_label, str_module in (
        ("OpenSlide", "openslide"),
        ("libvips/pyvips", "pyvips"),
        ("DICOM WSI", "dicomslide"),
    ):
        try:
            __import__(str_module)
            _log("OK", f"{str_label} is available.")
        except Exception as obj_error:
            list_errors.append(f"{str_label}: {obj_error}")
            _log("ERROR", f"{str_label} is unavailable: {obj_error}")
    try:
        import torch

        str_device = "CUDA" if torch.cuda.is_available() else "CPU"
        _log("OK", f"PyTorch {torch.__version__} is available ({str_device}).")
    except Exception as obj_error:
        list_errors.append(f"PyTorch: {obj_error}")
        _log("ERROR", f"PyTorch is unavailable: {obj_error}")
    return list_errors


def _check_philips_if_enabled() -> list[str]:
    bool_enabled = os.environ.get("MEDIAUTO_ENABLE_PHILIPS", "").strip().lower() in {
        "1", "true", "yes", "y",
    }
    if not bool_enabled and not os.environ.get("MEDIAUTO_PHILIPS_SDK_SOURCE", "").strip():
        _log("INFO", "Philips iSyntax support is not requested.")
        return []

    str_env_name = os.environ.get(
        "PHILIPS_CONDA_ENV",
        "philips-sdk-py37" if os.name == "nt" else "philips-sdk-py38",
    ).strip()
    str_python = os.environ.get("PHILIPS_PYTHON", "").strip()
    if str_python:
        list_command = [str_python]
    else:
        path_envs = Path(sys.prefix).resolve().parent
        path_python = (
            path_envs / str_env_name / "python.exe"
            if os.name == "nt"
            else path_envs / str_env_name / "bin" / "python"
        )
        if path_python.is_file():
            list_command = [str(path_python)]
        elif shutil.which("conda"):
            list_command = ["conda", "run", "-n", str_env_name, "python"]
        else:
            str_error = f"Philips environment cannot be located: {str_env_name}"
            _log("ERROR", str_error)
            return [str_error]
    list_command += [str(PATH_BACKEND / "scripts" / "bootstrap_philips.py"), "--check-only"]
    try:
        obj_result = subprocess.run(
            list_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=90,
        )
    except Exception as obj_error:
        str_error = f"Philips preflight failed: {obj_error}"
        _log("ERROR", str_error)
        return [str_error]
    if obj_result.returncode != 0:
        str_detail = (obj_result.stderr or obj_result.stdout).strip()
        str_error = f"Philips preflight failed: {str_detail}"
        _log("ERROR", str_error)
        return [str_error]
    _log("OK", f"Philips iSyntax environment is ready: {str_env_name}")
    return []


def _bootstrap_admin_document(str_login_id: str, str_password: str, str_name: str, str_department: str) -> dict:
    from app.models import ApprovalStatus, UserRole, create_user_document, hash_password

    return create_user_document(
        str_login_id=str_login_id,
        str_hashed_password=hash_password(str_password),
        str_name=str_name,
        str_role=UserRole.ADMIN,
        str_department=str_department,
        str_approval_status=ApprovalStatus.APPROVED,
        bool_is_active=True,
        str_approved_by="bootstrap",
    )


async def _check_postgres_and_admin(
    settings, bool_explicit: bool, str_login_id: str, str_password: str,
    str_name: str, str_department: str,
) -> tuple[bool, str]:
    from app.postgres.database import connect_postgres, disconnect_postgres
    from app.repositories.auth_store import PostgresUserStore

    try:
        await connect_postgres()
        obj_users = PostgresUserStore()
        int_user_count = await obj_users.count()
        _log("OK", "PostgreSQL is reachable and the application schema is ready.")
        if int_user_count > 0 and not bool_explicit:
            _log("INFO", "Existing PostgreSQL users found; default administrator bootstrap was skipped.")
            return True, ""
        if int_user_count > 0:
            if await obj_users.find_by_login_id(str_login_id):
                _log("OK", f"Bootstrap administrator already exists in PostgreSQL: {str_login_id}")
                return True, ""
            str_error = "PostgreSQL already contains users; automatic admin creation was refused."
            _log("ERROR", str_error)
            return False, str_error
        await obj_users.insert(
            _bootstrap_admin_document(
                str_login_id, str_password, str_name, str_department,
            )
        )
        _log("OK", f"Created the first PostgreSQL administrator: {str_login_id}")
        return True, ""
    except Exception as obj_error:
        str_error = f"PostgreSQL is unavailable or not initialized: {obj_error}"
        _log("WARN", str_error)
        return False, str_error
    finally:
        await disconnect_postgres()


def _check_database_and_admin(settings, bool_skip_db: bool) -> tuple[bool, str]:
    if bool_skip_db:
        _log("INFO", "Database checks skipped.")
        return True, ""
    try:
        from pymongo import MongoClient

        obj_client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
        obj_client.admin.command("ping")
        obj_mongo_db = obj_client[settings.MONGO_DB_NAME]
        _log("OK", f"MongoDB is reachable: {settings.MONGO_DB_NAME}")
    except Exception as obj_error:
        _log("WARN", f"MongoDB is unavailable: {obj_error}")
        return False, str(obj_error)

    bool_explicit, str_login_id, str_password, str_name, str_department = _admin_bootstrap_values()
    if not all((str_login_id, str_password, str_name)):
        obj_client.close()
        str_error = "Admin bootstrap requires ID, password, and name environment variables."
        _log("ERROR", str_error)
        return False, str_error
    if not STR_PASSWORD_PATTERN.match(str_password):
        obj_client.close()
        str_error = "Bootstrap admin password does not meet the application password policy."
        _log("ERROR", str_error)
        return False, str_error

    if settings.DATABASE_BACKEND == "postgresql":
        obj_client.close()
        return asyncio.run(_check_postgres_and_admin(
            settings, bool_explicit, str_login_id, str_password, str_name, str_department,
        ))
    if settings.DATABASE_BACKEND != "mongodb":
        obj_client.close()
        str_error = "DATABASE_BACKEND must be either 'mongodb' or 'postgresql'."
        _log("ERROR", str_error)
        return False, str_error

    try:
        int_user_count = obj_mongo_db.users.count_documents({})
        if int_user_count > 0 and not bool_explicit:
            _log("INFO", "Existing users found; default administrator bootstrap was skipped.")
            return True, ""
        if int_user_count > 0:
            if obj_mongo_db.users.find_one({"str_login_id": str_login_id}):
                _log("OK", f"Bootstrap admin already exists: {str_login_id}")
                return True, ""
            str_error = "Database already contains users; automatic admin creation was refused."
            _log("ERROR", str_error)
            return False, str_error

        dict_user = _bootstrap_admin_document(
            str_login_id, str_password, str_name, str_department,
        )
        obj_mongo_db.users.create_index("str_login_id", unique=True)
        obj_mongo_db.users.insert_one(dict_user)
        _log("OK", f"Created the first administrator: {str_login_id}")
        return True, ""
    finally:
        obj_client.close()


def main() -> int:
    obj_parser = argparse.ArgumentParser(description="Prepare and validate a MeDIAuto runtime.")
    obj_parser.add_argument(
        "--model-source",
        default=os.environ.get("MEDIAUTO_MODEL_SOURCE", ""),
        help="Directory or ZIP/TAR bundle containing AI model files.",
    )
    obj_parser.add_argument("--force-models", action="store_true", help="Replace existing model files.")
    obj_parser.add_argument("--strict-models", action="store_true", help="Fail if required models are missing.")
    obj_parser.add_argument("--strict-db", action="store_true", help="Fail if required databases/admin bootstrap are not ready.")
    obj_parser.add_argument("--skip-db", action="store_true", help="Skip database connectivity/admin checks.")
    obj_args = obj_parser.parse_args()

    try:
        settings = _prepare_runtime()
        list_models = _load_model_manifest()
        _install_model_bundle(
            obj_args.model_source,
            Path(settings.MODEL_DIR),
            list_models,
            obj_args.force_models,
        )
        list_missing_required, _ = _check_models(Path(settings.MODEL_DIR), list_models)
        list_native_errors = _check_native_dependencies()
        list_philips_errors = _check_philips_if_enabled()
        bool_db_ok, str_db_error = _check_database_and_admin(settings, obj_args.skip_db)
    except Exception as obj_error:
        _log("ERROR", str(obj_error))
        return 1

    list_failures = list(list_native_errors) + list(list_philips_errors)
    if obj_args.strict_models and list_missing_required:
        list_failures.append("required AI models are missing")
    if obj_args.strict_db and not bool_db_ok:
        list_failures.append(str_db_error or "Required databases are unavailable")
    if list_failures:
        _log("ERROR", "Bootstrap validation failed: " + "; ".join(list_failures))
        return 1

    if list_missing_required:
        _log("WARN", "Viewer can start, but AI features with missing models will be unavailable.")
    if not bool_db_ok:
        _log("WARN", "Database connectivity or administrator bootstrap needs attention before production use.")
    _log("OK", "Runtime bootstrap completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
