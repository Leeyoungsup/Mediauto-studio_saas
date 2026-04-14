"""
슬라이드 관리 API — 업로드 (청크), 서버 파일 열기, 목록, 정보, 삭제
타일 프리제네레이션 트리거 + 진행 상태 조회
"""

import os
import json
import uuid
import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import JSONResponse, StreamingResponse

from app.auth import get_current_user
from app.config import settings
from app.slide_manager import slide_manager
from app import tile_generator
from app import slide_store
from app import auto_ai
from app.cpu_layout import bg_executor

router = APIRouter(dependencies=[Depends(get_current_user)])


def _rel_path_for(file_path: str) -> str:
    """uploads/ 기준 상대 폴더 경로 ('' = 루트). 파일명 제외."""
    try:
        upload_dir = Path(settings.UPLOAD_DIR).resolve()
        p = Path(file_path).resolve()
        rel = p.parent.relative_to(upload_dir)
        s = str(rel).replace("\\", "/")
        return "" if s in (".", "") else s
    except Exception:
        return ""


def _slide_response(slide_id: str, info, filename: str):
    """슬라이드 정보 응답 공통 포맷"""
    return {
        "slide_id": slide_id,
        "filename": filename,
        "dimensions": info.dimensions,
        "level_count": info.level_count,
        "level_dimensions": info.level_dimensions,
        "level_downsamples": info.level_downsamples,
        "mpp": info.mpp,
        "mpp_x": info.mpp_x,
        "mpp_y": info.mpp_y,
        "vendor": info.vendor,
        "objective_power": info.objective_power,
        "physical_width_mm": info.physical_width_mm,
        "physical_height_mm": info.physical_height_mm,
        "tiles_ready": tile_generator.tiles_ready(filename),
    }


async def _open_and_generate(
    slide_id: str,
    file_path: str,
    filename: str,
    dict_user: Optional[dict] = None,
    bool_wait_for_tiles: bool = False,
):
    """슬라이드 열기 + 타일 생성 → DB 업서트 후 응답 반환.

    `bool_wait_for_tiles=True` 면 업로드 경로에서 호출된 것으로, 타일 프리젠이
    끝날 때까지 기다린 뒤 응답을 돌려준다. 터널/원격 환경에서 on-demand 타일
    생성이 느려 사용자 경험이 나빠지는 것을 방지.
    """
    # 이미 열려있으면 그대로
    existing = slide_manager.get(slide_id)
    if existing:
        await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
        resp = _slide_response(slide_id, existing, filename)
        await _upsert_and_attach(resp, slide_id, file_path, filename, existing, dict_user)
        return resp

    try:
        info = slide_manager.open(slide_id, file_path)
    except Exception as e:
        raise HTTPException(400, f"슬라이드 열기 실패: {e}")

    await _run_tile_gen(filename, file_path, bool_wait_for_tiles)
    resp = _slide_response(slide_id, info, filename)
    await _upsert_and_attach(resp, slide_id, file_path, filename, info, dict_user)
    return resp


async def _run_tile_gen(filename: str, file_path: str, bool_wait: bool) -> None:
    """타일 생성 실행. wait 모드에서는 동기 실행 (bg_executor), 아니면 백그라운드 스레드."""
    if tile_generator.tiles_ready(filename):
        return
    if not bool_wait:
        tile_generator.start_generation(filename, file_path)
        return
    # 동기 실행 — bg_executor 에 올려 이벤트 루프는 안 막는다
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        bg_executor, tile_generator._generate_tiles, filename, file_path
    )
    # mark_tiles_ready 는 _generate_tiles 가 threadsafe 로 예약하지만,
    # 업로드 응답 전에 DB 가 확실히 최신이 되도록 한 번 더 동기 마킹.
    try:
        str_rel = _rel_path_for(file_path)
        await slide_store.mark_tiles_ready(str_rel, filename, True)
    except Exception as e:
        print(f"[slides] mark_tiles_ready post-upload failed ({filename}): {e}")


