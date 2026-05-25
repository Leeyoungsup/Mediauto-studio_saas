"""text text AI text text text.

`_create_tissue_mask` text γ=2.0 text text text text AI text text text
text. text text text text text text.

text:
  1. ai_results/{Quanti HE,Quanti PD-L1,Quanti IHC,VS IHC}/<stem>_* text·text
  2. ai_results/<stem>_* text text text
  3. db.slides text dict_ai_results text (text text text, vendor text)
  4. db.user_ai_edits text text text

text text **text text text** — text text text/text text.

text:
    # text text (4text text text)
    python backend/scripts/reset_ai_results.py [--dry-run]

    # text text text (text: Quanti HE text)
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
    """text text text text — text text text text text."""
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
    """list_models text text text text.
    bool_full_legacy=True text ai_results text text <stem>_* text text text
    (text text reset text text text).
    """
    int_removed = 0
    if not path_ai_root.exists():
        return 0
    list_sub_dirs = [path_ai_root / s for s in list_models]
    if bool_full_legacy:
        list_sub_dirs.insert(0, path_ai_root)  # text text text text
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
                print(f"  [WARN] text text ({path_p}): {e}")
    return int_removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--models", default=None,
        help=("text text text text (Quanti HE,Quanti PD-L1,Quanti IHC,VS IHC). "
              "text text text text."),
    )
    args = parser.parse_args()
    bool_dry = args.dry_run

    # text text text text.
    if args.models:
        list_models = [s.strip() for s in args.models.split(",") if s.strip()]
        list_invalid = [m for m in list_models if m not in LIST_AI_MODEL_KEYS]
        if list_invalid:
            print(f"[reset_ai_results] text text text: {list_invalid}")
            print(f"  text: {LIST_AI_MODEL_KEYS}")
            return 2
    else:
        list_models = list(LIST_AI_MODEL_KEYS)
    bool_full_reset = (set(list_models) == set(LIST_AI_MODEL_KEYS))

    print(f"[reset_ai_results] {'DRY-RUN' if bool_dry else 'LIVE'} mode")
    print(f"[reset_ai_results] MongoDB : {settings.MONGO_URI}")
    print(f"[reset_ai_results] DB name : {settings.MONGO_DB_NAME}")
    print(f"[reset_ai_results] AI_DIR  : {settings.AI_RESULTS_DIR}")
    print(f"[reset_ai_results] models  : {list_models}"
          f" {'(text)' if bool_full_reset else '(text)'}")

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[settings.MONGO_DB_NAME]

    list_slides = list(db.slides.find({}))
    print(f"\n[reset_ai_results] text text DB text: {len(list_slides)}text")

    path_ai_root = Path(settings.AI_RESULTS_DIR)
    int_total_files = 0
    int_db_updated = 0

    # text text text DB text text text text text text (text text text text).
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
            print(f"  * {str_rel_path}/{str_filename}  —  {int_removed}text AI text/text")
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
                # text text: text text text text, text text text text.
                db.slides.update_one(
                    {"_id": dict_doc["_id"]},
                    {"$set": {**dict_set_partial,
                              "dt_updated_at": datetime.now(timezone.utc)}},
                )
        int_db_updated += 1

    # user_ai_edits — text text text ai_mode text text, text text text text.
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

        # text text text user_edits/{user_id}/{ai_mode}/ text — text text text.
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
        print("  (DRY-RUN — text text/DB text text text)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
