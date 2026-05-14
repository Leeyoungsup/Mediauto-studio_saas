"""모든 슬라이드의 AI 결과를 전면 초기화한다.

`_create_tissue_mask` 의 γ=2.0 감마 전처리 도입으로 기존 AI 결과가 새 마스크와
불일치. 재추론 유도를 위해 다음을 모두 제거한다.

대상:
  1. ai_results/{Quanti HE,Quanti PD-L1,Quanti IHC,VS IHC}/<stem>_* 파일·폴더
  2. ai_results/<stem>_* 레거시 루트 캐시
  3. db.slides 의 dict_ai_results 초기화 (전 슬라이드 대상, vendor 무관)
  4. db.user_ai_edits 전체 문서 삭제

이 스크립트는 **타일은 건드리지 않는다** — 타일은 색 보정/업로드와 무관.

사용:
    # 전체 리셋 (4개 모델 모두)
    python backend/scripts/reset_ai_results.py [--dry-run]

    # 특정 모델만 리셋 (예: Quanti HE 만)
    python backend/scripts/reset_ai_results.py --models Quanti HE [--dry-run]
    python backend/scripts/reset_ai_results.py --models Quanti HE,Quanti PD-L1
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


LIST_AI_SUBDIRS = list(LIST_AI_MODEL_KEYS)  # ["Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"]


def _empty_ai_results_for(list_models) -> dict:
    """선택한 모델만 빈 상태로 — 나머지 모델 결과는 건드리지 않음."""
    return {
        str_key: {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }
        for str_key in list_models
    }


def _cleanup_ai_caches_for_stem(path_ai_root: Path, str_stem: str,
                                  list_models, bool_full_legacy: bool,
                                  bool_dry: bool) -> int:
    """list_models 에 해당하는 서브디렉토리만 정리.
    bool_full_legacy=True 면 ai_results 루트의 레거시 <stem>_* 파일도 같이 제거
    (전체 모델 reset 일 때만 안전).
    """
    int_removed = 0
    if not path_ai_root.exists():
        return 0
    list_sub_dirs = [path_ai_root / s for s in list_models]
    if bool_full_legacy:
        list_sub_dirs.insert(0, path_ai_root)  # 루트 레거시 캐시도 같이
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
    parser.add_argument(
        "--models", default=None,
        help=("쉼표로 구분된 모델 키 (Quanti HE,Quanti PD-L1,Quanti IHC,VS IHC). "
              "지정하지 않으면 전체 리셋."),
    )
    args = parser.parse_args()
    bool_dry = args.dry_run

    # 어떤 모델을 리셋할지 결정.
    if args.models:
        list_models = [s.strip() for s in args.models.split(",") if s.strip()]
        list_invalid = [m for m in list_models if m not in LIST_AI_MODEL_KEYS]
        if list_invalid:
            print(f"[reset_ai_results] 잘못된 모델 키: {list_invalid}")
            print(f"  허용: {LIST_AI_MODEL_KEYS}")
            return 2
    else:
        list_models = list(LIST_AI_MODEL_KEYS)
    bool_full_reset = (set(list_models) == set(LIST_AI_MODEL_KEYS))

    print(f"[reset_ai_results] {'DRY-RUN' if bool_dry else 'LIVE'} mode")
    print(f"[reset_ai_results] MongoDB : {settings.MONGO_URI}")
    print(f"[reset_ai_results] DB name : {settings.MONGO_DB_NAME}")
    print(f"[reset_ai_results] AI_DIR  : {settings.AI_RESULTS_DIR}")
    print(f"[reset_ai_results] models  : {list_models}"
          f" {'(전체)' if bool_full_reset else '(부분)'}")

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[settings.MONGO_DB_NAME]

    list_slides = list(db.slides.find({}))
    print(f"\n[reset_ai_results] 대상 슬라이드 DB 문서: {len(list_slides)}개")

    path_ai_root = Path(settings.AI_RESULTS_DIR)
    int_total_files = 0
    int_db_updated = 0

    # 부분 리셋 시 DB 업데이트는 선택한 모델 키만 명시적으로 비움 (다른 모델 결과는 보존).
    dict_set_partial = {}
    for str_key in list_models:
        dict_set_partial[f"dict_ai_results.{str_key}"] = {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }

    for dict_doc in list_slides:
        str_filename = dict_doc.get("str_filename", "")
        str_rel_path = dict_doc.get("str_rel_path", "")
        str_stem = Path(str_filename).stem

        int_removed = _cleanup_ai_caches_for_stem(
            path_ai_root, str_stem, list_models, bool_full_reset, bool_dry,
        )
        if int_removed:
            print(f"  * {str_rel_path}/{str_filename}  —  {int_removed}개 AI 파일/폴더")
            int_total_files += int_removed

        if not bool_dry:
            if bool_full_reset:
                db.slides.update_one(
                    {"_id": dict_doc["_id"]},
                    {"$set": {
                        "dict_ai_results": _empty_ai_results_for(LIST_AI_MODEL_KEYS),
                        "dt_updated_at": datetime.now(timezone.utc),
                    }},
                )
            else:
                # 부분 리셋: 선택한 모델 키만 덮어씀, 나머지 모델 결과는 그대로.
                db.slides.update_one(
                    {"_id": dict_doc["_id"]},
                    {"$set": {**dict_set_partial,
                              "dt_updated_at": datetime.now(timezone.utc)}},
                )
        int_db_updated += 1

    # user_ai_edits — 부분 리셋이면 해당 ai_mode 만 삭제, 전체 리셋이면 컬렉션 통째로.
    if bool_full_reset:
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
    else:
        if bool_dry:
            int_edits = db.user_ai_edits.count_documents(
                {"str_ai_mode": {"$in": list_models}}
            )
        else:
            int_edits = db.user_ai_edits.delete_many(
                {"str_ai_mode": {"$in": list_models}}
            ).deleted_count

        # 사용자 편집본 폴더는 user_edits/{user_id}/{ai_mode}/ 구조 — 선택 모델만 정리.
        path_user_edits_fs = path_ai_root / "user_edits"
        if path_user_edits_fs.exists():
            for path_user_dir in path_user_edits_fs.iterdir():
                if not path_user_dir.is_dir():
                    continue
                for str_model in list_models:
                    path_mode_dir = path_user_dir / str_model
                    if not path_mode_dir.exists():
                        continue
                    if bool_dry:
                        print(f"  [dry] would delete {path_mode_dir}")
                    else:
                        shutil.rmtree(path_mode_dir, ignore_errors=True)

    print("\n───────── summary ─────────")
    print(f"  models                   : {list_models}")
    print(f"  slides processed         : {len(list_slides)}")
    print(f"  ai_results items removed : {int_total_files}")
    print(f"  DB slides reset          : {int_db_updated}")
    print(f"  user_ai_edits removed    : {int_edits}")
    if bool_dry:
        print("  (DRY-RUN — 실제 삭제/DB 갱신 안 함)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
