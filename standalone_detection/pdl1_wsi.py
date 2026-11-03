"""Fresh WSI inference and CSV-only reader comparison for PD-L1(ST).

Uses the repository backend's tissue, resolution, NMS and CPS implementations.
No persisted AI scores or application result caches are consumed.
"""
from pathlib import Path
import csv
import math
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone
from pdl1_pcc import pearson_pcc, lin_ccc, score_to_grade_code

DEFAULT_COLUMNS = {
    'project': '프로젝트', 'slide': '슬라이드 ID', 'account': '계정 ID',
    'grade': 'CPS Grade', 'reader_seconds': '전문의 판독시간(초)',
    'ai_seconds': 'AI 판독시간(초)', 'tissue_type': '판별 모델',
    'measured_at': '측정 시각(KST)', 'measurement_id': '측정 ID',
}
CPS_GRADES = {'CPS < 1': 0, '1 ≤ CPS < 10': 1, 'CPS ≥ 10': 2}


def load_reader_csvs(folder, columns=None, project='IHC(PD-L1)'):
    """Read KNUCH ZIP's 계정별/<login>/비교결과.csv without its saved AI scores.

    Accept an extracted ZIP root, its 계정별 directory, or one account directory.
    Select the latest CPS/Stomach reading by timestamp and measurement ID, as
    KNUCH comparison_statistics.latest_measurements does. JSON is never read.
    """
    columns = {**DEFAULT_COLUMNS, **(columns or {})}
    root = Path(folder).expanduser().resolve()
    if (root / '계정별').is_dir():
        root = root / '계정별'
    paths = sorted(root.rglob('비교결과.csv'))
    if not paths:
        raise FileNotFoundError(f'KNUCH ZIP의 계정별 폴더를 넣어주세요: {root}')
    records, orders = {}, {}
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            missing = set(columns.values()) - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f'{path}: KNUCH 비교결과 CSV 열 누락 {sorted(missing)}')
            for line, row in enumerate(reader, 2):
                if row[columns['project']].strip() not in (project, 'PD-L1(ST)'):
                    continue
                if row[columns['tissue_type']].strip() != 'Stomach':
                    continue
                record = {k: row[v].strip() for k, v in columns.items()}
                if not record['slide'] or not record['account']:
                    raise ValueError(f'{path}:{line}: 슬라이드/계정 ID 누락')
                label = record['grade']
                if label and label not in CPS_GRADES:
                    raise ValueError(f'{path}:{line}: 알 수 없는 CPS Grade {label!r}')
                record['grade'] = CPS_GRADES.get(label)
                for key in ('reader_seconds', 'ai_seconds'):
                    value = record[key]
                    number = float(value) if value else None
                    if number is not None and (not math.isfinite(number) or number < 0):
                        raise ValueError(f'{path}:{line}: 잘못된 {key}')
                    record[key] = number
                date = record['measured_at']
                try:
                    date = datetime.fromisoformat(date) if date else datetime.min.replace(tzinfo=timezone.utc)
                    date = date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date
                except (TypeError, ValueError):
                    date = datetime.min.replace(tzinfo=timezone.utc)
                order = (date, record['measurement_id'])
                record['project'] = project
                key = (project, record['slide'], record['tissue_type'], record['account'])
                if key not in orders or order > orders[key]:
                    records[key], orders[key] = record, order
                elif order == orders[key] and record != records[key]:
                    raise ValueError(f'{path}:{line}: 동일 측정 ID/시각의 기록이 서로 다릅니다.')
    if not records:
        raise ValueError('PD-L1(ST)/Stomach 기록이 없습니다.')
    return list(records.values())


