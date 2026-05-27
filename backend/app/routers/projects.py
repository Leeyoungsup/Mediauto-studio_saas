"""Project and folder management endpoints."""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app import slide_store
from app.auth import get_current_user, require_not_viewer, require_role
from app.config import settings
from app.database import get_db, is_db_connected
from app.models import UserRole
from app.path_utils import safe_filename, safe_subpath
from app.project_utils import (
    list_project_dirs,
    parse_ai_tasks_json,
    project_public_info,
    upsert_project_info,
)


router = APIRouter()


def _annotation_slide_dirname(filename: str) -> str:
    str_name = Path(filename).name.strip() or "slide"
    for ch in '<>:"/\\|?*':
        str_name = str_name.replace(ch, "_")
    str_name = "".join("_" if ord(ch) < 32 else ch for ch in str_name)
    str_name = str_name.rstrip(" .")
    return str_name or "slide"


async def _log_event(*args, **kwargs):
    from app.routers.slides import _log_management_event

    await _log_management_event(*args, **kwargs)


@router.get("/folder-tree")
async def folder_tree():
    upload_root = Path(settings.UPLOAD_DIR)
    list_folders: list[str] = []
    for dirpath, dirnames, _ in os.walk(upload_root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and not d.startswith("_chunks_")]
        for dir_name in sorted(dirnames):
            rel = os.path.relpath(os.path.join(dirpath, dir_name), upload_root)
            list_folders.append(rel.replace("\\", "/"))
    return {"folders": sorted(list_folders)}


@router.get("/projects")
async def list_projects():
    dict_infos = {}
    dict_metrics = {}
    if is_db_connected():
        db = get_db()
        async for dict_doc in db.project_infos.find({}):
            dict_infos[dict_doc.get("str_project_path", "")] = dict_doc
        async for dict_doc in db.slides.find(
            {},
            {"str_rel_path": 1, "str_status": 1, "str_annotation_status": 1, "dict_ai_results": 1},
        ):
            str_rel = (dict_doc.get("str_rel_path") or "").replace("\\", "/").strip("/")
            str_project = str_rel.split("/", 1)[0] if str_rel else ""
            if not str_project:
                continue
            dict_project = dict_metrics.setdefault(
                str_project,
                {
                    "annotation_count": 0,
                    "review_count": 0,
                    "termination_count": 0,
                    "reviewed_count": 0,
                    "in_progress_count": 0,
                    "ai_analyzed_count": 0,
                },
            )
            str_status = dict_doc.get("str_status") or ""
            str_annotation_status = dict_doc.get("str_annotation_status") or str_status
            if str_annotation_status in {"review", "done", "termination_in_progress", "termination", "flagged"}:
                dict_project["annotation_count"] += 1
            if str_annotation_status in {"termination_in_progress", "termination", "flagged"}:
                dict_project["review_count"] += 1
            if str_annotation_status == "termination":
                dict_project["termination_count"] += 1
            if str_status == "done":
                dict_project["reviewed_count"] += 1
            if str_status in {"pending", "in_progress"}:
                dict_project["in_progress_count"] += 1
            dict_ai = dict_doc.get("dict_ai_results") or {}
            bool_has_ai = False
            for str_model in slide_store.LIST_AI_MODEL_KEYS:
                dict_cur = dict_ai.get(str_model) or {}
                dict_legacy = dict_ai.get(slide_store._legacy_ai_model_key(str_model)) or {}
                if dict_cur.get("bool_has_result") or dict_legacy.get("bool_has_result"):
                    bool_has_ai = True
                    break
            if bool_has_ai:
                dict_project["ai_analyzed_count"] += 1

    list_projects_out = []
    for project_dir in list_project_dirs():
        int_slide_count = 0
        int_folder_count = 0
        for _root, dirs, files in os.walk(project_dir):
            dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("_chunks_")]
            int_folder_count += len(dirs)
            int_slide_count += sum(1 for file_name in files if Path(file_name).suffix.lower() in settings.SUPPORTED_EXTENSIONS)
        list_projects_out.append({
            "name": project_dir.name,
            "path": project_dir.name,
            "slide_count": int_slide_count,
            "folder_count": int_folder_count,
            "annotation_count": dict_metrics.get(project_dir.name, {}).get("annotation_count", 0),
            "review_count": dict_metrics.get(project_dir.name, {}).get("review_count", 0),
            "termination_count": dict_metrics.get(project_dir.name, {}).get("termination_count", 0),
            "reviewed_count": dict_metrics.get(project_dir.name, {}).get("reviewed_count", 0),
            "in_progress_count": dict_metrics.get(project_dir.name, {}).get("in_progress_count", 0),
            "ai_analyzed_count": dict_metrics.get(project_dir.name, {}).get("ai_analyzed_count", 0),
            "info": project_public_info(dict_infos.get(project_dir.name)),
        })
    return {"projects": list_projects_out}


