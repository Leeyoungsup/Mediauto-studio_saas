"""Slide file management endpoints."""

import hashlib
import json
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app import slide_store, tile_generator
from app.auth import get_current_user
from app.config import settings
from app.path_utils import safe_filename, safe_subpath
from app.slide_identity import slide_cache_key
from app.slide_manager import slide_manager


router = APIRouter()


def _cleanup_ai_caches_for_prefixes(list_prefixes: list[str]) -> list:
    list_removed = []
    ai_dir = Path(settings.AI_RESULTS_DIR)
    if not ai_dir.exists():
        return list_removed
    list_sub_dirs = [ai_dir] + [
        ai_dir / name for name in (
            "Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC",
            "HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC",
        )
    ]
    for folder in list_sub_dirs:
        if not folder.exists() or not folder.is_dir():
            continue
        for str_prefix in list_prefixes:
            for path in folder.glob(f"{str_prefix}_*"):
                try:
                    if path.is_dir():
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        path.unlink()
                    list_removed.append(str(path))
                except Exception as exc:
                    print(f"[file_operations] AI cache cleanup failed ({path}): {exc}")
    return list_removed


async def _delete_slide_file(str_path: str, str_filename: str) -> dict:
    str_filename = safe_filename(str_filename)
    target = safe_subpath(str_path) / str_filename
    if not target.exists():
        raise HTTPException(404, f"File not found: {str_filename}")

    str_slide_id = hashlib.md5(str_filename.encode()).hexdigest()[:12]
    if slide_manager.get(str_slide_id) is not None:
        try:
            slide_manager.close(str_slide_id)
        except Exception as exc:
            print(f"[file_operations] close before delete failed ({str_filename}): {exc}")

    try:
        target.unlink()
    except Exception as exc:
        raise HTTPException(500, f"File delete failed: {exc}")

    try:
        tiles_dir = tile_generator.get_tiles_dir_for_path(str(target))
        if tiles_dir.exists():
            shutil.rmtree(tiles_dir, ignore_errors=True)
        legacy_tiles_dir = tile_generator.get_tiles_dir(str_filename)
        if legacy_tiles_dir.exists():
            shutil.rmtree(legacy_tiles_dir, ignore_errors=True)
    except Exception as exc:
        print(f"[file_operations] tiles dir cleanup failed ({str_filename}): {exc}")

    list_removed_ai = _cleanup_ai_caches_for_prefixes([
        slide_cache_key(str(target)),
        Path(str_filename).stem,
    ])
    try:
        await slide_store.delete_slide(str_path, str_filename)
    except Exception as exc:
        print(f"[file_operations] DB delete failed ({str_filename}): {exc}")

    return {"filename": str_filename, "ai_files_removed": len(list_removed_ai)}


async def _log_event(*args, **kwargs):
    from app.routers.slides import _log_management_event

    await _log_management_event(*args, **kwargs)


@router.post("/file/delete")
async def delete_slide_files(
    request: Request,
    filenames_json: str = Form(...),
    path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as exc:
        raise HTTPException(400, f"Invalid filenames_json: {exc}")

    list_results = []
    list_errors = []
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            dict_res = await _delete_slide_file(path, str_fn)
            list_results.append(dict_res)
        except HTTPException as exc:
            list_errors.append({"filename": str_fn, "error": exc.detail})
        except Exception as exc:
            list_errors.append({"filename": str_fn, "error": str(exc)})

    await _log_event(
        request,
        dict_user,
        str_action="file.delete",
        str_resource_type="file",
        str_resource_id=path.replace("\\", "/").strip("/"),
        str_detail=f"Deleted {len(list_results)} file(s) from {path or 'root'}",
        dict_extra={
            "str_rel_path": path.replace("\\", "/").strip("/"),
            "list_filenames": [result.get("filename") for result in list_results],
            "list_errors": list_errors,
        },
        dict_before={"filenames": [result.get("filename") for result in list_results], "path": path},
    )
    return {"status": "ok", "deleted": list_results, "errors": list_errors}


@router.post("/file/status")
async def set_file_status(
    request: Request,
    filenames_json: str = Form(...),
    path: str = Form(""),
    status: str = Form(""),
    scope: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    str_scope = (scope or "").strip().lower()
    if str_scope not in {"", "ai", "annotation", "tissue_annotation", "cell_annotation"}:
        raise HTTPException(400, f"Invalid status scope: {scope}")
    if status not in slide_store.SET_SLIDE_STATUSES:
        raise HTTPException(400, f"Invalid status: {status}")
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as exc:
        raise HTTPException(400, f"Invalid filenames_json: {exc}")

    int_updated = 0
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            await slide_store.set_slide_status(path, str_fn, status, str_scope)
            int_updated += 1
        except Exception as exc:
            print(f"[file_operations] set_slide_status failed ({str_fn}): {exc}")
    await _log_event(
        request,
        dict_user,
        str_action="slide.status_update",
        str_resource_type="slide",
        str_resource_id=path.replace("\\", "/").strip("/"),
        str_detail=f"Set {str_scope or 'legacy'} status {status or 'none'} on {int_updated} slide(s)",
        dict_extra={
            "str_rel_path": path.replace("\\", "/").strip("/"),
            "list_filenames": [name for name in list_filenames if isinstance(name, str) and name],
            "str_status": status,
            "str_scope": str_scope,
            "int_updated": int_updated,
        },
        dict_after={"status": status, "scope": str_scope},
    )
    return {"status": "ok", "updated": int_updated}


@router.post("/file/move")
async def move_file(
    request: Request,
    filename: str = Form(...),
    src_path: str = Form(""),
    dst_path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    filename = safe_filename(filename)
    src = safe_subpath(src_path) / filename
    dst_dir = safe_subpath(dst_path)
    if not src.exists():
        raise HTTPException(404, "Source file not found")
    if not dst_dir.exists() or not dst_dir.is_dir():
        raise HTTPException(404, "Destination folder not found")
    dst = dst_dir / filename
    if dst.exists():
        raise HTTPException(400, "Destination file already exists")
    shutil.move(str(src), str(dst))
    await slide_store.move_slide(src_path, filename, dst_path, str(dst))
    await _log_event(
        request,
        dict_user,
        str_action="file.move",
        str_resource_type="file",
        str_resource_id=filename,
        str_detail=f"Moved file {filename} from {src_path or 'root'} to {dst_path or 'root'}",
        dict_extra={"str_filename": filename, "str_src_path": src_path, "str_dst_path": dst_path},
        dict_before={"path": src_path, "filename": filename},
        dict_after={"path": dst_path, "filename": filename},
    )
    return {"status": "moved"}