def project_slide_manifest(project_dir):
    """Resolve current application slide IDs; never guess from a partial filename."""
    from app.slide_identity import slide_cache_key
    root = Path(project_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(root)
    extensions = {'.ndpi', '.svs', '.tif', '.tiff', '.mrxs', '.isyntax', '.scn'}
    return {slide_cache_key(str(p)): p for p in sorted(root.iterdir())
            if p.is_file() and p.suffix.lower() in extensions}


class WSIInference:
    def __init__(self, checkpoint, device='cuda:0'):
        import torch
        from ai.nets import nn
        from app.ai_pipelines.scoring import PD_SCORE_CONFIG
        self.device = torch.device(device)
        if self.device.type == 'cuda' and not torch.cuda.is_available():
            raise RuntimeError('CUDA를 사용할 수 없습니다. GPU가 연결된 커널과 PyTorch CUDA 환경을 확인하세요. CPU로 자동 전환하지 않습니다.')
        self.checkpoint = Path(checkpoint).resolve()
        config = PD_SCORE_CONFIG['Stomach']
        payload = torch.load(str(self.checkpoint), map_location='cpu', weights_only=False)
        names = {int(k): str(v).lower() for k, v in payload.get('class_names', {}).items()}
        expected = {k: v.lower() for k, v in config['checkpoint_class_names'].items()}
        if (payload.get('architecture') != config['checkpoint_architecture'] or
                payload.get('num_classes') != 5 or names != expected):
            raise ValueError('Stomach flat-5 checkpoint/class order mismatch')
        model = nn.yolo_v11_m(5)
        state = payload['model_state_dict']
        dfl = state.get('head.dfl.conv.weight')
        if dfl is not None and dfl.shape[1] != model.head.ch:
            head = model.head
            head.ch = int(dfl.shape[1])
            head.no = head.ch * 4 + head.nc
            head.dfl = nn.DFL(head.ch)
            for seq in head.box:
                old = seq[-1]
                seq[-1] = torch.nn.Conv2d(old.in_channels, 4 * head.ch,
                                         old.kernel_size, old.stride, old.padding)
        model.load_state_dict(state, strict=True)
        self.model = model.to(self.device).eval()

    def predict(self, path, *, batch_size=8, max_patches=None, progress=print):
        """max_patches is a smoke test only: partial slides never get a CPS/Grade."""
        import numpy as np
        import torch
        from uuid import uuid4
        from app.slide_manager import slide_manager
        from app.thread_slide_pool import drop_thread_slide
        from app.ai_pipelines.tissue_mask import build_valid_patch_list
        from app.ai_pipelines.patch_reader import AIPatchReader
        from app.ai_pipelines.resolution import quanti_patch_size, QUANTI_INPUT_SIZE
        from app.ai_pipelines.dedup import (DETECTION_PATCH_OVERLAP_UM,
            patch_edge_keep_mask, apply_global_cell_dedup, processing_metadata)
        from app.ai_pipelines.scoring import compute_pd_score
        from ai.yolo_postprocess import non_max_suppression
        if batch_size < 1 or (max_patches is not None and max_patches < 1):
            raise ValueError('batch_size/max_patches must be positive')
        start = time.perf_counter()
        sid = 'pcc-' + uuid4().hex
        path = Path(path).resolve()
        info = slide_manager.open(sid, str(path))
        try:
            width, height = info.dimensions
            if not math.isfinite(info.mpp) or info.mpp <= 0:
                raise ValueError('Valid slide MPP is required')
            size = quanti_patch_size(info.mpp)
            coords, source = build_valid_patch_list(info.slide, width, height, size,
                icc_transform=info.icc_transform, mpp=info.mpp,
                overlap_um=DETECTION_PATCH_OVERLAP_UM)
            total = len(coords)
            coords = coords if max_patches is None else coords[:max_patches]
            progress(f'{path.name}: {len(coords)}/{total} patches ({source})')
            reader = AIPatchReader(sid, str(path), size, QUANTI_INPUT_SIZE,
                                   info.icc_transform, wait_for_viewer=False)
            chunks = []
            scale = size / QUANTI_INPUT_SIZE
            with torch.inference_mode():
                for offset in range(0, len(coords), batch_size):
                    current = coords[offset:offset + batch_size]
                    batch = torch.stack([reader.read_tensor(x, y) for x, y in current]).to(self.device)
                    with torch.amp.autocast('cuda', enabled=str(self.device).startswith('cuda')):
                        raw = self.model(batch)
                    predictions = non_max_suppression(raw, confidence_threshold=.01,
                        iou_threshold=.3, class_thresholds={i: .01 for i in range(5)},
                        nms_priority_classes=[0, 1, 2, 3])
                    if len(predictions) != len(current):
                        raise RuntimeError('Incomplete prediction batch')
                    for (x, y), detection in zip(current, predictions):
                        det = detection.detach().float().cpu().numpy().copy()
                        det[:, :4] *= scale
                        cx, cy = (det[:, 0] + det[:, 2])/2, (det[:, 1] + det[:, 3])/2
                        keep = patch_edge_keep_mask(cx, cy, x, y, width, height, size, info.mpp)
                        det = det[keep]
                        det[:, [0, 2]] += x
                        det[:, [1, 3]] += y
                        chunks.append(det)
                    progress(f'{min(offset + batch_size, len(coords))}/{len(coords)} patches')
            det = np.concatenate(chunks) if chunks else np.empty((0, 6), dtype=np.float32)
            x0, y0, x1, y1, conf, cls = det.T
            merged = apply_global_cell_dedup((x0+x1)/2, (y0+y1)/2, conf,
                cls.astype(np.int32), x0, y0, x1, y1, info.mpp, list_exclude=[4])
            x, y, conf, cls, x0, y0, x1, y1, dropped = merged
            scored = cls[(conf >= .1) & (cls != 4)]
            score = compute_pd_score(scored, 'Stomach')
            complete = len(coords) == total
            valid = complete and total > 0 and score['viable_tumor'] > 0
            cps = score['score'] if valid else None
            return {'path': str(path), 'complete': complete, 'patch_source': source,
                    'patches_total': total, 'patches_inferred': len(coords),
                    'global_nms_dropped': dropped, 'cells_after_nms': len(cls),
                    'cps': cps, 'grade': score_to_grade_code(cps),
                    'status': 'ok' if valid else 'partial' if not complete else 'no_viable_tumor',
                    'counts': score, 'inference_seconds': time.perf_counter()-start,
                    'checkpoint': str(self.checkpoint), 'device': str(self.device),
                    **processing_metadata()}
        finally:
            drop_thread_slide(sid)
            slide_manager.close(sid)


def compare_readers(records, predictions):
    """Return per-slide pairs, account metrics, majority consensus and metrics."""
    pairs, accounts, slides = [], defaultdict(list), defaultdict(list)
    for record in records:
        result = predictions.get(record['slide'])
        if result is None:
            raise ValueError(f"Missing WSI inference: {record['slide']}")
        if not result['complete']:
            raise ValueError('부분 패치 테스트는 PCC/CCC 계산에 사용할 수 없습니다.')
        row = {**record, 'ai_cps': result['cps'], 'ai_grade': result['grade'],
               'inference_seconds': result['inference_seconds'], 'inference_status': result['status']}
        pairs.append(row)
        accounts[(row['project'], row['account'])].append(row)
        slides[(row['project'], row['slide'])].append(row)
    def metrics(rows, reference='grade'):
        valid = [(r[reference], r['ai_grade']) for r in rows
                 if r[reference] is not None and r['ai_grade'] is not None]
        x, y = [v[0] for v in valid], [v[1] for v in valid]
        pcc, ccc = pearson_pcc(x, y), lin_ccc(x, y)
        return {'slides': len(rows), 'paired': len(valid), 'excluded': len(rows)-len(valid),
                'PCC': pcc, 'CCC': ccc,
                'PCC_status': 'ok' if pcc is not None else 'fewer_than_2_pairs' if len(valid)<2 else 'constant_grade',
                'CCC_status': 'ok' if ccc is not None else 'fewer_than_2_pairs' if len(valid)<2 else 'zero_denominator'}
    summaries = [{'project': p, 'account': a, **metrics(rows)} for (p, a), rows in sorted(accounts.items())]
    consensus = []
    for (project, slide), rows in sorted(slides.items()):
        votes = Counter(r['grade'] for r in rows if r['grade'] is not None)
        count = sum(votes.values())
        winner = next((g for g, n in votes.items() if count >= 2 and n > count/2), None)
        consensus.append({'project': project, 'slide': slide, 'grade': winner,
            'votes': str(dict(votes)), 'ai_grade': rows[0]['ai_grade'],
            'status': 'majority' if winner is not None else 'no_majority'})
    return pairs, summaries, consensus, [metrics(consensus)]