async def _upsert_and_attach(
    resp: dict,
    slide_id: str,
    file_path: str,
    filename: str,
    info,
    dict_user: Optional[dict],
):
    """slides 컬렉션에 upsert + 응답에 ai_results 플래그 부착 (DB 없으면 no-op)."""
    try:
        int_size_bytes = os.path.getsize(file_path)
    except Exception:
        int_size_bytes = 0

    str_uploaded_by = ""
    if dict_user:
        str_uploaded_by = str(dict_user.get("_id") or "")

    dict_doc = await slide_store.upsert_slide(
        str_slide_id=slide_id,
        str_filename=filename,
        str_rel_path=_rel_path_for(file_path),
        str_full_path=file_path,
        dict_info=resp,
        int_size_bytes=int_size_bytes,
        str_uploaded_by=str_uploaded_by,
    )
    if dict_doc:
        resp["ai_results"] = slide_store.serialize_slide_doc(dict_doc).get("dict_ai_results")
        resp["uploaded_at"] = dict_doc.get("dt_uploaded_at").isoformat() if dict_doc.get("dt_uploaded_at") else None


# ── 저장된 슬라이드/폴더 목록 ──

def _safe_subpath(subpath: str) -> Path:
    """uploads/ 하위 경로만 허용 (디렉토리 탈출 방지)"""
    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    target = (upload_dir / subpath).resolve()
    if not str(target).startswith(str(upload_dir)):
        raise HTTPException(400, "잘못된 경로")
    return target


@router.get("/browse")
async def browse(path: str = Query("", description="uploads/ 기준 상대 경로")):
    """현재 폴더의 하위 폴더 + 슬라이드 파일 목록 (DB 의 ai_results 플래그 포함)"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")

    folders = []
    slides = []

    # DB 에서 현재 폴더 슬라이드 문서 한 번에 조회
    dict_db_slides = await slide_store.list_slides_in_folder(path)

    for f in sorted(target.iterdir()):
        if f.name.startswith("_chunks_") or f.name.startswith("."):
            continue
        if f.is_dir():
            folders.append({"name": f.name, "type": "folder"})
        elif f.is_file() and f.suffix.lower() in settings.SUPPORTED_EXTENSIONS:
            slide_id = hashlib.md5(f.name.encode()).hexdigest()[:12]
            dict_item = {
                "filename": f.name,
                "slide_id": slide_id,
                "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                "type": "slide",
            }
            # DB 문서가 있으면 ai_results + 업로드 메타 부착
            dict_db = dict_db_slides.get(f.name)
            if dict_db:
                dict_ai = dict_db.get("dict_ai_results") or slide_store._empty_ai_results()
                dict_item["ai_results"] = {
                    str_k: {
                        "has_result": bool(v.get("bool_has_result")),
                        "variants": list(v.get("list_variants") or []),
                    }
                    for str_k, v in dict_ai.items()
                }
                dict_item["uploaded_by"] = dict_db.get("str_uploaded_by") or ""
                dt_opened = dict_db.get("dt_last_opened_at")
                dict_item["last_opened_at"] = dt_opened.isoformat() if dt_opened else None
                dict_item["status"] = dict_db.get("str_status") or ""
            else:
                dict_item["ai_results"] = None
                dict_item["status"] = ""
            slides.append(dict_item)

    return {"path": path, "folders": folders, "slides": slides}


@router.post("/folder/create")
async def create_folder(path: str = Form(""), name: str = Form(...)):
    """폴더 생성"""
    target = _safe_subpath(path) / name
    if target.exists():
        raise HTTPException(400, "이미 존재하는 폴더입니다")
    target.mkdir(parents=True, exist_ok=True)
    return {"status": "created", "path": str(Path(path) / name)}


@router.post("/folder/rename")
async def rename_folder(path: str = Form(...), new_name: str = Form(...)):
    """폴더 이름 변경"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")
    new_target = target.parent / new_name
    if new_target.exists():
        raise HTTPException(400, "이미 존재하는 이름입니다")
    target.rename(new_target)

    # DB 에 저장된 하위 슬라이드 문서의 rel_path 갱신
    old_rel = path.replace("\\", "/").strip("/")
    parent_rel = "/".join(old_rel.split("/")[:-1])
    new_rel = f"{parent_rel}/{new_name}" if parent_rel else new_name
    await slide_store.rename_folder_in_db(old_rel, new_rel)
    return {"status": "renamed"}


