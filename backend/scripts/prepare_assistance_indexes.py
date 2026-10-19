"""Prepare existing assistance spatial indexes without running AI inference."""
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from time import perf_counter
from app.config import settings
from app.database import get_db
from app.postgres.database import connect_postgres,disconnect_postgres
from app.routers.cell_annotation import _read_indexed_assistance

async def main(project,limit):
    await connect_postgres()
    try:
        slides=await get_db().slides.find({'str_rel_path':project}).to_list(length=100000)
        candidates=[]
        for slide in slides:
            path=Path(settings.CELL_ANNOTATION_DIR)/slide['str_slide_id']/'WSI_Labeling_assistance.json'
            if path.exists():candidates.append((path.stat().st_size,slide,path))
        candidates.sort(key=lambda x:x[0],reverse=True)
        if limit:candidates=candidates[:limit]
        for size,slide,path in candidates:
            start=perf_counter()
            metadata,_=await asyncio.to_thread(_read_indexed_assistance,SimpleNamespace(file_path=slide['str_full_path']))
            print(json.dumps({'slide_id':slide['str_slide_id'],'source_mb':round(size/1048576,1),
                'indexed':bool(metadata),'labels':metadata.get('total_labels',0),'seconds':round(perf_counter()-start,3)}),flush=True)
    finally:
        await disconnect_postgres()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--project',required=True);parser.add_argument('--limit',type=int,default=0)
    args=parser.parse_args();asyncio.run(main(args.project,args.limit))
