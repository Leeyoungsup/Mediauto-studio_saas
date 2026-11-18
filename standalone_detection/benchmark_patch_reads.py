"""Compare existing level-0 tiles with direct source reads (no inference).

Run with PYTHONPATH=backend. Uses 100 distinct production-grid patches by default;
never creates tiles. Alternating method order and repeated passes expose warm-up.
"""
import argparse
import json
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from app.ai_pipelines.patch_reader import AIPatchReader
from app.ai_pipelines.tissue_mask import build_valid_patch_list
from app.ai_pipelines.resolution import quanti_patch_size
from app.ai_pipelines.dedup import DETECTION_PATCH_OVERLAP_UM
from app.slide_manager import slide_manager, STAGE_READ_SIZE
from app.thread_slide_pool import drop_thread_slide
from app.tile_generator import get_tiles_dir_for_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('slide', type=Path)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--passes', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.count <= 0 or args.passes <= 0:
        parser.error('count and passes must be positive')
    torch.set_num_threads(4)
    slide_id = 'patch-read-benchmark'
    info = slide_manager.open(slide_id, str(args.slide.resolve()))
    try:
        size = quanti_patch_size(info.mpp)
        reader = AIPatchReader(slide_id, str(args.slide.resolve()), size,
                               icc_transform=info.icc_transform, wait_for_viewer=False)
        # Benchmark the existing tile cropper on other formats without changing
        # production routing: normal NDPI/SVS inference still reads the source.
        reader.level0_tiles = get_tiles_dir_for_path(str(args.slide.resolve())) / '0'
        coords, source = build_valid_patch_list(info.slide, *info.dimensions, size,
            icc_transform=info.icc_transform, mpp=info.mpp,
            overlap_um=DETECTION_PATCH_OVERLAP_UM)
        span = STAGE_READ_SIZE[0]
        def tiles_for(x, y):
            return [reader.level0_tiles / f'{tx}_{ty}.jpeg'
                    for ty in range(y // span, (y + size - 1) // span + 1)
                    for tx in range(x // span, (x + size - 1) // span + 1)]
        eligible = [(x, y) for x, y in coords if all(p.is_file() for p in tiles_for(x, y))]
        if len(eligible) < args.count:
            raise ValueError(f'Only {len(eligible)} fully cached patches; need {args.count}')
        # Spread selection across the existing production grid, no repeated coordinates.
        selected = [eligible[i] for i in np.linspace(0, len(eligible)-1, args.count, dtype=int)]
        details, differences = [], []
        methods = {'cached_tiles': reader._read_philips_tile_tensor, 'direct_source': reader._read_direct_tensor}
        # Prohibit silent cache misses, original-read fallback, or tile generation.
        with patch('app.ai_pipelines.patch_reader.generate_priority_tile_block',
                   side_effect=AssertionError('Benchmark must not generate tiles')), \
             patch.object(reader, '_read_direct_tensor',
                          side_effect=AssertionError('Cached path fell back to source')):
            for repeat in range(args.passes):
                times = {name: [] for name in methods}
                for index, (x, y) in enumerate(selected):
                    outputs = {}
                    order = list(methods) if (index + repeat) % 2 == 0 else list(reversed(methods))
                    for name in order:
                        start = time.perf_counter()
                        tensor = methods[name](x, y)
                        elapsed = time.perf_counter() - start
                        if tensor is None or tuple(tensor.shape) != (3, 512, 512):
                            raise RuntimeError(f'Invalid {name} patch at {(x,y)}')
                        times[name].append(elapsed)
                        outputs[name] = tensor
                    if repeat == 0:
                        delta = (outputs['cached_tiles']-outputs['direct_source']).abs()
                        differences.append({'x': x, 'y': y, 'mae_255': float(delta.mean())*255,
                                            'max_abs_255': float(delta.max())*255})
                    if (index+1) % 25 == 0:
                        print(f'pass {repeat+1}: {index+1}/{args.count}', flush=True)
                summary = {'pass': repeat+1}
                for name, values in times.items():
                    summary[name] = {'total_seconds': sum(values),
                                     'mean_ms': float(np.mean(values))*1000,
                                     'median_ms': float(np.median(values))*1000,
                                     'p95_ms': float(np.percentile(values,95))*1000,
                                     'per_patch_seconds': values}
                summary['speedup_source_over_tiles'] = sum(times['direct_source'])/sum(times['cached_tiles'])
                details.append(summary)
                print(json.dumps({k:v for k,v in summary.items() if k in ('pass','speedup_source_over_tiles')}),flush=True)
        result = {
            'slide': str(args.slide.resolve()), 'dimensions': info.dimensions, 'mpp': info.mpp,
            'source_reader': 'Philips SDK bridge' if reader.is_philips else 'OpenSlide',
            'icc_transform_applied': info.icc_transform is not None,
            'source_patch_size': size, 'model_input_size': 512, 'patch_source': source,
            'count': len(selected), 'passes': args.passes, 'eligible_cached_patches': len(eligible),
            'unique_tile_files': len({p for xy in selected for p in tiles_for(*xy)}),
            'coordinates': selected, 'measurements': details,
            'pixel_difference': {'mean_mae_255': float(np.mean([r['mae_255'] for r in differences])),
                                 'max_abs_255': max(r['max_abs_255'] for r in differences),
                                 'patches': differences},
            'notes': ['100 unique patches by default; same coordinates for both methods.',
                      'Includes read/decode, ICC when applicable, crop/assemble, resize and CPU tensor conversion.',
                      'Excludes slide opening, coordinate selection, pixel comparison, model/GPU inference and NMS.',
                      'Direct reads use Philips SDK for iSyntax, otherwise the normal OpenSlide reader.',
                      'OS/source caches not flushed; first pass includes reader warm-up; later passes are warm.',
                      'No new tiles generated; no added decoded-tile RAM cache.']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('Saved',args.output,flush=True)
    finally:
        drop_thread_slide(slide_id)
        slide_manager.close(slide_id)


if __name__ == '__main__':
    main()