@router.post("/folder/delete")
async def delete_folder(path: str = Form(...)):
    """폴더 삭제 (비어있을 때만)"""
    target = _safe_subpath(path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(404, "폴더를 찾을 수 없습니다")
    # 비어있는지 확인
    children = list(target.iterdir())
    if children:
        raise HTTPException(400, "폴더가 비어있지 않습니다")
    target.rmdir()
    return {"status": "deleted"}


def _cleanup_ai_caches_for_stem(str_stem: str) -> list:
    """주어진 slide stem 에 속한 AI 결과 캐시/타일 피라미드 제거.

    파일/폴더 명명 규칙:
        - ai_results/HE-Fit/{stem}_HE-Fit_*.json
        - ai_results/PD-Score/{stem}_PD-Score_*.json
        - ai_results/Precise-IHC/{stem}_Precise-IHC_*.json
        - ai_results/VS-IHC/{stem}_VS-IHC_*.(png|json)
        - ai_results/VS-IHC/{stem}_VS-IHC_*_tile/  (피라미드 폴더)
        - ai_results/{stem}_*  (레거시 루트)
    """
    list_removed = []
    try:
        ai_dir = Path(settings.AI_RESULTS_DIR)
    except Exception:
        return list_removed
    if not ai_dir.exists():
        return list_removed
    list_sub_dirs = [ai_dir] + [ai_dir / s for s in ("HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC")]
    for d in list_sub_dirs:
        if not d.exists() or not d.is_dir():
            continue
        for p in d.glob(f"{str_stem}_*"):
            try:
                if p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    p.unlink()
                list_removed.append(str(p))
            except Exception as e:
                print(f"[slides] AI cache cleanup failed ({p}): {e}")
    return list_removed


async def _delete_slide_file(str_path: str, str_filename: str) -> dict:
    """파일 + 타일 디렉토리 + AI 결과 캐시 + DB 문서를 모두 제거.

    열려있는 슬라이드면 먼저 close.
    """
    target = _safe_subpath(str_path) / str_filename
    if not target.exists():
        raise HTTPException(404, f"파일을 찾을 수 없습니다: {str_filename}")

    # 열려있는 슬라이드는 먼저 닫기
    str_slide_id = hashlib.md5(str_filename.encode()).hexdigest()[:12]
    if slide_manager.get(str_slide_id) is not None:
        try:
            slide_manager.close(str_slide_id)
        except Exception as e:
            print(f"[slides] close before delete failed ({str_filename}): {e}")

    str_stem = Path(str_filename).stem

    # 1) 원본 파일 삭제
    try:
        target.unlink()
    except Exception as e:
        raise HTTPException(500, f"파일 삭제 실패: {e}")

    # 2) 타일 피라미드 폴더 삭제
    try:
        tiles_dir = tile_generator.get_tiles_dir(str_filename)
        if tiles_dir.exists():
            shutil.rmtree(tiles_dir, ignore_errors=True)
    except Exception as e:
        print(f"[slides] tiles dir cleanup failed ({str_filename}): {e}")

    # 3) AI 결과 캐시 + VS 타일 피라미드 삭제
    list_removed_ai = _cleanup_ai_caches_for_stem(str_stem)

    # 4) DB 문서 제거
    try:
        await slide_store.delete_slide(str_path, str_filename)
    except Exception as e:
        print(f"[slides] DB delete failed ({str_filename}): {e}")

    return {"filename": str_filename, "ai_files_removed": len(list_removed_ai)}


@router.post("/file/delete")
async def delete_slide_files(
    filenames_json: str = Form(...),
    path: str = Form(""),
):
    """슬라이드 파일들 + AI 결과/타일 캐시 + DB 문서 일괄 삭제.

    filenames_json: JSON list (예: ["a.svs","b.ndpi"])
    """
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as e:
        raise HTTPException(400, f"잘못된 filenames_json: {e}")

    list_results = []
    list_errors = []
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            dict_res = await _delete_slide_file(path, str_fn)
            list_results.append(dict_res)
        except HTTPException as he:
            list_errors.append({"filename": str_fn, "error": he.detail})
        except Exception as e:
            list_errors.append({"filename": str_fn, "error": str(e)})

    return {
        "status": "ok",
        "deleted": list_results,
        "errors": list_errors,
    }


@router.post("/file/status")
async def set_file_status(
    filenames_json: str = Form(...),
    path: str = Form(""),
    status: str = Form(""),
):
    """슬라이드 리뷰 상태 일괄 설정.

    status: "" | "pending" | "in_progress" | "done" | "flagged"
    """
    if status not in slide_store.SET_SLIDE_STATUSES:
        raise HTTPException(400, f"잘못된 status: {status}")
    try:
        list_filenames = json.loads(filenames_json)
        if not isinstance(list_filenames, list):
            raise ValueError("filenames_json must be a JSON list")
    except Exception as e:
        raise HTTPException(400, f"잘못된 filenames_json: {e}")

    int_updated = 0
    for str_fn in list_filenames:
        if not isinstance(str_fn, str) or not str_fn:
            continue
        try:
            await slide_store.set_slide_status(path, str_fn, status)
            int_updated += 1
        except Exception as e:
            print(f"[slides] set_slide_status failed ({str_fn}): {e}")
    return {"status": "ok", "updated": int_updated}


@router.post("/file/move")
async def move_file(filename: str = Form(...), src_path: str = Form(""), dst_path: str = Form("")):
    """파일을 다른 폴더로 이동"""
    src = _safe_subpath(src_path) / filename
    dst_dir = _safe_subpath(dst_path)
    if not src.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다")
    if not dst_dir.exists() or not dst_dir.is_dir():
        raise HTTPException(404, "대상 폴더를 찾을 수 없습니다")
    dst = dst_dir / filename
    if dst.exists():
        raise HTTPException(400, "대상 폴더에 같은 이름의 파일이 있습니다")
    shutil.move(str(src), str(dst))
    await slide_store.move_slide(src_path, filename, dst_path, str(dst))
    return {"status": "moved"}


# ── 서버에 파일 존재 확인 후 바로 열기 ──

@router.post("/open")
async def open_slide(
    filename: str = Form(...),
    path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """파일명으로 서버 디스크에 있는지 확인 → 있으면 바로 열기"""
    final_path = _safe_subpath(path) / filename
    if not final_path.exists():
        return {"exists": False}

    slide_id = hashlib.md5(filename.encode()).hexdigest()[:12]
    resp = await _open_and_generate(slide_id, str(final_path), filename, dict_user)
    resp["exists"] = True
    return resp


# ── 청크 업로드 ──

@router.post("/upload/start")
async def upload_start(filename: str = Form(...)):
    """업로드 시작 — upload_id 발급"""
    ext = Path(filename).suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

    upload_id = uuid.uuid4().hex[:12]
    chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    return {
        "upload_id": upload_id,
        "filename": filename,
        "chunk_size": settings.CHUNK_SIZE,
    }


@router.post("/upload/chunk")
async def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
):
    """청크 업로드 — 개별 청크 저장. 업로드 카운터로 auto_ai 일시정지."""
    auto_ai.upload_enter()
    try:
        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "업로드 세션을 찾을 수 없습니다")

        chunk_path = chunk_dir / f"chunk_{chunk_index:06d}"
        content = await chunk.read()
        with open(chunk_path, "wb") as f:
            f.write(content)

        return {"chunk_index": chunk_index, "size": len(content)}
    finally:
        auto_ai.upload_exit()


