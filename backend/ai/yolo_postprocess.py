"""Shared YOLO post-processing helpers for AI pipelines."""

import numpy as np
import torch
import torchvision


def wh2xy(x):
    """Convert center(x, y, w, h) boxes to corner(x1, y1, x2, y2)."""
    y = x.clone() if isinstance(x, torch.Tensor) else np.copy(x)
    y[:, 0] = x[:, 0] - x[:, 2] / 2
    y[:, 1] = x[:, 1] - x[:, 3] / 2
    y[:, 2] = x[:, 0] + x[:, 2] / 2
    y[:, 3] = x[:, 1] + x[:, 3] / 2
    return y


def non_max_suppression(outputs, confidence_threshold=0.01, iou_threshold=0.35,
                         class_thresholds=None, nms_priority_classes=None):
    """NMS for YOLO raw outputs.

    Args:
        outputs: (B, 4+nc, N) raw YOLO output.
        confidence_threshold: global confidence cutoff.
        iou_threshold: IoU threshold.
        class_thresholds: optional {class_id: threshold} per-class cutoff.
        nms_priority_classes: optional class ids that win NMS ordering over others.
    """
    bs = outputs.shape[0]
    nc = outputs.shape[1] - 4

    min_conf = confidence_threshold
    if class_thresholds:
        min_conf = min(min(class_thresholds.values()), confidence_threshold)
    xc = outputs[:, 4:4 + nc].amax(1) > min_conf

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

        if thresh_t is not None:
            cls_idx = x[:, 5].long().clamp(0, nc - 1)
            x = x[x[:, 4] >= thresh_t[cls_idx]]
        else:
            x = x[x[:, 4] > confidence_threshold]

        if not x.shape[0]:
            continue

        x = x[x[:, 4].argsort(descending=True)]
        cls_idx = x[:, 5].long()
        boxes = x[:, :4]
        scores = x[:, 4]
        if nms_priority_classes:
            priority_mask = torch.zeros_like(scores, dtype=torch.bool)
            for cid in nms_priority_classes:
                priority_mask |= cls_idx == int(cid)
            scores = scores + priority_mask.to(scores.dtype)
        keep = torchvision.ops.nms(boxes, scores, iou_threshold)
        output[xi] = x[keep]

    return output
