"""마커별 점수 계산 — PD-L1 (CPS/TPS), HER2, Allred (ER/PR), KI-67.

routers/ai.py 의 _run_pd_score / _run_precise_ihc 가 추론 결과(class array)
를 받아 호출. 설정 dict (PD_SCORE_CONFIG / PRECISE_IHC_CONFIG) 도 함께 두어
score_type 분기와 클래스 메타데이터를 한 곳에 모은다.
"""

# ═══════════════════════════════════════════════════════════════════
# PD-Score (PD-L1)
# ═══════════════════════════════════════════════════════════════════

PD_SCORE_CONFIG = {
    "Stomach": {
        "model_file": "PDL1_ST_CPS_detection.pt",
        "num_classes": 7,
        "class_names": {
            0: "Negative Epithelial",
            1: "Negative Lymphocyte",
            2: "Negative Macrophage",
            3: "Positive Epithelial",
            4: "Positive Lymphocyte",
            5: "Positive Macrophage",
            6: "Other",
        },
        "class_colors": {
            0: "#1e8449",
            1: "#27ae60",
            2: "#16a085",
            3: "#922b21",
            4: "#e74c3c",
            5: "#ec7063",
            6: "#95a5a6",
        },
        "score_type": "CPS",
        "exclude_classes": [6],
    },
    "Lung": {
        "model_file": "PDL1_TPS_detection.pt",
        "num_classes": 3,
        "class_names": {
            0: "PD-L1 Negative Tumor",
            1: "PD-L1 Positive Tumor",
            2: "Non-Tumor Cell",
        },
        "class_colors": {
            0: "#3498db",
            1: "#e74c3c",
            2: "#95a5a6",
        },
        "score_type": "TPS",
        # Non-Tumor (cls 2) 는 TPS 공식에 포함되지 않으니 표시도 생략한다.
        # marker_pipeline 에서 keep_mask 로 추론 결과에서 제거 + class_names/colors
        # 에서도 빠져 프론트 범례·시각화에 안 나온다.
        "exclude_classes": [2],
    },
}


def compute_pd_score(all_cls, tissue_type: str) -> dict:
    """
    CPS (Stomach): (positive tumor + positive immune) / viable tumor * 100, capped at 100
                   - positive tumor = cls 3 (positive Epithelial)
                   - positive immune = cls 4 + cls 5 (positive lymphocyte/macrophage)
                   - viable tumor = cls 0 + cls 3 (all epithelial)
    TPS  (Lung):   positive tumor / (positive + negative tumor) * 100
                   - positive tumor = cls 1
                   - negative tumor = cls 0
    """
    score_type = PD_SCORE_CONFIG[tissue_type]["score_type"]
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(PD_SCORE_CONFIG[tissue_type]["num_classes"])}

    if score_type == "CPS":
        int_pos_tumor = int_counts.get(3, 0)
        int_pos_immune = int_counts.get(4, 0) + int_counts.get(5, 0)
        int_viable_tumor = int_counts.get(0, 0) + int_counts.get(3, 0)
        if int_viable_tumor == 0:
            float_score = 0.0
        else:
            float_score = min(100.0, (int_pos_tumor + int_pos_immune) / int_viable_tumor * 100.0)
        return {
            "score_type": "CPS",
            "score": round(float_score, 2),
            "positive_tumor": int_pos_tumor,
            "positive_immune": int_pos_immune,
            "viable_tumor": int_viable_tumor,
            "class_counts": int_counts,
        }
    else:  # TPS
        int_pos_tumor = int_counts.get(1, 0)
        int_neg_tumor = int_counts.get(0, 0)
        int_total_tumor = int_pos_tumor + int_neg_tumor
        if int_total_tumor == 0:
            float_score = 0.0
        else:
            float_score = int_pos_tumor / int_total_tumor * 100.0
        return {
            "score_type": "TPS",
            "score": round(float_score, 2),
            "positive_tumor": int_pos_tumor,
            "negative_tumor": int_neg_tumor,
            "total_tumor": int_total_tumor,
            "class_counts": int_counts,
        }


# ═══════════════════════════════════════════════════════════════════
# Precise-IHC — HER2 / ER-PR / KI-67
# ═══════════════════════════════════════════════════════════════════

PRECISE_IHC_CONFIG = {
    "HER2": {
        "model_file": "Precise_IHC_HER2_detection.pt",
        "num_classes": 5,
        "class_names": {
            0: "HER2 0+",
            1: "HER2 1+",
            2: "HER2 2+",
            3: "HER2 3+",
            4: "Other",
        },
        # class0 (0+) 초록 → class3 (3+) 새빨강. class 숫자 ↑ → red ↑
        "class_colors": {
            0: "#27ae60",  # green (0+)
            1: "#f1c40f",  # yellow (1+)
            2: "#e67e22",  # orange (2+)
            3: "#c0392b",  # deep red (3+)
            4: "#95a5a6",  # other (hidden)
        },
        "score_type": "HER2",
        "exclude_classes": [4],
    },
    # ER/PR: HER2 와 동일한 5-class 모델 구조 (intensity 0+~3+ + Other).
    # ER 과 PR 은 동일 .pt 를 공유하고 추론 결과도 동일하므로 단일 marker("ER_PR") 로 통합.
    "ER_PR": {
        "model_file": "Precise_IHC_ER_PR_detection.pt",
        "num_classes": 5,
        "class_names": {
            0: "ER/PR 0+",
            1: "ER/PR 1+",
            2: "ER/PR 2+",
            3: "ER/PR 3+",
            4: "Other",
        },
        "class_colors": {
            0: "#27ae60",
            1: "#f1c40f",
            2: "#e67e22",
            3: "#c0392b",
            4: "#95a5a6",
        },
        "score_type": "Allred",
        "exclude_classes": [4],
    },
    # KI-67: ER/PR 모델을 임시 사용. class 0 = Negative, class 1/2/3 = Positive.
    # KI-67 Index = Positive / Total × 100 (%).
    "KI_67": {
        "model_file": "Precise_IHC_ER_PR_detection.pt",
        "num_classes": 5,
        "class_names": {
            0: "Negative",
            1: "Positive (1+)",
            2: "Positive (2+)",
            3: "Positive (3+)",
            4: "Other",
        },
        "class_colors": {
            0: "#27ae60",   # green (Negative)
            1: "#e67e22",   # orange (Positive weak)
            2: "#e74c3c",   # red (Positive moderate)
            3: "#c0392b",   # deep red (Positive strong)
            4: "#95a5a6",   # other (hidden)
        },
        "score_type": "KI67",
        "exclude_classes": [4],
    },
}


