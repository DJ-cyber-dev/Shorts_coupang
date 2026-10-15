import importlib.util
import os
from pathlib import Path, PureWindowsPath
import unittest
from unittest.mock import patch

from shorts_studio.core import MediaError
from shorts_studio.text_removal.service import check_ready


class ReadinessTests(unittest.TestCase):
    def test_msix_user_network_is_stored_in_user_writable_local_app_data(self):
        from shorts_studio.text_removal.model import user_network_dir

        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local",
                                     "SHORTS_USER_NETWORK_DIR": ""}), \
             patch("shorts_studio.text_removal.model._has_package_identity", return_value=True):
            self.assertEqual(
                PureWindowsPath(str(user_network_dir())),
                PureWindowsPath(r"C:\Users\Test\AppData\Local\ShortsStudio\models\user_network"),
            )

    def test_lama_pinned_model_digest(self):
        from shorts_studio.text_removal.model import LAMA_BYTES, LAMA_SHA256
        self.assertEqual(LAMA_BYTES, 92_591_623)
        self.assertEqual(
            LAMA_SHA256,
            "7df918ac3921d3daf0aae1d219776cf0dc4e4935f035af81841b40adcf74fdf2",
        )

    def test_missing_dependency_reports_setup(self):
        with patch("shorts_studio.text_removal.service.importlib.util.find_spec", return_value=None):
            with self.assertRaisesRegex(MediaError, "setup\\.ps1"):
                check_ready()

    def test_missing_model_does_not_silently_skip(self):
        missing_model_dir = Path(__file__).resolve().parents[1] / "build" / "missing-model-test"
        with patch("shorts_studio.text_removal.service.importlib.util.find_spec", return_value=True), \
             patch("shorts_studio.text_removal.service.model_dir", return_value=missing_model_dir):
            with self.assertRaisesRegex(MediaError, "탐지 모델"):
                check_ready()

    def test_thread_budget_respects_user_cap(self):
        from shorts_studio.text_removal.worker import text_cpu_threads
        with patch.dict(os.environ, {"SHORTS_STUDIO_CPU_THREADS": "2"}):
            self.assertEqual(text_cpu_threads(12), 2)
        with patch.dict(os.environ, {"SHORTS_STUDIO_CPU_THREADS": "12"}):
            self.assertEqual(text_cpu_threads(12), 12)
        with patch.dict(os.environ, {"SHORTS_STUDIO_CPU_THREADS": "bad"}):
            self.assertEqual(text_cpu_threads(12), 8)


