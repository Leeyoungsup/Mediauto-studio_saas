import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import pytest
from app import assistance_spatial_index as spatial


def label(x,y,cls='0'):
    return [x-2,y-2,4,4,x,y,cls,.8]


def fixture(tmp_path,labels):
    path=tmp_path/'WSI_Labeling_assistance.json'
    payload={'labels':labels,'total_labels':len(labels),'classes':[],'label_format':'bbox_compact_v1'}
    path.write_text(json.dumps(payload));return path,payload


def test_patch_matches_half_open_boundaries_and_preserves_original_ids(tmp_path):
    labels=[label(-1,0),label(0,0),label(99.9999999,50),label(100,50),label(50,100),label(50,-.01),label(50,50)]
    path,payload=fixture(tmp_path,labels)
    patch={'int_x':0,'int_y':0,'int_w':100,'int_h':100}
    meta,rows=spatial.read(path,lambda:payload,patch)
    assert rows==[(i,l) for i,l in enumerate(labels,1) if 0<=l[4]<100 and 0<=l[5]<100]
    assert meta['total_labels']==len(labels)
    assert 'labels' not in meta


def test_warm_patch_and_metadata_reads_never_load_source_json(tmp_path,monkeypatch):
    path,payload=fixture(tmp_path,[label(i,i) for i in range(10000)])
    spatial.prepare(path,payload,spatial.signature(path))
    original=Path.open
    def guarded(self,*a,**kw):
        assert self!=path,'Full JSON should not be opened for a warm lookup'
        return original(self,*a,**kw)
    monkeypatch.setattr(Path,'open',guarded)
    def forbidden(): pytest.fail('loader must not run')
    meta,rows=spatial.read(path,forbidden,{'int_x':100,'int_y':100,'int_w':10,'int_h':10})
    assert len(rows)==10 and rows[0][0]==101
    assert spatial.read(path,forbidden)[0]==meta
    assert meta['total_labels']==10000


def test_replacement_corruption_and_missing_source(tmp_path):
    path,payload=fixture(tmp_path,[label(1,1)])
    patch={'int_x':0,'int_y':0,'int_w':10,'int_h':10}
    spatial.read(path,lambda:payload,patch)
    replacement=path.with_suffix('.new');new={**payload,'labels':[label(2,2)]}
    replacement.write_text(json.dumps(new));os.replace(replacement,path)
    assert spatial.read(path,lambda:new,patch)[1][0][1]==label(2,2)
    spatial.index_path(path).write_bytes(b'broken')
    assert spatial.read(path,lambda:new,patch)[1][0][1]==label(2,2)
    path.unlink();assert spatial.read(path,lambda:new,patch)==({},[])


def test_concurrent_requests_only_build_once(tmp_path):
    path,payload=fixture(tmp_path,[label(i,i) for i in range(500)])
    calls=[]
    def load():calls.append(1);return payload
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:spatial.read(path,load),range(4)))
    assert len(calls)==1 and all(result==results[0] for result in results)


def test_loader_normalization_and_old_generation_prepare(tmp_path):
    path,payload=fixture(tmp_path,[label(1,1)])
    old=spatial.signature(path);calls=[]
    def load():
        if not calls:path.write_text(json.dumps({**payload,'normalized':True}))
        calls.append(1);return json.loads(path.read_text())
    assert spatial.read(path,load)[0]['normalized'] is True
    assert len(calls)==2
    assert spatial.prepare(path,payload,old) is False


def test_patch_api_same_cells_as_original_scan(tmp_path,monkeypatch):
    from app.routers import cell_annotation as ca
    labels=[label(-2,4),label(0,0),label(10,10),label(99,99),label(100,100)]
    path,payload=fixture(tmp_path,labels)
    info=SimpleNamespace(file_path='slide.ndpi')
    patch={'int_x':0,'int_y':0,'int_w':100,'int_h':100}
    monkeypatch.setattr(ca,'_existing_assistance_path',lambda _:path)
    monkeypatch.setattr(ca,'_read_assistance_file',lambda _:payload)
    monkeypatch.setattr(ca,'_validate_assistance_payload',lambda _,p:(p,False))
    lookup={'0':{'id':'0','name':'Tumor','color':[255,0,0]}}
    monkeypatch.setattr(ca,'_assistance_class_lookup',lambda *a:lookup)
    monkeypatch.setattr(ca,'_load_cell_classes_for_project',lambda *a:[])
    expected=[cell for i,l in enumerate(labels,1) if (cell:=ca._assistance_label_to_cell(l,patch,i,lookup)) is not None]
    response=json.loads(ca._patch_assistance_response(info,'slide','patch',patch).body)
    assert response['cells']==expected
    assert response['total_labels']==len(labels)