def compute_her2_score(all_cls) -> dict:
    """
    HER2 score:
      - 클래스 0~3 은 intensity 0+/1+/2+/3+
      - 가중 평균 = Σ(i * n_i) / Σ(n_i)  (i = 0..3)
      - dominant_class = 가장 많은 intensity
    """
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(4)}
    int_total = sum(int_counts.values())
    if int_total == 0:
        return {
            "score_type": "HER2",
            "score": 0.0,
            "dominant_class": 0,
            "total_tumor": 0,
            "class_counts": int_counts,
        }
    float_weighted = sum(i * int_counts[i] for i in range(4)) / int_total
    int_dominant = max(int_counts, key=lambda k: int_counts[k])
    return {
        "score_type": "HER2",
        "score": round(float_weighted, 3),
        "dominant_class": int_dominant,
        "total_tumor": int_total,
        "class_counts": int_counts,
    }


def compute_allred_score(all_cls) -> dict:
    """
    Allred score (ER/PR):
      - intensity 클래스 0~3 (none / weak / intermediate / strong)
      - Proportion Score (PS): 양성 비율 (positive / total tumor)
          0=0%, 1=<1%, 2=1-10%, 3=10-33%, 4=33-66%, 5=>66%
      - Intensity Score (IS): 양성 세포 평균 강도 → bin 0/1/2/3
          (avg < 0.5: 0, 0.5–1.5: 1, 1.5–2.5: 2, ≥2.5: 3)
      - Total Score (TS) = PS + IS (0~8). 3 이상 → Positive.
    """
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(4)}
    n0, n1, n2, n3 = int_counts[0], int_counts[1], int_counts[2], int_counts[3]
    int_total = n0 + n1 + n2 + n3
    int_pos = n1 + n2 + n3

    if int_total == 0:
        return {
            "score_type": "Allred",
            "proportion_score": 0,
            "intensity_score": 0,
            "total_score": 0,
            "positive_pct": 0.0,
            "avg_intensity": 0.0,
            "interpretation": "Negative",
            "total_tumor": 0,
            "class_counts": int_counts,
        }

    float_pos_pct = int_pos / int_total * 100.0
    if int_pos == 0:
        int_ps = 0
    elif float_pos_pct < 1.0:
        int_ps = 1
    elif float_pos_pct < 10.0:
        int_ps = 2
    elif float_pos_pct < 33.0:
        int_ps = 3
    elif float_pos_pct < 66.0:
        int_ps = 4
    else:
        int_ps = 5

    if int_pos == 0:
        float_avg = 0.0
        int_is = 0
    else:
        float_avg = (1 * n1 + 2 * n2 + 3 * n3) / int_pos
        if float_avg < 0.5:
            int_is = 0
        elif float_avg < 1.5:
            int_is = 1
        elif float_avg < 2.5:
            int_is = 2
        else:
            int_is = 3

    int_ts = int_ps + int_is
    str_interp = "Positive" if int_ts >= 3 else "Negative"

    return {
        "score_type": "Allred",
        "proportion_score": int_ps,
        "intensity_score": int_is,
        "total_score": int_ts,
        "positive_pct": round(float_pos_pct, 2),
        "avg_intensity": round(float_avg, 3),
        "interpretation": str_interp,
        "total_tumor": int_total,
        "class_counts": int_counts,
    }


def compute_ki67_score(all_cls) -> dict:
    """
    KI-67 Labeling Index:
      - class 0 = Negative, class 1/2/3 = Positive
      - KI-67 Index = Positive / Total × 100 (%)
      - 해석: ≥14% → High, <14% → Low (St Gallen 2013 기준)
    """
    int_counts = {int(c): int((all_cls == c).sum()) for c in range(4)}
    n0, n1, n2, n3 = int_counts[0], int_counts[1], int_counts[2], int_counts[3]
    int_total = n0 + n1 + n2 + n3
    int_pos = n1 + n2 + n3

    if int_total == 0:
        return {
            "score_type": "KI67",
            "ki67_index": 0.0,
            "positive_count": 0,
            "negative_count": 0,
            "total_tumor": 0,
            "interpretation": "Low",
            "class_counts": int_counts,
        }

    float_index = int_pos / int_total * 100.0
    str_interp = "High" if float_index >= 14.0 else "Low"

    return {
        "score_type": "KI67",
        "ki67_index": round(float_index, 2),
        "positive_count": int_pos,
        "negative_count": n0,
        "total_tumor": int_total,
        "interpretation": str_interp,
        "class_counts": int_counts,
    }
