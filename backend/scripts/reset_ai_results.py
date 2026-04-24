"""모든 슬라이드의 AI 결과를 전면 초기화한다.

`_create_tissue_mask` 의 γ=2.0 감마 전처리 도입으로 기존 AI 결과가 새 마스크와
불일치. 재추론 유도를 위해 다음을 모두 제거한다.

대상:
  1. ai_results/{HE-Fit,PD-Score,Precise-IHC,VS-IHC}/<stem>_* 파일·폴더
  2. ai_results/<stem>_* 레거시 루트 캐시
  3. db.slides 의 dict_ai_results 초기화 (전 슬라이드 대상, vendor 무관)
  4. db.user_ai_edits 전체 문서 삭제

이 스크립트는 **타일은 건드리지 않는다** — 타일은 색 보정/업로드와 무관.

사용:
    python backend/scripts/reset_ai_results.py [--dry-run]
"""
import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PATH_BACKEND = Path(__file__).resolve().parent.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

from pymongo import MongoClient

from app.config import settings
from app.slide_store import LIST_AI_MODEL_KEYS


LIST_AI_SUBDIRS = list(LIST_AI_MODEL_KEYS)  # ["HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC"]


def _empty_ai_results() -> dict:
    return {
        str_key: {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }
        for str_key in LIST_AI_MODEL_KEYS
    }


def _cleanup_ai_caches_for_stem(path_ai_root: Path, str_stem: str, bool_dry: bool) -> int:
    int_removed = 0
    if not path_ai_root.exists():
        return 0
    list_sub_dirs = [path_ai_root] + [path_ai_root / s for s in LIST_AI_SUBDIRS]
    for path_dir in list_sub_dirs:
        if not path_dir.exists() or not path_dir.is_dir():
            continue
        for path_p in path_dir.glob(f"{str_stem}_*"):
            int_removed += 1
            if bool_dry:
                continue
            try:
                if path_p.is_dir():
                    shutil.rmtree(path_p, ignore_errors=True)
                else:
                    path_p.unlink()
            except Exception as e:
                print(f"  [WARN] 제거 실패 ({path_p}): {e}")
    return int_removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    bool_dry = args.dry_run

    print(f"[reset_ai_results] {'DRY-RUN' if bool_dry else 'LIVE'} mode")
    print(f"[reset_ai_results] MongoDB : {settings.MONGO_URI}")
    print(f"[reset_ai_results] DB name : {settings.MONGO_DB_NAME}")
    print(f"[reset_ai_results] AI_DIR  : {settings.AI_RESULTS_DIR}")

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[settings.MONGO_DB_NAME]

    list_slides = list(db.slides.find({}))
    print(f"\n[reset_ai_results] 대상 슬라이드 DB 문서: {len(list_slides)}개")

    path_ai_root = Path(settings.AI_RESULTS_DIR)
    int_total_files = 0
    int_db_updated = 0

    for dict_doc in list_slides:
        str_filename = dict_doc.get("str_filename", "")
        str_rel_path = dict_doc.get("str_rel_path", "")
        str_stem = Path(str_filename).stem

        int_removed = _cleanup_ai_caches_for_stem(path_ai_root, str_stem, bool_dry)
        if int_removed:
            print(f"  * {str_rel_path}/{str_filename}  —  {int_removed}개 AI 파일/폴더")
            int_total_files += int_removed

        if not bool_dry:
            db.slides.update_one(
                {"_id": dict_doc["_id"]},
                {"$set": {
                    "dict_ai_results": _empty_ai_results(),
                    "dt_updated_at": datetime.now(timezone.utc),
                }},
            )
        int_db_updated += 1

    # user_ai_edits 는 한 번에 전부 제거 (DB + 파일시스템 미러)
    if bool_dry:
        int_edits = db.user_ai_edits.count_documents({})
    else:
        int_edits = db.user_ai_edits.delete_many({}).deleted_count

    path_user_edits_fs = path_ai_root / "user_edits"
    if path_user_edits_fs.exists():
        if bool_dry:
            print(f"  [dry] would delete {path_user_edits_fs}")
        else:
            shutil.rmtree(path_user_edits_fs, ignore_errors=True)

    print("\n───────── summary ─────────")
    print(f"  slides processed         : {len(list_slides)}")
    print(f"  ai_results items removed : {int_total_files}")
    print(f"  DB slides reset          : {int_db_updated}")
    print(f"  user_ai_edits removed    : {int_edits}")
    if bool_dry:
        print("  (DRY-RUN — 실제 삭제/DB 갱신 안 함)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
