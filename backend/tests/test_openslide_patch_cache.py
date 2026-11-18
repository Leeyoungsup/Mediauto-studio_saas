from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from app.ai_pipelines import patch_reader as pr
from app.ai_pipelines.dedup import processing_metadata, cache_has_current_detection_postprocess


def make_reader(tmp_path, monkeypatch, *, size=1114, vendor='generic'):
    slide = SimpleNamespace(properties={'openslide.vendor': vendor}, color_profile=None,
                            read_region=lambda *args: Image.new('RGB', args[2], (100, 150, 200)))
    monkeypatch.setattr(pr, 'get_thread_slide', lambda *args: slide)
    monkeypatch.setattr(pr, 'read_complete_marker', lambda *args: {
        'version': pr.COMPLETE_MARKER_VERSION, 'icc_hash': None})
    monkeypatch.setattr(pr, 'source_signature_matches', lambda *args: True)
    reader = pr.AIPatchReader('id', 'slide.ndpi', size, wait_for_viewer=False)
    reader.level0_tiles = tmp_path
    return reader, slide


def test_nine_tiles_are_cropped_at_exact_origin(tmp_path, monkeypatch):
    reader, _ = make_reader(tmp_path, monkeypatch)
    span = pr.TILE_SIZE_OUT
    rng = np.random.default_rng(3)
    source = rng.integers(0, 256, (span*3, span*3, 3), dtype=np.uint8)
    for y in range(3):
        for x in range(3):
            Image.fromarray(source[y*span:(y+1)*span,x*span:(x+1)*span]).save(
                tmp_path/f'{x}_{y}.jpeg', format='PNG')
    monkeypatch.setattr(reader, '_to_tensor', lambda im: np.array(im))
    monkeypatch.setattr(reader, '_read_direct_tensor', lambda *args: pytest.fail('unexpected direct read'))
    # 1000+1114 exceeds two 1024 tiles on both axes: touches all nine.
    np.testing.assert_array_equal(reader.read_tensor(1000, 1000), source[1000:2114,1000:2114])


@pytest.mark.parametrize('bad', ['missing', 'corrupt', 'wrong_size'])
def test_incomplete_cache_reads_original_without_generating(tmp_path, monkeypatch, bad):
    reader, _ = make_reader(tmp_path, monkeypatch, size=512)
    if bad == 'corrupt':
        (tmp_path/'0_0.jpeg').write_bytes(b'broken')
    elif bad == 'wrong_size':
        Image.new('RGB',(32,32)).save(tmp_path/'0_0.jpeg')
    monkeypatch.setattr(pr, 'generate_priority_tile_block', lambda *args: pytest.fail('must not generate'))
    calls=[]
    monkeypatch.setattr(reader, '_read_direct_tensor', lambda x,y: calls.append((x,y)) or 'original')
    assert reader.read_tensor(50, 60) == 'original'
    assert calls == [(50,60)]


@pytest.mark.parametrize('reason', ['source', 'version', 'missing_marker', 'icc'])
def test_untrusted_cache_is_bypassed(tmp_path, monkeypatch, reason):
    reader, _ = make_reader(tmp_path, monkeypatch)
    if reason == 'source': monkeypatch.setattr(pr,'source_signature_matches',lambda *args: False)
    elif reason == 'version': monkeypatch.setattr(pr,'read_complete_marker',lambda *args: {'version': -1})
    elif reason == 'missing_marker': monkeypatch.setattr(pr,'read_complete_marker',lambda *args: None)
    else: monkeypatch.setattr(pr,'_slide_icc_hash',lambda *args:'changed')
    monkeypatch.setattr(reader,'_read_cached_tile_tensor',lambda *args: pytest.fail('untrusted tile read'))
    monkeypatch.setattr(reader,'_read_direct_tensor',lambda *args:'original')
    assert reader.read_tensor(0,0) == 'original'


def test_ndpi_fallback_and_tiles_use_same_color_transform(tmp_path, monkeypatch):
    reader, slide = make_reader(tmp_path, monkeypatch, size=512, vendor='hamamatsu')
    correct, meta = pr.build_color_corrector(slide)
    assert meta['ndp_applied']
    with Image.new('RGB',(pr.TILE_SIZE_OUT,)*2,(100,150,200)) as raw:
        corrected = correct(raw)
        corrected.save(tmp_path/'0_0.jpeg',format='PNG')
        corrected.close()
    cached = reader.read_tensor(0,0)
    (tmp_path/'0_0.jpeg').unlink()
    direct = reader.read_tensor(0,0)
    np.testing.assert_array_equal(cached.numpy(),direct.numpy())


def test_previous_reader_results_remain_readable_without_reinference():
    payload = processing_metadata()
    assert cache_has_current_detection_postprocess(payload)
    del payload['patch_reader_version']
    assert cache_has_current_detection_postprocess(payload)


def test_base_tiles_not_ndpmatch_variant(tmp_path, monkeypatch):
    monkeypatch.setattr(pr, 'get_tiles_dir_for_path', lambda *args: tmp_path)
    reader = pr.AIPatchReader('id', 'slide.ndpi', 512, wait_for_viewer=False)
    assert reader.level0_tiles == tmp_path/'0'
    (tmp_path/'0').mkdir()
    (tmp_path/'ndpmatch/0').mkdir(parents=True)
    Image.new('RGB',(pr.TILE_SIZE_OUT,)*2,(100,100,100)).save(tmp_path/'0/0_0.jpeg',format='PNG')
    Image.new('RGB',(pr.TILE_SIZE_OUT,)*2,(200,200,200)).save(tmp_path/'ndpmatch/0/0_0.jpeg',format='PNG')
    monkeypatch.setattr(reader,'_has_valid_openslide_tiles',lambda:True)
    monkeypatch.setattr(reader,'_to_tensor',lambda im:np.array(im))
    assert np.all(reader.read_tensor(0,0) == 100)