@router.post("/upload/complete")
async def upload_complete(
    upload_id: str = Form(...),
    filename: str = Form(...),
    total_chunks: int = Form(...),
    path: str = Form(""),
    dict_user: dict = Depends(get_current_user),
):
    """업로드 완료 — 청크 조립 → 슬라이드 열기 + 타일 생성"""
    auto_ai.upload_enter()
    try:
        chunk_dir = Path(settings.UPLOAD_DIR) / f"_chunks_{upload_id}"
        if not chunk_dir.exists():
            raise HTTPException(404, "업로드 세션을 찾을 수 없습니다")

        # 확장자 재검증 (start 단계 우회 방지)
        ext = Path(filename).suffix.lower()
        if ext not in settings.SUPPORTED_EXTENSIONS:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

        # 청크 총 크기 선집계 → 상한 초과 시 조립 전에 거부
        int_total_bytes = 0
        for i in range(total_chunks):
            chunk_path = chunk_dir / f"chunk_{i:06d}"
            if not chunk_path.exists():
                shutil.rmtree(chunk_dir, ignore_errors=True)
                raise HTTPException(400, f"청크 {i} 누락")
            int_total_bytes += chunk_path.stat().st_size
        if int_total_bytes > settings.MAX_UPLOAD_BYTES:
            shutil.rmtree(chunk_dir, ignore_errors=True)
            int_limit_gb = settings.MAX_UPLOAD_BYTES / (1024 ** 3)
            raise HTTPException(
                413,
                f"업로드 크기 상한 초과: {int_total_bytes / (1024**3):.2f} GB > {int_limit_gb:.2f} GB",
            )

        save_dir = _safe_subpath(path)
        save_dir.mkdir(parents=True, exist_ok=True)
        final_path = save_dir / filename

        bool_newly_written = False
        if final_path.exists():
            shutil.rmtree(chunk_dir, ignore_errors=True)
        else:
            with open(final_path, "wb") as out:
                for i in range(total_chunks):
                    chunk_path = chunk_dir / f"chunk_{i:06d}"
                    with open(chunk_path, "rb") as cf:
                        shutil.copyfileobj(cf, out)
            shutil.rmtree(chunk_dir, ignore_errors=True)
            bool_newly_written = True

        slide_id = hashlib.md5(filename.encode()).hexdigest()[:12]
        try:
            return await _open_and_generate(
                slide_id, str(final_path), filename, dict_user,
                bool_wait_for_tiles=True,
            )
        except HTTPException:
            # OpenSlide 열기 실패 — 손상/위조 파일로 간주, 이번 업로드로 쓴 경우만 정리
            if bool_newly_written and final_path.exists():
                try:
                    final_path.unlink()
                except Exception:
                    pass
            raise
    finally:
        auto_ai.upload_exit()


