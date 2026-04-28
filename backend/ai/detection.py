"""
병변 검출 (Lesion Detection) 모듈 — 공용 유틸.

SaaS 백엔드(`app/routers/ai.py`) 가 import 하는 세 가지만 유지:
  - CLASS_NAMES / CLASS_COLORS (HE 세포 클래스 메타)
  - non_max_suppression (벡터화 class-wise NMS)

기존에 있던 PyQt5 `DetectionWorker` / `CellDetection` / `DetectionOverlay` /
`TiledDetectionOverlay` / XML 저장 헬퍼 / `SpatialGrid` (Python 판) 등의 데스크톱
뷰어 전용 코드는 SaaS 파이프라인 (`_run_detection` 등) 에서 재구현 → 직접 사용되지
않으므로 제거했다. 필요 시 git history 에서 복구 가능.
"""

import numpy as np
import torch
import torchvision


# ── HE 세포 클래스 메타 ──
# 0~5 : detection 모델 원본 6-class
# 6, 7 : epithelial 후처리 분류 결과 (WSISegmentationModel 에서 채워짐)
CLASS_NAMES = {
    0: "Neutrophil",
    1: "Epithelial",
    2: "Lymphocyte",
    3: "Plasma",
    4: "Eosinophil",
    5: "Stromal cell",
    6: "Tumor Epithelial",
    7: "Benign Epithelial",
}

CLASS_COLORS = {
    0: "#FF4500",  # Neutrophil
    1: "#00FF00",  # Epithelial
    2: "#0000FF",  # Lymphocyte
    3: "#FFFF00",  # Plasma
    4: "#8A2BE2",  # Eosinophil
    5: "#808080",  # Stromal cell
    6: "#FF0000",  # Tumor Epithelial
    7: "#00FF00",  # Benign Epithelial
}


def wh2xy(x):
    """center(x, y, w, h) → corner(x1, y1, x2, y2). Torch tensor / ndarray 모두 지원."""
    y = x.clone() if isinstance(x, torch.Tensor) else np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def non_max_suppression(outputs, confidence_threshold=0.01, iou_threshold=0.35,
                         class_thresholds=None):
    """클래스별 NMS.

    Args:
        outputs: (B, 4+nc, N) YOLO raw 출력
        confidence_threshold: 전역 confidence 컷오프 (class_thresholds 미지정 class 에도 적용)
        iou_threshold: IoU 임계값
        class_thresholds: {class_id: threshold} per-class 컷오프

    Returns:
        list of (K_i, 6) tensors — [x1, y1, x2, y2, conf, cls]
    """
    bs = outputs.shape[0]
    nc = outputs.shape[1] - 4

    # 전체 confidence 가 낮은 것들 1차 필터 — 가장 낮은 threshold 기준
    min_conf = confidence_threshold
    if class_thresholds:
        min_conf = min(min(class_thresholds.values()), confidence_threshold)
    xc = outputs[:, 4:4 + nc].amax(1) > min_conf

    # 클래스별 threshold 텐서 사전 구성 (루프 외부 1회)
    thresh_t = None
    if class_thresholds:
        thresh_t = torch.full((nc,), confidence_threshold,
                              dtype=torch.float32, device=outputs.device)
        for cid, thr in class_thresholds.items():
            if 0 <= cid < nc:
                thresh_t[cid] = thr

    output = [torch.zeros((0, 6), device=outputs.device)] * bs

    for xi, x in enumerate(outputs):
        x = x.transpose(0, -1)[xc[xi]]
        if not x.shape[0]:
            continue

        box, cls = x.split((4, nc), 1)
        box = wh2xy(box)

        conf, j = cls.max(1, keepdim=True)
        x = torch.cat((box, conf, j.float()), 1)

        # 클래스별 threshold 벡터화 적용
        if thresh_t is not None:
            cls_idx = x[:, 5].long().clamp(0, nc - 1)
            x = x[x[:, 4] >= thresh_t[cls_idx]]
        else:
            x = x[x[:, 4] > confidence_threshold]

        if not x.shape[0]:
            continue

        x = x[x[:, 4].argsort(descending=True)]
        boxes = x[:, :4]
        scores = x[:, 4]
        keep = torchvision.ops.nms(boxes, scores, iou_threshold)
        output[xi] = x[keep]

    return output
