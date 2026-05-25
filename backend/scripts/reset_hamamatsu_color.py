"""Hamamatsu text text / AI text / DB text text.

slide_manager.py text NDP.view2 text text LUT text text text, text raw text
text text JPEG text AI text text text text text text text text
text text.

text:
- `db.slides` text `str_vendor` text "hamamatsu" (text text) text text
  - text: tiles/<stem>/ text + ai_results/{Quanti HE,Quanti PD-L1,Quanti IHC,VS IHC}/<stem>_* + ai_results/<stem>_* (text)
  - DB text: bool_tiles_ready=False, dt_tiles_ready_at=None, dict_ai_results text
- `db.user_ai_edits` text text slide_id text text text

text:
    python backend/scripts/reset_hamamatsu_color.py [--dry-run]

text text text. `--dry-run` text text text text.
"""
import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# backend/ text import path text text app.* text text text text text
PATH_BACKEND = Path(__file__).resolve().parent.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

from pymongo import MongoClient

# app.config / app.slide_store text text text
from app.config import settings
from app.slide_store import LIST_AI_MODEL_KEYS


LIST_AI_SUBDIRS = list(LIST_AI_MODEL_KEYS)  # ["Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"]


def _empty_ai_results() -> dict:
    return {
        str_key: {
            "bool_has_result": False,
            "list_variants": [],
            "dt_updated_at": None,
        }
        for str_key in LIST_AI_MODEL_KEYS
    }


def _cleanup_ai_caches_for_stem(path_ai_root: Path, str_stem: str, bool_dry: bool) -> list:
    """text slide stem text AI text text/VS text text text."""
    list_removed = []
    if not path_ai_root.exists():
        return list_removed
    list_sub_dirs = [path_ai_root] + [path_ai_root / s for s in LIST_AI_SUBDIRS]
    for path_dir in list_sub_dirs:
        if not path_dir.exists() or not path_dir.is_dir():
            continue
        for path_p in path_dir.glob(f"{str_stem}_*"):
            list_removed.append(str(path_p))
            if bool_dry:
                continue
            try:
                if path_p.is_dir():
                    shutil.rmtree(path_p, ignore_errors=True)
                else:
                    path_p.unlink()
            except Exception as e:
                print(f"  [WARN] AI cache text text ({path_p}): {e}")
    return list_removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="text text, text text X")
    args = parser.parse_args()
    bool_dry = args.dry_run

    print(f"[reset_hamamatsu_color] {'DRY-RUN' if bool_dry else 'LIVE'} mode")
    print(f"[reset_hamamatsu_color] MongoDB : {settings.MONGO_URI}")
    print(f"[reset_hamamatsu_color] DB name : {settings.MONGO_DB_NAME}")
    print(f"[reset_hamamatsu_color] TILES   : {settings.TILES_DIR}")
    print(f"[reset_hamamatsu_color] AI_DIR  : {settings.AI_RESULTS_DIR}")

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")  # text text
    db = client[settings.MONGO_DB_NAME]

    # text text vendor=hamamatsu text
    dict_filter = {"str_vendor": {"$regex": "^hamamatsu$", "$options": "i"}}
    list_slides = list(db.slides.find(dict_filter))
    print(f"\n[reset_hamamatsu_color] Hamamatsu text DB text: {len(list_slides)}text")

    if not list_slides:
        print("[reset_hamamatsu_color] text text — text")
        return 0

    path_tiles_root = Path(settings.TILES_DIR)
    path_ai_root = Path(settings.AI_RESULTS_DIR)

    int_tiles_removed = 0
    int_ai_removed = 0
    int_db_updated = 0
    int_edits_removed = 0

    for dict_doc in list_slides:
        str_filename = dict_doc.get("str_filename", "")
        str_slide_id = dict_doc.get("str_slide_id", "")
        str_rel_path = dict_doc.get("str_rel_path", "")
        str_stem = Path(str_filename).stem

        print(f"\n  *{str_rel_path}/{str_filename}  (slide_id={str_slide_id})")

        # 1) text text text — tiles/<stem>/
        path_tiles_dir = path_tiles_root / str_stem
        if path_tiles_dir.exists():
            print(f"      - tiles: {path_tiles_dir}")
            if not bool_dry:
                shutil.rmtree(path_tiles_dir, ignore_errors=True)
            int_tiles_removed += 1
        else:
            print(f"      - tiles: (text)")

        # 2) AI text text text
        list_ai = _cleanup_ai_caches_for_stem(path_ai_root, str_stem, bool_dry)
        if list_ai:
            print(f"      - ai_results: {len(list_ai)}text text/text")
            for str_p in list_ai[:3]:
                print(f"          -{str_p}")
            if len(list_ai) > 3:
                print(f"          -... (+{len(list_ai)-3} more)")
            int_ai_removed += len(list_ai)
        else:
            print(f"      - ai_results: (text)")

        # 3) DB text text
        dict_reset = {
            "$set": {
                "bool_tiles_ready": False,
                "dt_tiles_ready_at": None,
                "dict_ai_results": _empty_ai_results(),
                "dt_updated_at": datetime.now(timezone.utc),
            }
        }
        if bool_dry:
            print(f"      - DB reset: (dry-run)")
        else:
            db.slides.update_one({"_id": dict_doc["_id"]}, dict_reset)
            print(f"      - DB reset: tiles_ready=False, ai_results cleared")
        int_db_updated += 1

        # 4) user_ai_edits text (text text text text)
        if str_slide_id:
            if bool_dry:
                int_count = db.user_ai_edits.count_documents({"str_slide_id": str_slide_id})
                if int_count:
                    print(f"      - user_ai_edits: {int_count}text (dry-run)")
                int_edits_removed += int_count
            else:
                result = db.user_ai_edits.delete_many({"str_slide_id": str_slide_id})
                if result.deleted_count:
                    print(f"      - user_ai_edits: {result.deleted_count}text text")
                int_edits_removed += result.deleted_count

    print("\n───────── summary ─────────")
    print(f"  slides processed         : {len(list_slides)}")
    print(f"  tile dirs removed        : {int_tiles_removed}")
    print(f"  ai_results items removed : {int_ai_removed}")
    print(f"  DB slides reset          : {int_db_updated}")
    print(f"  user_ai_edits removed    : {int_edits_removed}")
    if bool_dry:
        print("  (DRY-RUN — text text/DB text text text)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