@unittest.skipUnless(importlib.util.find_spec("cv2"), "Optional text dependencies absent")
class MaskTests(unittest.TestCase):
    def test_low_contrast_detection_enhancement_preserves_frame_shape(self):
        import cv2
        import numpy as np
        from shorts_studio.text_removal.worker import enhance_for_text_detection

        frame = np.full((120, 180, 3), 180, dtype=np.uint8)
        cv2.putText(frame, "watermark", (8, 65), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (195, 195, 195), 1, cv2.LINE_AA)
        enhanced = enhance_for_text_detection(frame)
        self.assertEqual(enhanced.shape, frame.shape)
        self.assertEqual(enhanced.dtype, frame.dtype)
        self.assertFalse(np.array_equal(enhanced, frame))

    def test_persistent_small_text_consensus_keeps_repeated_small_masks_only(self):
        import numpy as np
        from shorts_studio.text_removal.worker import persistent_small_text_mask

        shape = (400, 600)
        samples = [np.zeros(shape, dtype=np.uint8) for _ in range(4)]
        # A faint watermark repeats in two samples; a large caption and a
        # one-off small label must not become a mask for every frame.
        for sample in samples[:2]:
            sample[100:116, 120:180] = 255
        for sample in samples:
            sample[220:285, 150:370] = 255
        samples[0][40:54, 420:470] = 255

        persistent = persistent_small_text_mask(samples, shape)
        self.assertGreater(int(persistent[108, 145]), 0)
        self.assertEqual(int(persistent[250, 250]), 0)
        self.assertEqual(int(persistent[46, 440]), 0)

    def test_craft_thread_budget_scales_with_logical_processors(self):
        from shorts_studio.text_removal.worker import text_cpu_threads
        self.assertEqual(text_cpu_threads(12), 8)
        self.assertEqual(text_cpu_threads(8), 6)
        self.assertEqual(text_cpu_threads(4), 2)
        self.assertEqual(text_cpu_threads(2), 1)

    def test_lama_prefers_opencl_fp16_only_when_advertised(self):
        from shorts_studio.text_removal.worker import load_inpainter

        class FakeNet:
            def __init__(self):
                self.target = None

            def setPreferableBackend(self, backend):
                self.backend = backend

            def setPreferableTarget(self, target):
                self.target = target

        class FakeDnn:
            DNN_BACKEND_OPENCV = 3
            DNN_TARGET_OPENCL_FP16 = 2
            DNN_TARGET_CPU = 0

            def __init__(self, targets):
                self.targets = targets
                self.net = FakeNet()

            def readNetFromONNX(self, _path):
                return self.net

            def getAvailableTargets(self, _backend):
                return self.targets

        class FakeOcl:
            def __init__(self, available):
                self.available = available

            def haveOpenCL(self):
                return self.available

            def setUseOpenCL(self, _enabled):
                pass

        class FakeCV2:
            error = RuntimeError

            def __init__(self, available, targets):
                self.dnn = FakeDnn(targets)
                self.ocl = FakeOcl(available)

        accelerated = FakeCV2(True, [2, 0])
        net, backend = load_inpainter(accelerated, "lama.onnx")
        self.assertIs(net, accelerated.dnn.net)
        self.assertEqual(backend["name"], "opencl-fp16")
        self.assertEqual(net.target, accelerated.dnn.DNN_TARGET_OPENCL_FP16)

        cpu_only = FakeCV2(False, [0])
        _, backend = load_inpainter(cpu_only, "lama.onnx")
        self.assertEqual(backend["name"], "opencv-cpu")
        self.assertEqual(cpu_only.dnn.net.target, cpu_only.dnn.DNN_TARGET_CPU)

    def test_lama_opencl_failure_retries_once_on_cpu(self):
        import cv2
        import numpy as np
        from shorts_studio.text_removal.worker import lama_inpaint_crop

        class FakeNet:
            def __init__(self):
                self.fail_once = True
                self.inputs = {}
                self.targets = []

            def setInput(self, value, name):
                self.inputs[name] = value

            def setPreferableBackend(self, value):
                self.backend = value

            def setPreferableTarget(self, value):
                self.targets.append(value)

            def forward(self):
                if self.fail_once:
                    self.fail_once = False
                    raise cv2.error("OpenCL execution failed")
                return np.full((1, 3, 512, 512), 180, dtype=np.float32)

        net = FakeNet()
        state = {"name": "opencl-fp16"}
        frame = np.full((120, 180, 3), 30, dtype=np.uint8)
        mask = np.zeros((120, 180), dtype=np.uint8)
        mask[40:60, 70:110] = 255
        result = lama_inpaint_crop(frame, mask, net, margin=16, backend_state=state)
        self.assertEqual(state["name"], "cpu-fallback")
        self.assertEqual(net.targets[-1], cv2.dnn.DNN_TARGET_CPU)
        self.assertTrue(np.all(result[50, 90] == 180))

    def test_craft_canvas_quality_choices_are_validated(self):
        from shorts_studio.text_removal.worker import text_canvas_size
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(text_canvas_size(), 960)
        for value in ("640", "960", "1280"):
            with patch.dict("os.environ", {"SHORTS_TEXT_CANVAS": value}):
                self.assertEqual(text_canvas_size(), int(value))
        with patch.dict("os.environ", {"SHORTS_TEXT_CANVAS": "720"}):
            with self.assertRaisesRegex(RuntimeError, "640, 960, 1280"):
                text_canvas_size()

    def test_box_polygon_and_border_clipping(self):
        import numpy as np
        from shorts_studio.text_removal.worker import make_mask
        mask = make_mask((100, 100, 3), [[-5, 20, 10, 30]], [[[60, 60], [80, 60], [80, 80], [60, 80]]])
        self.assertEqual(mask.dtype, np.uint8)
        self.assertEqual(mask[20, 0], 255)
        self.assertEqual(mask[70, 70], 255)
        self.assertEqual(mask[95, 5], 0)

    def test_no_text_preserves_frame(self):
        import numpy as np
        from shorts_studio.text_removal.worker import make_mask
        mask = make_mask((100, 100, 3), [], [])
        self.assertFalse(mask.any())

    def test_lama_crop_changes_masked_pixels_and_preserves_unmasked_frame(self):
        import numpy as np
        from shorts_studio.text_removal.worker import lama_inpaint_crop

        class FakeNet:
            def __init__(self):
                self.inputs = {}

            def setInput(self, value, name):
                self.inputs[name] = value

            def forward(self):
                self.assert_inputs()
                return np.full((1, 3, 512, 512), 180, dtype=np.float32)

            def assert_inputs(self):
                self_shape = self.inputs["image"].shape
                mask_shape = self.inputs["mask"].shape
                if self_shape != (1, 3, 512, 512) or mask_shape != (1, 1, 512, 512):
                    raise AssertionError((self_shape, mask_shape))

        frame = np.full((120, 180, 3), 30, dtype=np.uint8)
        mask = np.zeros((120, 180), dtype=np.uint8)
        mask[40:60, 70:110] = 255
        result = lama_inpaint_crop(frame, mask, FakeNet(), margin=16)
        self.assertTrue(np.array_equal(result[0, 0], frame[0, 0]))
        self.assertTrue(np.all(result[50, 90] == 180))

    def test_craft_confidence_map_masks_glyph_pixels_not_full_line(self):
        if importlib.util.find_spec("torch") is None:
            self.skipTest("Optional PyTorch dependency absent")
        import numpy as np
        import torch
        from shorts_studio.text_removal.worker import make_text_mask

        class FakeDetector:
            device = "cpu"

            def __init__(self):
                self.detector = self

            def __call__(self, image):
                scores = np.zeros((1, 50, 50, 2), dtype=np.float32)
                scores[0, 10:15, 20:25, 0] = 0.9
                return torch.from_numpy(scores), None

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mask = make_text_mask(FakeDetector(), frame, canvas_size=100, threshold=0.25, padding=0)
        ys, xs = np.where(mask)
        self.assertTrue(mask.any())
        self.assertGreaterEqual(xs.min(), 39)
        self.assertLessEqual(xs.max(), 50)
        self.assertGreaterEqual(ys.min(), 19)
        self.assertLessEqual(ys.max(), 30)
        self.assertLess(mask.sum(), 255 * 200)

    def test_craft_default_padding_stays_tight_around_glyphs(self):
        if importlib.util.find_spec("torch") is None:
            self.skipTest("Optional PyTorch dependency absent")
        import numpy as np
        import torch
        from shorts_studio.text_removal.worker import make_text_mask

        class FakeDetector:
            device = "cpu"

            def __init__(self):
                self.detector = self

            def __call__(self, image):
                scores = np.zeros((1, 50, 50, 2), dtype=np.float32)
                scores[0, 10:15, 20:25, 0] = 0.9
                return torch.from_numpy(scores), None

        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        tight = make_text_mask(FakeDetector(), frame, canvas_size=100,
                               threshold=0.25)
        wide = make_text_mask(FakeDetector(), frame, canvas_size=100,
                              threshold=0.25, padding=8)
        self.assertGreater(tight[25, 45], 0)
        self.assertEqual(tight[15, 45], 0)
        self.assertGreater(wide.sum(), tight.sum())
        self.assertLess(tight.sum(), wide.sum() * 0.7)

    def test_adaptive_mask_padding_scales_with_glyph_height(self):
        import numpy as np
        from shorts_studio.text_removal.worker import adaptive_dilate_text_mask, adaptive_text_padding
        self.assertEqual(adaptive_text_padding(12), 3)
        self.assertEqual(adaptive_text_padding(30), 4)
        self.assertEqual(adaptive_text_padding(63), 8)
        self.assertEqual(adaptive_text_padding(200), 8)

        mask = np.zeros((160, 160), dtype=np.uint8)
        mask[20:32, 20:60] = 255
        mask[80:143, 80:145] = 255
        expanded = adaptive_dilate_text_mask(mask)
        # Both cores remain covered, while the large title receives the larger margin.
        self.assertTrue(np.all(expanded[20:32, 20:60] == 255))
        self.assertTrue(np.all(expanded[80:143, 80:145] == 255))
        self.assertEqual(expanded[17, 40], 255)  # 12px text: 3px margin.
        self.assertEqual(expanded[16, 40], 0)
        self.assertEqual(expanded[72, 110], 255)  # 63px title: 8px margin.
        self.assertEqual(expanded[71, 110], 0)

    def test_temporal_merge_restores_only_aligned_text_pixels(self):
        import numpy as np
        from shorts_studio.text_removal.worker import temporal_inpaint_merge

        height, width = 128, 160
        reference = np.zeros((height, width, 3), dtype=np.uint8)
        reference[:, :, 0] = np.arange(width, dtype=np.uint8)[None, :] * 2
        reference[:, :, 1] = np.arange(height, dtype=np.uint8)[:, None] * 2
        frame = reference.copy()
        mask = np.zeros((height, width), dtype=np.uint8)
        mask[52:76, 58:104] = 255
        # Sparse glyph strokes leave enough background structure for flow tracking.
        frame[56:73, 66:70] = 255
        frame[60:76, 84:88] = 255
        frame[56:73, 98:102] = 255
        spatial = np.full_like(frame, 127)

        merged, coverage = temporal_inpaint_merge(
            frame, mask, spatial, reference, np.zeros_like(mask)
        )
        self.assertGreaterEqual(coverage, 0.20)
        restored = np.all(merged == reference, axis=2) & (mask > 0)
        self.assertTrue(restored.any())
        self.assertTrue(np.array_equal(merged[10, 10], spatial[10, 10]))

    def test_temporal_merge_rejects_photometrically_different_scene(self):
        import numpy as np
        from shorts_studio.text_removal.worker import temporal_inpaint_merge

        frame = np.zeros((128, 160, 3), dtype=np.uint8)
        mask = np.zeros((128, 160), dtype=np.uint8)
        mask[52:76, 58:104] = 255
        frame[mask > 0] = 255
        spatial = np.full_like(frame, 80)
        reference = np.full_like(frame, 180)

        merged, coverage = temporal_inpaint_merge(
            frame, mask, spatial, reference, np.zeros_like(mask)
        )
        self.assertLess(coverage, 0.20)
        self.assertTrue(np.array_equal(merged, spatial))