# ── 서버 로컬 파일 열기 ──

@router.post("/open-local")
async def open_local_file(
    file_path: str = Form(...),
    dict_user: dict = Depends(get_current_user),
):
    """서버 로컬 디스크의 WSI 파일 열기"""
    path = Path(file_path)
    if not path.exists():
        raise HTTPException(404, f"파일이 존재하지 않습니다: {file_path}")

    ext = path.suffix.lower()
    if ext not in settings.SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"지원하지 않는 파일 형식: {ext}")

    slide_id = hashlib.md5(path.name.encode()).hexdigest()[:12]
    return await _open_and_generate(slide_id, str(path), path.name, dict_user)


# ── 타일 생성 진행 상태 ──

@router.get("/tile-progress/{slide_id}")
async def get_tile_progress(slide_id: str):
    """타일 프리제네레이션 진행 상태 (slide_id로 filename 조회)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    progress = tile_generator.get_progress(filename)
    if progress is None:
        raise HTTPException(404, "타일 생성 정보를 찾을 수 없습니다")
    return progress


# ── 슬라이드 정보 ──

@router.get("/{slide_id}/info")
async def get_slide_info(slide_id: str):
    """슬라이드 메타데이터 조회"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    return {
        "slide_id": slide_id,
        "file_path": info.file_path,
        "dimensions": info.dimensions,
        "level_count": info.level_count,
        "level_dimensions": info.level_dimensions,
        "level_downsamples": info.level_downsamples,
        "mpp": info.mpp,
        "tiles_ready": tile_generator.tiles_ready(Path(info.file_path).name),
    }


