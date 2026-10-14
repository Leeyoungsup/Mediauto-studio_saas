"""Back up and migrate saved PD-L1(ST) cell labels; default is a dry run.

Run with the deployment environment and PYTHONPATH=backend. --apply writes the
migration. AI inference caches are not relabeled as new-model predictions.
"""
import argparse
import asyncio
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil

from sqlalchemy import select
from app.config import settings
from app.postgres.database import connect_postgres, disconnect_postgres, get_postgres_session
from app.postgres.models import ApplicationDocument
from app.ai_pipelines.scoring import PD_SCORE_CONFIG
from app.project_utils import cell_annotation_classes_for_ai

PROJECT = 'IHC(PD-L1)'
SCHEMA = 'pdl1_flat_5class'
OLD_IDS = {'0':'0', '1':'1', '2':'1', '3':'2', '4':'3', '5':'3', '6':'4', 'other':'4'}
NAMES = {str(k):v for k,v in PD_SCORE_CONFIG['Stomach']['class_names'].items()}
NAME_IDS = {
    'negative epithelial':'0', 'negative tumor(epithelial)':'0',
    'negative lymphocyte':'1', 'negative macrophage':'1', 'negative immune':'1',
    'positive epithelial':'2', 'positive tumor(epithelial)':'2',
    'positive lymphocyte':'3', 'positive macrophage':'3', 'positive immune':'3', 'other':'4',
}


def convert_cell(cell, legacy):
    result = copy.deepcopy(cell)
    old_id = str(cell.get('class_id', ''))
    name = str(cell.get('class_name', '')).strip().lower()
    new_id = NAME_IDS.get(name)
    if new_id is None and not name and legacy:
        new_id = OLD_IDS.get(old_id)
    if new_id is not None:
        result['class_id'] = new_id
        result['class_name'] = NAMES[new_id]
    elif old_id in OLD_IDS and legacy:
        raise ValueError(f'Unrecognized name for legacy class {old_id}: {name}')
    return result


def atomic_json(path, payload):
    temp = path.with_name(path.name + '.flat5.tmp')
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


async def migrate(apply):
    root = Path(settings.CELL_ANNOTATION_DIR).resolve()
    classes_path = root / '_projects' / PROJECT / 'classes.json'
    original_classes = json.loads(classes_path.read_text())
    legacy = any('macrophage' in c['name'].lower() for c in original_classes['classes'])
    custom = [c for c in original_classes['classes'] if c['name'].lower() not in NAME_IDS]
    classes = cell_annotation_classes_for_ai(True, 'quanti_pd_l1_stomach') + custom
    file_changes = []
    def stage(path, before, after):
        if before != after:
            file_changes.append((path, hashlib.sha256(path.read_bytes()).hexdigest(), after))
    stage(classes_path, original_classes, {**original_classes, 'classes':classes})
    db_changes = []
    originals = []
    before_counts, after_counts = Counter(), Counter()
    await connect_postgres()
    backup = None
    installed = []
    committed = False
    try:
        async with get_postgres_session() as session:
            project = (await session.scalars(select(ApplicationDocument).where(
                ApplicationDocument.str_collection == 'project_infos',
                ApplicationDocument.dict_document['str_project_path'].as_string() == PROJECT).with_for_update())).one()
            assert project.dict_document['str_title'] == 'PD-L1(ST)'
            slides = list((await session.scalars(select(ApplicationDocument).where(
                ApplicationDocument.str_collection == 'slides',
                ApplicationDocument.dict_document['str_rel_path'].as_string() == PROJECT))).all())
            slide_ids = [s.dict_document['str_slide_id'] for s in slides]
            patches = list((await session.scalars(select(ApplicationDocument).where(
                ApplicationDocument.str_collection == 'patch_cell_annotations',
                ApplicationDocument.dict_document['str_slide_id'].as_string().in_(slide_ids)).with_for_update())).all())
            for row in patches:
                before = row.dict_document
                after = copy.deepcopy(before)
                after['list_cells'] = [convert_cell(c, legacy) for c in before.get('list_cells', [])]
                for a,b in zip(before.get('list_cells',[]), after['list_cells']):
                    assert {k:v for k,v in a.items() if k not in ('class_id','class_name')} == {k:v for k,v in b.items() if k not in ('class_id','class_name')}
                    before_counts[a.get('class_name','')] += 1
                    after_counts[b.get('class_name','')] += 1
                if after != before:
                    db_changes.append((row,after)); originals.append({'collection':row.str_collection,'id':row.str_id,'document':before})
            project_after = copy.deepcopy(project.dict_document)
            project_after['str_annotation_ai_key'] = 'quanti_pd_l1_stomach'
            project_after['bool_annotation_ai_enabled'] = True
            if project_after != project.dict_document:
                db_changes.append((project,project_after)); originals.append({'collection':project.str_collection,'id':project.str_id,'document':project.dict_document})
            for slide_id in slide_ids:
                directory = root / slide_id
                info = directory / 'info.json'
                if info.exists():
                    before = json.loads(info.read_text());after = {**before, 'classes':classes};stage(info,before,after)
                for path in (directory / 'labels').glob('patch_*.json'):
                    before = json.loads(path.read_text());after = copy.deepcopy(before)
                    after['cells'] = [convert_cell(c,legacy) for c in before.get('cells',[])]
                    stage(path,before,after)
            report = {'project':PROJECT,'schema':SCHEMA,'slides':len(slides),'patch_documents':len(patches),
                      'changed_documents':len(db_changes),'changed_files':len(file_changes),
                      'cells':sum(before_counts.values()),'before_counts':dict(before_counts),'after_counts':dict(after_counts),
                      'custom_classes_preserved':custom,'applied':apply}
            print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
            if not apply or not (db_changes or file_changes):
                return report
            backup = root.parent / 'migration_backups' / ('pdl1-st-flat5-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
            backup.mkdir(parents=True,mode=0o700)
            atomic_json(backup/'database.json',originals)
            for path,digest,after in file_changes:
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'File changed during migration: {path}'
                saved = backup/'files'/path.relative_to(root);saved.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,saved)
            atomic_json(backup/'manifest.json',{**report,'root':str(root),'files':[{'path':str(p.relative_to(root)),'sha256':h} for p,h,_ in file_changes]})
            for row,after in db_changes:
                row.dict_document = after
            await session.flush()
            for path,digest,after in file_changes:
                assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'File changed during migration: {path}'
                installed.append(path)
                atomic_json(path,after)
        committed = True
        (backup/'COMPLETED').write_text('Database transaction committed; label coordinates and workflow metadata preserved.\n')
        print('BACKUP',backup,flush=True)
    except Exception:
        if backup and not committed:
            for path in reversed(installed):
                shutil.copy2(backup/'files'/path.relative_to(root),path)
        raise
    finally:
        await disconnect_postgres()


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true')
    asyncio.run(migrate(parser.parse_args().apply))
