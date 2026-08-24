import json
import unittest

import numpy as np

from app.ai_pipelines.stil_scoring import compute_stil_score


class StilScoringTests(unittest.TestCase):
    def test_area_score_and_density_use_tumor_associated_stroma(self):
        # output_mpp=10 means each mask pixel represents 100 um2.
        mask = np.zeros((20, 20), dtype=np.uint8)
        mask[8:12, 8:12] = 3  # tumor
        mask[4:16, 4:16][mask[4:16, 4:16] == 0] = 1  # surrounding stroma

        score = compute_stil_score(
            mask,
            {"output_mpp": 10.0, "wsi_mpp": 1.0, "region_offset": (0, 0)},
            np.array([50.0, 60.0, 190.0]),
            np.array([50.0, 60.0, 190.0]),
            np.array([2, 3, 2]),
            np.array([0.9, 0.9, 0.9]),
            immune_cell_area_um2=100.0,
            tumor_proximity_um=50.0,
            grid_size_um=100.0,
        )

        self.assertTrue(score["available"])
        self.assertEqual(score["lymphocyte_count"], 1)
        self.assertEqual(score["plasma_count"], 1)
        self.assertGreater(score["tumor_associated_stroma_area_mm2"], 0)
        expected = 200.0 / (score["tumor_associated_stroma_area_mm2"] * 1_000_000.0) * 100.0
        self.assertAlmostEqual(score["score_percent"], expected, places=2)
        self.assertTrue(score["spatial_heatmap"]["global_score_is_area_weighted"])
        json.dumps(score)

    def test_score_unavailable_without_tumor(self):
        mask = np.ones((8, 8), dtype=np.uint8)
        score = compute_stil_score(
            mask,
            {"output_mpp": 4.0, "wsi_mpp": 0.25, "region_offset": (0, 0)},
            [], [], [], [],
        )
        self.assertFalse(score["available"])
        self.assertIn("tumor", score["reason"].lower())

    def test_roi_and_confidence_filter_immune_detections(self):
        mask = np.ones((20, 20), dtype=np.uint8)
        mask[8:12, 8:12] = 3

        score = compute_stil_score(
            mask,
            {"output_mpp": 10.0, "wsi_mpp": 1.0, "region_offset": (0, 0)},
            np.array([50.0, 60.0, 150.0]),
            np.array([50.0, 60.0, 150.0]),
            np.array([2, 3, 2]),
            np.array([0.9, 0.05, 0.9]),
            roi_polygons=[[(0, 0), (120, 0), (120, 200), (0, 200)]],
            immune_cell_area_um2=100.0,
            tumor_proximity_um=100.0,
            grid_size_um=100.0,
            min_confidence=0.1,
        )

        self.assertTrue(score["available"])
        self.assertEqual(score["lymphocyte_count"], 1)
        self.assertEqual(score["plasma_count"], 0)
        self.assertEqual(score["minimum_detection_confidence"], 0.1)


if __name__ == "__main__":
    unittest.main()
