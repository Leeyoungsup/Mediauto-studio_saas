"""Clear AI result caches and Cell Annotation AI assistance files.

Default mode is dry-run. Add --apply to delete files and update MongoDB.

Examples:
    python backend/scripts/clear_ai_and_cell_assistance.py --all
    python backend/scripts/clear_ai_and_cell_assistance.py --all --apply
    python backend/scripts/clear_ai_and_cell_assistance.py --rel-path IHC(PD-L1) --apply
    python backend/scripts/clear_ai_and_cell_assistance.py --slide-stem CODIPAI-STBX-SS-04335-I-PD-22 --apply
    python backend/scripts/clear_ai_and_cell_assistance.py --all --models "Quanti HE,Quanti IHC" --apply
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PATH_BACKEND = Path(__file__).resolve().parent.parent
if str(PATH_BACKEND) not in sys.path:
    sys.path.insert(0, str(PATH_BACKEND))

PATH_CELL_ANNOTATION_ROOT = PATH_BACKEND / "cell_annotation"
LIST_AI_MODEL_KEYS = ["Quanti HE", "Quanti PD-L1", "Quanti IHC", "VS IHC"]
LIST_QUANTI_MODEL_KEYS = ["Quanti HE", "Quanti PD-L1", "Quanti IHC"]
LIST_LEGACY_MODEL_SUBDIRS = ["HE-Fit", "PD-Score", "Precise-IHC", "VS-IHC"]


def _split_csv(value: str) -> list:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _empty_ai_result() -> dict:
    return {
        "bool_has_result": False,
        "list_variants": [],
        "dt_updated_at": None,
    }


def _safe_remove(path: Path, bool_apply: bool) -> bool:
    if not path.exists():
        return False
    if not bool_apply:
        return True
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink()
    return True


def _ai_model_dirs(path_ai_root: Path, list_models: list, bool_include_legacy: bool) -> list:
    list_dirs = [path_ai_root / model for model in list_models]
    if bool_include_legacy:
        list_dirs.extend(path_ai_root / model for model in LIST_LEGACY_MODEL_SUBDIRS)
        list_dirs.append(path_ai_root)
    return list_dirs


def _cleanup_ai_for_stem(path_ai_root: Path, str_stem: str, list_models: list,
                         bool_include_legacy: bool, bool_apply: bool) -> list:
    list_removed = []
    if not path_ai_root.exists():
        return list_removed
    for path_dir in _ai_model_dirs(path_ai_root, list_models, bool_include_legacy):
        if not path_dir.exists() or not path_dir.is_dir():
            continue
        for path_item in path_dir.glob(f"{str_stem}_*"):
            if path_item.resolve() == path_ai_root.resolve():
                continue
            list_removed.append(path_item)
            _safe_remove(path_item, bool_apply)
    return list_removed


def _cleanup_assistance_for_stem(str_stem: str, bool_apply: bool) -> list:
    list_removed = []
    path_slide_dir = PATH_CELL_ANNOTATION_ROOT / str_stem
    path_assistance = path_slide_dir / "WSI_Labeling_assistance.json"
    if path_assistance.exists():
        list_removed.append(path_assistance)
        _safe_remove(path_assistance, bool_apply)
    return list_removed


def _cleanup_user_edit_files(path_ai_root: Path, str_stem: str, list_models: list,
                             bool_all_models: bool, bool_apply: bool) -> list:
    path_user_root = path_ai_root / "user_edits"
    list_removed = []
    if not path_user_root.exists():
        return list_removed
    for path_user_dir in path_user_root.iterdir():
        if not path_user_dir.is_dir():
            continue
        list_mode_dirs = [p for p in path_user_dir.iterdir() if p.is_dir()] if bool_all_models else [
            path_user_dir / model for model in list_models
        ]
        for path_mode_dir in list_mode_dirs:
            if not path_mode_dir.exists() or not path_mode_dir.is_dir():
                continue
            for path_item in path_mode_dir.glob(f"{str_stem}_*"):
                list_removed.append(path_item)
                _safe_remove(path_item, bool_apply)
    return list_removed


def _slide_filter(args) -> dict:
    list_or = []
    list_stems = []
    for value in args.slide_stem or []:
        list_stems.extend(_split_csv(value))
    if list_stems:
        list_or.extend({"str_filename": {"$regex": f"^{re.escape(stem)}\\.", "$options": "i"}} for stem in list_stems)

    list_paths = []
    for value in args.rel_path or []:
        list_paths.extend(_split_csv(value))
    if list_paths:
        list_or.extend({"str_rel_path": path.strip("/").replace("\\", "/")} for path in list_paths)

    if args.all:
        return {}
    if not list_or:
        raise ValueError("Select slides with --all, --slide-stem, or --rel-path.")
    return {"$or": list_or}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clear AI result caches and Cell Annotation AI assistance files.",
    )
    parser.add_argument("--apply", action="store_true", help="Actually delete files and update DB.")
    parser.add_argument("--all", action="store_true", help="Process every slide in MongoDB.")
    parser.add_argument("--slide-stem", action="append", help="Slide stem to process. Can be repeated or comma-separated.")
    parser.add_argument("--rel-path", action="append", help="Slide folder/project relative path. Can be repeated or comma-separated.")
    parser.add_argument(
        "--models",
        default=",".join(LIST_AI_MODEL_KEYS),
        help="Comma-separated AI models to reset. Defaults to all AI models.",
    )
    parser.add_argument("--quanti-only", action="store_true", help="Reset Quanti HE, Quanti PD-L1, and Quanti IHC only.")
    parser.add_argument("--ai-only", action="store_true", help="Clear AI results only.")
    parser.add_argument("--assistance-only", action="store_true", help="Clear Cell Annotation AI assistance only.")
    parser.add_argument("--include-user-edits", action="store_true", help="Also delete saved user AI edit records/files.")
    parser.add_argument("--include-patch-cells", action="store_true", help="Also delete patch_cell_annotations docs for selected slides.")
    args = parser.parse_args()

    if args.ai_only and args.assistance_only:
        print("[clear_ai_and_cell_assistance] choose only one of --ai-only or --assistance-only")
        return 2

    list_models = list(LIST_QUANTI_MODEL_KEYS) if args.quanti_only else _split_csv(args.models)
    list_invalid = [model for model in list_models if model not in LIST_AI_MODEL_KEYS]
    if list_invalid:
        print(f"[clear_ai_and_cell_assistance] invalid models: {list_invalid}")
        print(f"  allowed: {LIST_AI_MODEL_KEYS}")
        return 2

    try:
        dict_filter = _slide_filter(args)
    except ValueError as exc:
        print(f"[clear_ai_and_cell_assistance] {exc}")
        return 2

    bool_apply = bool(args.apply)
    bool_clear_ai = not args.assistance_only
    bool_clear_assistance = not args.ai_only
    bool_all_models = set(list_models) == set(LIST_AI_MODEL_KEYS)

    try:
        from pymongo import MongoClient
        from app.config import settings
    except ModuleNotFoundError as exc:
        print(f"[clear_ai_and_cell_assistance] missing dependency: {exc.name}")
        print("  Run this script with the backend Python environment.")
        return 2

    print(f"[clear_ai_and_cell_assistance] {'LIVE' if bool_apply else 'DRY-RUN'} mode")
    print(f"[clear_ai_and_cell_assistance] MongoDB   : {settings.MONGO_URI}")
    print(f"[clear_ai_and_cell_assistance] DB name   : {settings.MONGO_DB_NAME}")
    print(f"[clear_ai_and_cell_assistance] AI dir    : {settings.AI_RESULTS_DIR}")
    print(f"[clear_ai_and_cell_assistance] Cell dir  : {PATH_CELL_ANNOTATION_ROOT}")
    print(f"[clear_ai_and_cell_assistance] models    : {list_models}")
    print(f"[clear_ai_and_cell_assistance] filter    : {dict_filter or '<all>'}")

    client = MongoClient(settings.MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[settings.MONGO_DB_NAME]
    list_slides = list(db.slides.find(dict_filter))
    print(f"\n[clear_ai_and_cell_assistance] slides matched: {len(list_slides)}")

    path_ai_root = Path(settings.AI_RESULTS_DIR)
    int_ai_items = 0
    int_assistance_files = 0
    int_slide_db_updates = 0
    int_user_edits = 0
    int_user_edit_files = 0
    int_patch_cells = 0

    for dict_slide in list_slides:
        str_filename = dict_slide.get("str_filename", "")
        str_slide_id = dict_slide.get("str_slide_id", "")
        str_rel_path = dict_slide.get("str_rel_path", "")
        str_stem = Path(str_filename).stem
        print(f"\n  * {str_rel_path}/{str_filename} (slide_id={str_slide_id})")

        if bool_clear_ai:
            list_removed_ai = _cleanup_ai_for_stem(
                path_ai_root,
                str_stem,
                list_models,
                bool_include_legacy=bool_all_models,
                bool_apply=bool_apply,
            )
            int_ai_items += len(list_removed_ai)
            print(f"      - ai_results: {len(list_removed_ai)} item(s)")
            for path_item in list_removed_ai[:5]:
                print(f"          {path_item}")
            if len(list_removed_ai) > 5:
                print(f"          ... (+{len(list_removed_ai) - 5} more)")

            if bool_apply:
                dict_set = {
                    f"dict_ai_results.{model}": _empty_ai_result()
                    for model in list_models
                }
                dict_set["dt_updated_at"] = datetime.now(timezone.utc)
                db.slides.update_one({"_id": dict_slide["_id"]}, {"$set": dict_set})
            int_slide_db_updates += 1

        if bool_clear_assistance:
            list_removed_assist = _cleanup_assistance_for_stem(str_stem, bool_apply)
            int_assistance_files += len(list_removed_assist)
            print(f"      - cell assistance: {len(list_removed_assist)} file(s)")
            for path_item in list_removed_assist:
                print(f"          {path_item}")

        if args.include_user_edits and str_slide_id:
            query = {"str_slide_id": str_slide_id}
            if not bool_all_models:
                query["str_ai_mode"] = {"$in": list_models}
            if bool_apply:
                int_deleted = db.user_ai_edits.delete_many(query).deleted_count
            else:
                int_deleted = db.user_ai_edits.count_documents(query)
            int_user_edits += int_deleted
            print(f"      - user_ai_edits: {int_deleted} doc(s)")
            list_removed_user_files = _cleanup_user_edit_files(
                path_ai_root, str_stem, list_models, bool_all_models, bool_apply
            )
            int_user_edit_files += len(list_removed_user_files)
            print(f"      - user_ai_edit files: {len(list_removed_user_files)} file(s)")

        if args.include_patch_cells and str_slide_id:
            query = {"str_slide_id": str_slide_id}
            if bool_apply:
                int_deleted = db.patch_cell_annotations.delete_many(query).deleted_count
            else:
                int_deleted = db.patch_cell_annotations.count_documents(query)
            int_patch_cells += int_deleted
            print(f"      - patch_cell_annotations: {int_deleted} doc(s)")

    print("\n========== summary ==========")
    print(f"  slides processed         : {len(list_slides)}")
    print(f"  ai_results items removed : {int_ai_items}")
    print(f"  assistance files removed : {int_assistance_files}")
    print(f"  DB slide AI resets       : {int_slide_db_updates if bool_clear_ai else 0}")
    print(f"  user_ai_edits removed    : {int_user_edits}")
    print(f"  user edit files removed  : {int_user_edit_files}")
    print(f"  patch cell docs removed  : {int_patch_cells}")
    if not bool_apply:
        print("  DRY-RUN only. Re-run with --apply to delete/update.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