@router.get("/thumbnail-by-name")
async def get_thumbnail_by_name(
    filename: str = Query(...),
    path: str = Query(""),
    size: int = Query(300, ge=64, le=1024),
):
    """파일명 기반 썸네일 — slide_manager 불필요, 디스크에서 바로 반환"""
    import io
    import openslide

    # 1) 프리제네레이트된 썸네일이 있으면 바로 반환
    thumb_path = tile_generator.get_tiles_dir(filename) / "thumbnail.jpeg"
    if thumb_path.exists():
        return StreamingResponse(open(thumb_path, "rb"), media_type="image/jpeg")

    # 2) 없으면 즉석 생성 + 저장
    file_path = _safe_subpath(path) / filename
    if not file_path.exists():
        raise HTTPException(404, "파일을 찾을 수 없습니다")

    try:
        slide = openslide.OpenSlide(str(file_path))
        thumb = slide.get_thumbnail((size, size))
        thumb_rgb = thumb.convert("RGB")

        # ICC → sRGB 픽셀 변환 (한 번만, JPEG 임베드 X)
        try:
            obj_profile = getattr(slide, "color_profile", None)
            if obj_profile is not None:
                from PIL import ImageCms
                obj_srgb = ImageCms.createProfile("sRGB")
                obj_tx = ImageCms.buildTransform(obj_profile, obj_srgb, "RGB", "RGB")
                thumb_rgb = ImageCms.applyTransform(thumb_rgb, obj_tx)
        except Exception:
            pass

        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_rgb.save(str(thumb_path), "JPEG", quality=85)
        slide.close()

        buf = io.BytesIO()
        thumb_rgb.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(500, f"썸네일 생성 실패: {e}")


@router.get("/{slide_id}/preview")
async def get_preview(slide_id: str, size: int = Query(2048, ge=512, le=8192)):
    """고해상도 슬라이드 프리뷰 (PDF 리포트용, 캐시 미사용)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    import io
    thumb = info.slide.get_thumbnail((size, size))
    thumb_rgb = info.apply_icc(thumb.convert("RGB"))
    buf = io.BytesIO()
    thumb_rgb.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


@router.get("/{slide_id}/thumbnail")
async def get_thumbnail(slide_id: str, size: int = Query(300, ge=64, le=1024)):
    """slide_id 기반 썸네일 (하위 호환)"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    thumb_path = tile_generator.get_tiles_dir(filename) / "thumbnail.jpeg"
    if thumb_path.exists():
        return StreamingResponse(open(thumb_path, "rb"), media_type="image/jpeg")

    import io
    thumb = info.slide.get_thumbnail((size, size))
    thumb_rgb = info.apply_icc(thumb.convert("RGB"))
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    thumb_rgb.save(str(thumb_path), "JPEG", quality=85)
    buf = io.BytesIO()
    thumb_rgb.save(buf, format="JPEG", quality=85)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/jpeg")


# ── 목록 / 삭제 ──

@router.get("/")
async def list_slides():
    """열린 슬라이드 목록"""
    return slide_manager.list_slides()


# ═══════════════════════════════════════════════════════
# 폴더별 AI 자동 추론 설정 — folder_ai_configs 컬렉션
# ═══════════════════════════════════════════════════════

from datetime import datetime, timezone
from app.database import get_db, is_db_connected


def _norm_folder_path(str_path: str) -> str:
    if not str_path:
        return ""
    return str_path.replace("\\", "/").strip("/")


@router.get("/folder-config")
async def get_folder_config(path: str = Query("")):
    """폴더의 AI 자동 추론 설정 조회 — 없으면 기본값 반환."""
    if not is_db_connected():
        return {"path": path, "enabled": False, "tasks": []}
    db = get_db()
    str_norm = _norm_folder_path(path)
    dict_doc = await db.folder_ai_configs.find_one({"str_rel_path": str_norm})
    if not dict_doc:
        return {"path": path, "enabled": False, "tasks": []}
    list_out = []
    for t in (dict_doc.get("list_tasks") or []):
        dict_task = {"model": t.get("model", ""), "variant": t.get("variant", "")}
        if t.get("target_mpp") is not None:
            dict_task["target_mpp"] = float(t.get("target_mpp"))
        list_out.append(dict_task)
    return {
        "path": str_norm,
        "enabled": bool(dict_doc.get("bool_enabled", False)),
        "tasks": list_out,
    }


