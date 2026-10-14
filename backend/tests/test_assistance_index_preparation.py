import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from app import assistance_index_preparation as prep, assistance_spatial_index as spatial
from app import auto_ai
from app.config import settings


def setup_source(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,'CELL_ANNOTATION_DIR',str(tmp_path/'patches'))
    slide=tmp_path/'slide.ndpi';slide.write_bytes(b'slide')
    source=prep.source_path(str(slide));source.parent.mkdir(parents=True)
    payload={'labels':[[0,0,10,10,5,5,'0',.9]],'total_labels':1}
    source.write_text(json.dumps(payload));spatial.prepare(source,payload,spatial.signature(source))
    patches=[{'str_patch_id':'patch_1','int_x':0,'int_y':0,'int_w':10,'int_h':10}]
    return str(slide),source,payload,patches,{'key':'quanti_pd_l1_stomach'}


def test_readiness_detects_patch_source_and_index_changes(tmp_path,monkeypatch):
    slide,source,payload,patches,config=setup_source(tmp_path,monkeypatch)
    assert prep.needs_preparation(slide,patches,config)
    expected={'source':spatial.signature(source),'slide':spatial.signature(__import__('pathlib').Path(slide))}
    assert prep.record_prepared(slide,patches,config,expected)
    assert not prep.needs_preparation(slide,patches,config)
    # Workflow status changes don't invalidate spatial geometry.
    assert not prep.needs_preparation(slide,[{**patches[0],'str_status':'completed'}],config)
    assert prep.needs_preparation(slide,[{**patches[0],'int_x':11}],config)
    assert prep.needs_preparation(slide,patches+[dict(patches[0],str_patch_id='patch_2')],config)
    assert not prep.needs_preparation(slide,[],config)
    assert prep.needs_preparation(slide,patches,{'key':'other_model'})
    source.write_text(json.dumps({**payload,'updated':True}))
    assert prep.needs_preparation(slide,patches,config)
    assert not prep.record_prepared(slide,patches,config,expected)


def test_selection_change_reuses_whole_slide_index(tmp_path,monkeypatch):
    from app.routers import cell_annotation as ca
    slide,source,payload,patches,config=setup_source(tmp_path,monkeypatch)
    original_index=spatial.signature(spatial.index_path(source))
    monkeypatch.setattr(ca,'_read_indexed_assistance',lambda info,patch=None:spatial.read(source,lambda:(_ for _ in ()).throw(AssertionError('must not load whole JSON')),patch))
    expected=prep.prepare_selection(slide,patches)
    assert prep.record_prepared(slide,patches,config,expected)
    changed=[{**patches[0],'int_x':100}]
    assert prep.needs_preparation(slide,changed,config)
    expected=prep.prepare_selection(slide,changed)
    assert prep.record_prepared(slide,changed,config,expected)
    assert spatial.signature(spatial.index_path(source))==original_index
    assert not prep.needs_preparation(slide,changed,config)
    spatial.index_path(source).unlink()
    assert prep.needs_preparation(slide,changed,config)


def test_worker_index_task_does_not_infer_and_rechecks_selection(monkeypatch):
    from app.ai_pipelines import task_state
    initial=[{'str_patch_id':'p','int_x':0,'int_y':0,'int_w':10,'int_h':10}]
    changed=[{**initial[0],'int_x':10}]
    monkeypatch.setattr(prep,'selected_patches',AsyncMock(side_effect=[initial,changed]))
    prepared=[]
    monkeypatch.setattr(prep,'prepare_selection',lambda path,patches:prepared.append(patches) or {'source':[1],'slide':[2]})
    record=__import__('unittest.mock',fromlist=['Mock']).Mock()
    monkeypatch.setattr(prep,'record_prepared',record)
    monkeypatch.setattr(auto_ai,'check_idle_and_reserve',lambda *args:True)
    inference=AsyncMock();monkeypatch.setattr(auto_ai,'_run_auto_inference',inference)
    updates=[];monkeypatch.setattr(task_state,'update_task',lambda task,**kw:updates.append(kw))
    asyncio.run(auto_ai._run_auto_assistance_index_prepare(object(),{'str_full_path':'/tmp/a.ndpi','str_slide_id':'slide'},{'key':'model'}))
    assert prepared==[initial] and not record.called and not inference.called
    assert updates[-1]['status']=='completed' and 'changed' in updates[-1]['status_msg']


def test_worker_prepares_fresh_assistance_instead_of_inferring(tmp_path,monkeypatch):
    from app import database,slide_store
    slide=tmp_path/'a.ndpi';slide.touch()
    doc={'str_full_path':str(slide),'str_rel_path':'project','str_slide_id':'slide','bool_tiles_ready':True}
    class Collection:
        def __init__(self,items):self.items=items
        async def find(self,*args):
            for item in self.items:yield item
    db=SimpleNamespace(folder_ai_configs=Collection([]),project_infos=Collection([{'str_project_path':'project','bool_annotation_ai_enabled':True,'str_annotation_ai_key':'quanti_pd_l1_stomach'}]),slides=Collection([doc]))
    monkeypatch.setattr(database,'is_db_connected',lambda:True);monkeypatch.setattr(database,'get_db',lambda:db)
    monkeypatch.setattr(slide_store,'repair_folder_ai_config_paths',AsyncMock(return_value=0))
    monkeypatch.setattr(slide_store,'list_slides_in_folder',AsyncMock(return_value={'a':doc}))
    monkeypatch.setattr(auto_ai,'is_system_idle',lambda:True)
    monkeypatch.setattr(auto_ai,'_should_yield_for_active_tile_generation',AsyncMock(return_value=False))
    monkeypatch.setattr(auto_ai,'_should_defer_slide_for_pending_tiles',AsyncMock(return_value=False))
    monkeypatch.setattr(auto_ai,'_assistance_needs_refresh',lambda *args:False)
    monkeypatch.setattr(auto_ai,'_selected_assistance_index_work',AsyncMock(return_value={**doc,'_index_patches':[{}]}))
    prepare=AsyncMock();inference=AsyncMock()
    monkeypatch.setattr(auto_ai,'_run_auto_assistance_index_prepare',prepare)
    monkeypatch.setattr(auto_ai,'_run_auto_inference',inference)
    asyncio.run(auto_ai._scan_and_infer_once())
    assert prepare.await_count==1 and inference.await_count==0


def test_original_slide_change_invalidates_memoized_marker_cache(tmp_path,monkeypatch):
    slide=tmp_path/'source.ndpi';slide.write_bytes(b'original')
    cache=tmp_path/'cache.json';cache.write_text('{}')
    monkeypatch.setattr(auto_ai,'_marker_cache_path',lambda *args:cache)
    monkeypatch.setattr(auto_ai,'_expected_marker_model_runtime',lambda *args:None)
    monkeypatch.setattr(auto_ai,'_marker_cache_requires_excluded_cells',lambda *args:False)
    monkeypatch.setattr(auto_ai,'cache_has_current_detection_postprocess',lambda *args:True)
    stat=slide.stat()
    monkeypatch.setattr(auto_ai,'_read_marker_cache_metadata',lambda *args:{'source':{'filename':slide.name,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns},'has_cells':False})
    assert not auto_ai._marker_cache_needs_refresh(str(slide),'Quanti PD-L1','Stomach')
    slide.write_bytes(b'replaced source')
    assert auto_ai._marker_cache_needs_refresh(str(slide),'Quanti PD-L1','Stomach')
