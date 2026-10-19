"""Background readiness tracking for saved cell patch selections.

The spatial index covers the whole slide. Changing selected patches only needs
range-query preparation, not another model run or a full index rebuild.
"""
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from app import assistance_spatial_index as spatial
from app.config import settings
from app.slide_identity import slide_cache_key

FIELDS = ('str_patch_id', 'int_x', 'int_y', 'int_w', 'int_h')


async def selected_patches(db, slide_id):
    return await db.patch_annotation_status.find(
        {'str_slide_id':slide_id,'str_status':{'$ne':'not_required'}},
        {key:1 for key in FIELDS},
    ).to_list(length=200000)


def selection_signature(patches):
    rows = sorted([str(p.get('str_patch_id','')),
                   *[float(p.get(key,0)) for key in FIELDS[1:]]] for p in patches)
    return hashlib.sha256(json.dumps(rows,separators=(',',':')).encode()).hexdigest()


def source_path(full_path):
    return Path(settings.CELL_ANNOTATION_DIR)/slide_cache_key(full_path)/'WSI_Labeling_assistance.json'


def readiness_state(full_path, patches, config):
    source = source_path(full_path)
    return {'version':spatial.VERSION,'selection':selection_signature(patches),
            'source':spatial.signature(source),'index':spatial.signature(spatial.index_path(source)),
            'slide':spatial.signature(Path(full_path)),'ai_key':config['key']}


def needs_preparation(full_path, patches, config):
    if not patches:
        return False
    try:
        current=readiness_state(full_path,patches,config)
        stored=json.loads(source_path(full_path).with_suffix('.prepared.json').read_text())
        return stored != current or spatial._query(source_path(full_path),None) is None
    except (OSError,ValueError,TypeError,KeyError):
        return True


def prepare_selection(full_path, patches):
    from app.routers.cell_annotation import _read_indexed_assistance
    info=SimpleNamespace(file_path=full_path)
    slide_before=spatial.signature(Path(full_path))
    meta,_=_read_indexed_assistance(info)
    if not meta:
        raise ValueError('Current assistance result is not available for indexing')
    source_before=spatial.signature(source_path(full_path))
    for patch in patches:
        meta,_=_read_indexed_assistance(info,patch)
        if not meta:
            raise ValueError('Assistance result changed during patch preparation')
    if spatial.signature(source_path(full_path)) != source_before:
        raise ValueError('Assistance result changed during patch preparation')
    return {"source":source_before,"slide":slide_before}


def record_prepared(full_path,patches,config,expected_source):
    state=readiness_state(full_path,patches,config)
    if state['source'] != expected_source['source'] or state['slide'] != expected_source['slide']:
        return False
    path=source_path(full_path).with_suffix('.prepared.json')
    temporary=path.with_suffix('.json.tmp')
    try:
        temporary.write_text(json.dumps(state,separators=(',',':')))
        os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
