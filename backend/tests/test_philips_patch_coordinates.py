import numpy as np
from PIL import Image
from app.ai_pipelines import patch_reader as pr


def test_overlapping_philips_patch_uses_exact_requested_origin(tmp_path, monkeypatch):
    span = pr.STAGE_READ_SIZE[0]
    assert span == pr.TILE_SIZE_OUT
    rng = np.random.default_rng(42)
    source = rng.integers(0, 256, (span*2, span*2, 3), dtype=np.uint8)
    for ty in range(2):
        for tx in range(2):
            # Lossless fixtures, irrespective of suffix, to check every pixel.
            Image.fromarray(source[ty*span:(ty+1)*span,tx*span:(tx+1)*span]).save(tmp_path/f'{tx}_{ty}.jpeg', format='PNG')
    reader = pr.AIPatchReader('slide', 'slide.isyntax', span, wait_for_viewer=False)
    reader.level0_tiles = tmp_path
    monkeypatch.setattr(reader, '_to_tensor', lambda im: np.array(im))
    for x,y in [(0,0),(span-40,span-40),(137,253),(span,span)]:
        result = reader._read_philips_tile_tensor(x,y)
        np.testing.assert_array_equal(result,source[y:y+span,x:x+span])
    # Tile coordinates must be independent of the AI patch size.
    reader.image_size = span//2
    np.testing.assert_array_equal(reader._read_philips_tile_tensor(span+37,23),
                                  source[23:23+span//2,span+37:span+37+span//2])


def test_missing_neighbor_falls_back_to_exact_direct_read(tmp_path, monkeypatch):
    span = pr.STAGE_READ_SIZE[0]
    Image.new('RGB',(span,span)).save(tmp_path/'0_0.jpeg')
    reader=pr.AIPatchReader('slide','slide.isyntax',span,wait_for_viewer=False)
    reader.level0_tiles=tmp_path
    monkeypatch.setattr(pr,'generate_priority_tile_block',lambda *args: None)
    calls=[]
    monkeypatch.setattr(reader,'_read_direct_tensor',lambda x,y: calls.append((x,y)) or 'direct')
    assert reader.read_tensor(span-40,0)=='direct'
    assert calls==[(span-40,0)]


def test_old_philips_cache_is_backed_up_and_not_reused(tmp_path):
    import pytest
    from app.ai_pipelines.patch_coordinates import patch_coordinate_metadata, validate_patch_coordinate_cache
    path=tmp_path/'result.json'
    path.write_text('{"cells": [1]}')
    with pytest.raises(ValueError, match='stale Philips patch coordinates'):
        validate_patch_coordinate_cache({},'slide.isyntax',path)
    assert path.read_text()=='{"cells": [1]}'
    assert path.with_name(path.name+'.before-philips-coordinate-v2.bak').read_bytes()==path.read_bytes()
    validate_patch_coordinate_cache(patch_coordinate_metadata('slide.isyntax'),'slide.isyntax',path)
    validate_patch_coordinate_cache({},'slide.ndpi',path)