@router.post("/folder-config")
async def save_folder_config(
    path: str = Form(""),
    enabled: bool = Form(True),
    tasks_json: str = Form("[]"),
):
    """폴더의 AI 자동 추론 설정 저장/업서트.

    tasks_json: JSON array — `[{"model": "HE-Fit", "variant": "Stomach"}, ...]`
      model 은 {HE-Fit, PD-Score, Precise-IHC} 중 하나, variant 는 tissue_type/marker.
    """
    if not is_db_connected():
        raise HTTPException(503, "DB 연결 필요")

    try:
        list_raw = json.loads(tasks_json)
        if not isinstance(list_raw, list):
            raise ValueError("tasks_json must be a JSON array")
    except Exception as e:
        raise HTTPException(400, f"잘못된 tasks_json: {e}")

    set_allowed_models = {"HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC"}
    list_clean = []
    for dict_t in list_raw:
        if not isinstance(dict_t, dict):
            continue
        str_model = str(dict_t.get("model", "")).strip()
        str_variant = str(dict_t.get("variant", "")).strip()
        if str_model not in set_allowed_models or not str_variant:
            continue
        dict_entry = {"model": str_model, "variant": str_variant}
        if str_model == "VS-IHC":
            try:
                float_mpp = float(dict_t.get("target_mpp", 2.0))
            except (TypeError, ValueError):
                float_mpp = 2.0
            dict_entry["target_mpp"] = float_mpp
        list_clean.append(dict_entry)

    db = get_db()
    str_norm = _norm_folder_path(path)
    dt_now = datetime.now(timezone.utc)
    await db.folder_ai_configs.update_one(
        {"str_rel_path": str_norm},
        {
            "$set": {
                "bool_enabled": bool(enabled),
                "list_tasks": list_clean,
                "dt_updated_at": dt_now,
            },
            "$setOnInsert": {
                "str_rel_path": str_norm,
                "dt_created_at": dt_now,
            },
        },
        upsert=True,
    )
    return {"status": "saved", "path": str_norm, "enabled": enabled, "tasks": list_clean}


@router.delete("/folder-config")
async def delete_folder_config(path: str = Query("")):
    """폴더의 AI 자동 추론 설정 삭제."""
    if not is_db_connected():
        raise HTTPException(503, "DB 연결 필요")
    db = get_db()
    str_norm = _norm_folder_path(path)
    await db.folder_ai_configs.delete_one({"str_rel_path": str_norm})
    return {"status": "deleted", "path": str_norm}


@router.delete("/{slide_id}")
async def close_slide(slide_id: str):
    """슬라이드 닫기"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")

    slide_manager.close(slide_id)
    return {"status": "closed", "slide_id": slide_id}


# ── Annotation 저장/불러오기 ──

@router.post("/{slide_id}/annotations/save")
async def save_annotations(slide_id: str, data: str = Form(...)):
    """슬라이드별 annotation JSON 저장"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    ann_path = tile_generator.get_tiles_dir(filename) / "annotations.json"
    ann_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ann_path, "w", encoding="utf-8") as f:
        f.write(data)
    return {"status": "saved", "count": len(json.loads(data))}


@router.get("/{slide_id}/annotations/load")
async def load_annotations(slide_id: str):
    """슬라이드별 annotation JSON 불러오기"""
    info = slide_manager.get(slide_id)
    if not info:
        raise HTTPException(404, "슬라이드를 찾을 수 없습니다")
    filename = Path(info.file_path).name
    ann_path = tile_generator.get_tiles_dir(filename) / "annotations.json"
    if not ann_path.exists():
        return []
    with open(ann_path, "r", encoding="utf-8") as f:
        return json.loads(f.read())