@router.post("/project/create", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def create_project(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    institution: str = Form(""),
    department: str = Form(""),
    owner: str = Form(""),
    status: str = Form("active"),
    due_date: str = Form(""),
    description: str = Form(""),
    project_ai_enabled: bool = Form(False),
    project_ai_tasks_json: str = Form("[]"),
    annotation_ai_enabled: bool = Form(False),
    annotation_ai_key: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    name = safe_filename(name)
    target = safe_subpath("") / name
    if target.exists():
        raise HTTPException(400, "Project already exists")
    target.mkdir(parents=True, exist_ok=True)
    list_project_ai_tasks = parse_ai_tasks_json(project_ai_tasks_json)
    await upsert_project_info(
        str_project_path=name,
        str_title=title or name,
        str_institution=institution,
        str_department=department,
        str_owner=owner,
        str_status=status,
        str_due_date=due_date,
        str_description=description,
        bool_project_ai_enabled=project_ai_enabled,
        list_project_ai_tasks=list_project_ai_tasks,
        bool_annotation_ai_enabled=annotation_ai_enabled,
        str_annotation_ai_key=annotation_ai_key,
    )
    await _log_event(
        request,
        dict_user,
        str_action="project.create",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Created project {name}",
        dict_after={
            "title": title or name,
            "institution": institution,
            "department": department,
            "owner": owner,
            "status": status,
            "due_date": due_date,
            "description": description,
            "project_ai_enabled": bool(project_ai_enabled),
            "project_ai_tasks": list_project_ai_tasks,
            "annotation_ai_enabled": bool(annotation_ai_enabled),
            "annotation_ai_key": annotation_ai_key,
        },
    )
    return {"status": "created", "name": name, "path": name}


@router.post("/project/update", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def update_project(
    request: Request,
    name: str = Form(...),
    title: str = Form(""),
    institution: str = Form(""),
    department: str = Form(""),
    owner: str = Form(""),
    status: str = Form("active"),
    due_date: str = Form(""),
    description: str = Form(""),
    project_ai_enabled: bool = Form(False),
    project_ai_tasks_json: str = Form("[]"),
    annotation_ai_enabled: bool = Form(False),
    annotation_ai_key: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    name = safe_filename(name)
    target = safe_subpath(name)
    dict_before = None
    if is_db_connected():
        db = get_db()
        dict_before = project_public_info(await db.project_infos.find_one({"str_project_path": name}))
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Project not found")
    list_project_ai_tasks = parse_ai_tasks_json(project_ai_tasks_json)
    await upsert_project_info(
        str_project_path=name,
        str_title=title or name,
        str_institution=institution,
        str_department=department,
        str_owner=owner,
        str_status=status,
        str_due_date=due_date,
        str_description=description,
        bool_project_ai_enabled=project_ai_enabled,
        list_project_ai_tasks=list_project_ai_tasks,
        bool_annotation_ai_enabled=annotation_ai_enabled,
        str_annotation_ai_key=annotation_ai_key,
    )
    await _log_event(
        request,
        dict_user,
        str_action="project.update",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Updated project {name}",
        dict_before=dict_before,
        dict_after={
            "title": title or name,
            "institution": institution,
            "department": department,
            "owner": owner,
            "status": status,
            "due_date": due_date,
            "description": description,
            "project_ai_enabled": bool(project_ai_enabled),
            "project_ai_tasks": list_project_ai_tasks,
            "annotation_ai_enabled": bool(annotation_ai_enabled),
            "annotation_ai_key": annotation_ai_key,
        },
    )
    return {"status": "saved", "name": name, "path": name}


@router.post("/project/rename", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def rename_project(
    request: Request,
    name: str = Form(...),
    new_name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    name = safe_filename(name)
    new_name = safe_filename(new_name)
    target = safe_subpath(name)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Project not found")
    new_target = safe_subpath("") / new_name
    if new_target.exists():
        raise HTTPException(400, "Project name already exists")
    target.rename(new_target)
    await slide_store.rename_folder_in_db(name, new_name)
    old_class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(name)
    new_class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(new_name)
    if old_class_dir.exists() and not new_class_dir.exists():
        new_class_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_class_dir), str(new_class_dir))
    if is_db_connected():
        db = get_db()
        await db.project_infos.update_one(
            {"str_project_path": name},
            {"$set": {"str_project_path": new_name, "dt_updated_at": datetime.now(timezone.utc)}},
        )
    await _log_event(
        request,
        dict_user,
        str_action="project.rename",
        str_resource_type="project",
        str_resource_id=new_name,
        str_detail=f"Renamed project {name} to {new_name}",
        dict_extra={"str_old_path": name, "str_new_path": new_name},
        dict_before={"path": name},
        dict_after={"path": new_name},
    )
    return {"status": "renamed", "name": new_name, "path": new_name}


@router.post("/project/move-folder", dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.DOCTOR))])
async def move_folder_to_project(
    request: Request,
    src_path: str = Form(...),
    dst_project: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    src_path = src_path.replace("\\", "/").strip("/")
    dst_project = safe_filename(dst_project)
    if not src_path or "/" not in src_path:
        raise HTTPException(400, "Only subfolders can be moved into a project")
    target = safe_subpath(src_path)
    dst_project_dir = safe_subpath(dst_project)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Source folder not found")
    if not dst_project_dir.exists() or not dst_project_dir.is_dir():
        raise HTTPException(404, "Destination project not found")
    dst_path = dst_project_dir / target.name
    if dst_path.exists():
        raise HTTPException(400, "Destination folder already exists")
    shutil.move(str(target), str(dst_path))
    str_new_rel = f"{dst_project}/{target.name}"
    await slide_store.rename_folder_in_db(src_path, str_new_rel)
    await _log_event(
        request,
        dict_user,
        str_action="project.move_folder",
        str_resource_type="folder",
        str_resource_id=str_new_rel,
        str_detail=f"Moved folder {src_path} to {str_new_rel}",
        dict_extra={"str_src_path": src_path, "str_dst_path": str_new_rel, "str_dst_project": dst_project},
        dict_before={"path": src_path},
        dict_after={"path": str_new_rel},
    )
    return {"status": "moved", "src_path": src_path, "dst_path": str_new_rel}


@router.post("/project/delete", dependencies=[Depends(require_role(UserRole.ADMIN))])
async def delete_project(
    request: Request,
    name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    name = safe_filename(name)
    target = safe_subpath(name)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Project not found")
    if any(target.iterdir()):
        raise HTTPException(400, "Project must be empty before deletion")
    target.rmdir()
    if is_db_connected():
        db = get_db()
        dict_before = project_public_info(await db.project_infos.find_one({"str_project_path": name}))
        await db.project_infos.delete_one({"str_project_path": name})
    else:
        dict_before = None
    class_dir = Path(settings.ANNOTATIONS_DIR) / "_projects" / _annotation_slide_dirname(name)
    if class_dir.exists():
        shutil.rmtree(class_dir)
    await _log_event(
        request,
        dict_user,
        str_action="project.delete",
        str_resource_type="project",
        str_resource_id=name,
        str_detail=f"Deleted project {name}",
        dict_before=dict_before,
    )
    return {"status": "deleted", "name": name}


@router.post("/folder/create")
async def create_folder(
    request: Request,
    path: str = Form(""),
    name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    name = safe_filename(name)
    target = safe_subpath(path) / name
    if target.exists():
        raise HTTPException(400, "Folder already exists")
    target.mkdir(parents=True, exist_ok=True)
    str_parent = path.replace("\\", "/").strip("/")
    str_new_rel = f"{str_parent}/{name}" if str_parent else name
    await _log_event(
        request,
        dict_user,
        str_action="folder.create",
        str_resource_type="folder",
        str_resource_id=str_new_rel,
        str_detail=f"Created folder {str_new_rel}",
        dict_after={"path": str_new_rel},
    )
    return {"status": "created", "path": str_new_rel}


@router.post("/folder/rename")
async def rename_folder(
    request: Request,
    path: str = Form(...),
    new_name: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    new_name = safe_filename(new_name)
    target = safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Folder not found")
    new_target = target.parent / new_name
    if new_target.exists():
        raise HTTPException(400, "Folder name already exists")
    target.rename(new_target)
    old_rel = path.replace("\\", "/").strip("/")
    parent_rel = "/".join(old_rel.split("/")[:-1])
    new_rel = f"{parent_rel}/{new_name}" if parent_rel else new_name
    await slide_store.rename_folder_in_db(old_rel, new_rel)
    await _log_event(
        request,
        dict_user,
        str_action="folder.rename",
        str_resource_type="folder",
        str_resource_id=new_rel,
        str_detail=f"Renamed folder {old_rel} to {new_rel}",
        dict_extra={"str_old_path": old_rel, "str_new_path": new_rel},
        dict_before={"path": old_rel},
        dict_after={"path": new_rel},
    )
    return {"status": "renamed"}


@router.post("/folder/delete")
async def delete_folder(
    request: Request,
    path: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    target = safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "Folder not found")
    if list(target.iterdir()):
        raise HTTPException(400, "Folder must be empty before deletion")
    target.rmdir()
    str_rel = path.replace("\\", "/").strip("/")
    await _log_event(
        request,
        dict_user,
        str_action="folder.delete",
        str_resource_type="folder",
        str_resource_id=str_rel,
        str_detail=f"Deleted folder {str_rel}",
        dict_before={"path": str_rel},
    )
    return {"status": "deleted"}
