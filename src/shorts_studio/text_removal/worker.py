import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from shorts_studio.text_removal.model import lama_model_path, model_dir, prepare_lama_model, user_network_dir


def make_mask(shape, horizontal, polygons, padding=3):
    import cv2
    import numpy as np
    mask = np.zeros(shape[:2], dtype=np.uint8)
    h, w = mask.shape
    for x1, x2, y1, y2 in horizontal:
        x1, x2 = max(0, int(x1)), min(w, int(x2) + 1)
        y1, y2 = max(0, int(y1)), min(h, int(y2) + 1)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    for polygon in polygons:
        points = np.asarray(polygon, dtype=np.int32)
        points[:, 0] = points[:, 0].clip(0, w - 1)
        points[:, 1] = points[:, 1].clip(0, h - 1)
        cv2.fillPoly(mask, [points], 255)
    # 글자 외곽선/그림자까지 포함하도록 작은 margin 추가.
    return cv2.dilate(mask, np.ones((padding * 2 + 1, padding * 2 + 1), np.uint8))


def adaptive_text_padding(text_height):
    """Scale the glyph margin with text size while bounding frame damage."""
    return max(3, min(8, int(float(text_height) * 0.13 + 0.5)))


def adaptive_dilate_text_mask(mask):
    """Dilate each nearby glyph group according to its text height."""
    import cv2
    import numpy as np

    height, width = mask.shape[:2]
    grouped = cv2.dilate(mask, np.ones((5, 5), np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(grouped)
    expanded = np.zeros((height, width), dtype=np.uint8)
    for label in range(1, count):
        x, y, box_width, box_height, area = stats[label]
        if area <= 0:
            continue
        padding = adaptive_text_padding(box_height)
        x0, y0 = max(0, x - padding), max(0, y - padding)
        x1, y1 = min(width, x + box_width + padding), min(height, y + box_height + padding)
        local_labels = labels[y0:y1, x0:x1] == label
        local_text = (mask[y0:y1, x0:x1] > 0) & local_labels
        if not local_text.any():
            continue
        local_mask = local_text.astype(np.uint8) * 255
        local_expanded = cv2.dilate(
            local_mask, np.ones((padding * 2 + 1, padding * 2 + 1), np.uint8)
        )
        expanded[y0:y1, x0:x1] = np.maximum(expanded[y0:y1, x0:x1], local_expanded)
    return expanded


def persistent_small_text_mask(sample_masks, frame_shape, min_votes=None):
    """Find small text masks repeated at the same pixels across sampled frames.

    This recovers faint, fixed overlays such as creator watermarks while
    excluding large, changing captions from the persistent mask.
    """
    import cv2
    import numpy as np

    height, width = frame_shape[:2]
    result = np.zeros((height, width), dtype=np.uint8)
    masks = [mask for mask in sample_masks
             if mask is not None and mask.shape[:2] == (height, width)]
    if len(masks) < 2:
        return result

    max_text_height = max(20, int(height * 0.0375))
    max_text_width = max(64, int(width * 0.32))
    hits = np.zeros((height, width), dtype=np.uint8)
    kernel = np.ones((5, 5), dtype=np.uint8)
    for mask in masks:
        grouped = cv2.dilate((mask > 0).astype(np.uint8), kernel)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(grouped)
        for label in range(1, count):
            x, y, box_width, box_height, area = stats[label]
            if (box_height < 6 or box_height > max_text_height
                    or box_width > max_text_width or area < 8):
                continue
            pixels = (labels == label) & (mask > 0)
            hits[pixels] += 1

    required_votes = min_votes if min_votes is not None else max(2, (len(masks) + 1) // 2)
    result[hits >= required_votes] = 255
    if result.any():
        result = cv2.dilate(result, np.ones((3, 3), dtype=np.uint8))
    return result


def sample_persistent_text_mask(cap, frame_count, detector, frame_shape):
    """Detect low-contrast fixed text in four evenly spaced source frames."""
    import cv2

    if frame_count < 4:
        return persistent_small_text_mask([], frame_shape), 0
    indices = sorted({int(round(frame_count * fraction))
                      for fraction in (0.05, 0.35, 0.65, 0.95)})
    masks = []
    for index in indices:
        if not cap.set(cv2.CAP_PROP_POS_FRAMES, min(index, frame_count - 1)):
            continue
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        mask = make_text_mask(
            detector, enhance_for_text_detection(frame),
            canvas_size=1280, threshold=0.12, padding=None,
        )
        masks.append(mask)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
    return persistent_small_text_mask(masks, frame_shape), len(masks)


def make_text_mask(detector, frame, canvas_size=1920, threshold=0.25, padding=3):
    """Build a tight mask from CRAFT's per-pixel text confidence map."""
    import cv2
    import numpy as np
    import torch
    from easyocr.imgproc import normalizeMeanVariance, resize_aspect_ratio

    height, width = frame.shape[:2]
    resized, ratio, _ = resize_aspect_ratio(
        frame, canvas_size, interpolation=cv2.INTER_LINEAR, mag_ratio=1
    )
    tensor = torch.from_numpy(
        np.transpose(normalizeMeanVariance(resized), (2, 0, 1))[None].astype(np.float32)
    ).to(detector.device)
    with torch.no_grad():
        output, _ = detector.detector(tensor)
    score = output[0, :, :, 0].detach().cpu().numpy()
    # Remove CRAFT's padded canvas before scaling the half-resolution map back.
    scaled_width, scaled_height = int(width * ratio), int(height * ratio)
    score = score[:(scaled_height + 1) // 2, :(scaled_width + 1) // 2]
    score = cv2.resize(score, (width, height), interpolation=cv2.INTER_LINEAR)
    mask = (score >= threshold).astype(np.uint8) * 255
    if padding is None:
        mask = adaptive_dilate_text_mask(mask)
    elif padding:
        size = padding * 2 + 1
        mask = cv2.dilate(mask, np.ones((size, size), np.uint8))
    return mask


def enhance_for_text_detection(frame, clip_limit=2.0, tile_grid_size=(8, 8)):
    """Boost low-contrast overlay text for CRAFT without changing output pixels."""
    import cv2

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=tile_grid_size).apply(gray)
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def lama_inpaint_crop(frame, mask, net, margin=48, backend_state=None):
    """Inpaint only the masked crop so high-resolution unmasked detail survives."""
    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    ys, xs = np.where(mask > 0)
    if not len(xs):
        return frame.copy()
    x1, x2 = max(0, int(xs.min()) - margin), min(width, int(xs.max()) + margin + 1)
    y1, y2 = max(0, int(ys.min()) - margin), min(height, int(ys.max()) + margin + 1)
    image_crop, mask_crop = frame[y1:y2, x1:x2], mask[y1:y2, x1:x2]
    crop_h, crop_w = image_crop.shape[:2]
    side = max(crop_h, crop_w)
    left = (side - crop_w) // 2
    right = side - crop_w - left
    top = (side - crop_h) // 2
    bottom = side - crop_h - top
    square = cv2.copyMakeBorder(image_crop, top, bottom, left, right, cv2.BORDER_REFLECT_101)
    square_mask = cv2.copyMakeBorder(
        mask_crop, top, bottom, left, right, cv2.BORDER_CONSTANT, value=0
    )

    image_blob = cv2.dnn.blobFromImage(square, 1 / 255.0, (512, 512), (0, 0, 0), False, False)
    mask_blob = cv2.dnn.blobFromImage(square_mask, 1.0, (512, 512), (0,), False, False)
    mask_blob = (mask_blob > 0).astype(np.float32)
    net.setInput(image_blob, "image")
    net.setInput(mask_blob, "mask")
    try:
        output = net.forward()
    except cv2.error:
        # Some OpenCL drivers advertise FP16 but fail on a particular graph.
        # Retry on CPU so optional acceleration can never block text removal.
        if backend_state is None or backend_state.get("name") != "opencl-fp16":
            raise
        net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        backend_state["name"] = "cpu-fallback"
        net.setInput(image_blob, "image")
        net.setInput(mask_blob, "mask")
        output = net.forward()
    if output.shape != (1, 3, 512, 512) or not np.isfinite(output).all():
        raise RuntimeError("LaMa returned an invalid inpainting result.")

    restored = np.transpose(output[0], (1, 2, 0)).clip(0, 255).astype(np.uint8)
    restored = cv2.resize(restored, (side, side), interpolation=cv2.INTER_CUBIC)
    restored_crop = restored[top:top + crop_h, left:left + crop_w]

    # Keep source pixels outside the mask; feather only the outer seam.
    expanded = cv2.dilate(mask_crop, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(expanded.astype(np.float32) / 255.0, (0, 0), sigmaX=1.5)
    alpha[mask_crop > 0] = 1.0
    result = frame.copy()
    original_crop = result[y1:y2, x1:x2].astype(np.float32)
    result[y1:y2, x1:x2] = (
        original_crop * (1.0 - alpha[:, :, None])
        + restored_crop.astype(np.float32) * alpha[:, :, None]
    ).clip(0, 255).astype(np.uint8)
    return result


def temporal_inpaint_merge(frame, mask, spatial, reference, reference_mask,
                           min_coverage=0.20, max_context_difference=12.0):
    """Use an adjacent frame only where motion and surrounding pixels agree.

    The spatial result remains the fallback. This conservative merge is meant
    to restore a portion of text-covered texture without copying moving hands,
    scene cuts, or another frame's subtitle into the output.
    """
    import cv2
    import numpy as np

    text = mask > 0
    if not text.any():
        return spatial, 0.0
    height, width = text.shape
    scale = min(1.0, 640.0 / max(width, height))
    flow_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    current_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    reference_gray = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY)
    current_small = cv2.resize(current_gray, flow_size, interpolation=cv2.INTER_AREA)
    reference_small = cv2.resize(reference_gray, flow_size, interpolation=cv2.INTER_AREA)
    forward_small = cv2.calcOpticalFlowFarneback(
        current_small, reference_small, None, 0.5, 3, 21, 3, 5, 1.2, 0
    )
    backward_small = cv2.calcOpticalFlowFarneback(
        reference_small, current_small, None, 0.5, 3, 21, 3, 5, 1.2, 0
    )
    forward = cv2.resize(forward_small, (width, height), interpolation=cv2.INTER_LINEAR)
    backward = cv2.resize(backward_small, (width, height), interpolation=cv2.INTER_LINEAR)
    forward[:, :, 0] /= scale
    forward[:, :, 1] /= scale
    backward[:, :, 0] /= scale
    backward[:, :, 1] /= scale

    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    map_x, map_y = xx + forward[:, :, 0], yy + forward[:, :, 1]
    warped_reference = cv2.remap(
        reference, map_x, map_y, cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    warped_reference_mask = cv2.remap(
        (reference_mask > 0).astype(np.uint8), map_x, map_y, cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT, borderValue=1,
    ) > 0
    warped_backward = cv2.remap(
        backward, map_x, map_y, cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )
    flow_error = np.sqrt(
        (forward[:, :, 0] + warped_backward[:, :, 0]) ** 2
        + (forward[:, :, 1] + warped_backward[:, :, 1]) ** 2
    )
    flow_consistent = flow_error < 2.5

    # Compare the unmasked neighborhood, not the subtitle pixels themselves.
    context = (~text) & (~warped_reference_mask) & flow_consistent
    difference = cv2.absdiff(current_gray, cv2.cvtColor(warped_reference, cv2.COLOR_BGR2GRAY))
    context_float = context.astype(np.float32)
    kernel = (31, 31)
    difference_sum = cv2.boxFilter(
        difference.astype(np.float32) * context_float, -1, kernel, normalize=False
    )
    context_count = cv2.boxFilter(context_float, -1, kernel, normalize=False)
    local_difference = difference_sum / np.maximum(context_count, 1.0)

    valid = text & (~warped_reference_mask) & flow_consistent
    valid &= local_difference <= float(max_context_difference)
    coverage = float(valid.sum()) / max(int(text.sum()), 1)
    if coverage < float(min_coverage):
        return spatial, coverage

    alpha = cv2.GaussianBlur(valid.astype(np.float32), (0, 0), sigmaX=1.0)
    alpha[valid] = 1.0
    merged = (
        spatial.astype(np.float32) * (1.0 - alpha[:, :, None])
        + warped_reference.astype(np.float32) * alpha[:, :, None]
    ).clip(0, 255).astype(np.uint8)
    return merged, coverage


def load_detector(download=False):
    import torch
    import easyocr
    torch.set_num_threads(text_cpu_threads())
    network_dir = user_network_dir()
    network_dir.mkdir(parents=True, exist_ok=True)
    # CRAFT 탐지만 사용. 언어별 인식 모델과 문자 whitelist는 사용하지 않음.
    return easyocr.Reader(["en"], gpu=False, recognizer=False, verbose=False,
                          model_storage_directory=str(model_dir()),
                          user_network_directory=str(network_dir), download_enabled=download)


def text_cpu_threads(cpu_count=None):
    """Use available CPU parallelism under an optional user-configured cap."""
    count = cpu_count if cpu_count is not None else (os.cpu_count() or 2)
    automatic = max(1, min(8, int(count) - 2))
    try:
        configured = int(os.environ.get("SHORTS_STUDIO_CPU_THREADS", ""))
    except ValueError:
        return automatic
    return min(max(1, int(count)), max(1, configured)) if configured else automatic


def load_inpainter(cv2, path):
    """Prefer OpenCL FP16 when supported; keep a CPU path for older PCs/drivers."""
    net = cv2.dnn.readNetFromONNX(str(path))
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    if cv2.ocl.haveOpenCL():
        try:
            targets = cv2.dnn.getAvailableTargets(cv2.dnn.DNN_BACKEND_OPENCV)
            target = cv2.dnn.DNN_TARGET_OPENCL_FP16
            if target in targets:
                cv2.ocl.setUseOpenCL(True)
                net.setPreferableTarget(target)
                return net, {"name": "opencl-fp16"}
        except cv2.error:
            pass
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    return net, {"name": "opencv-cpu"}


def text_canvas_size():
    """Select a supported CRAFT scale; larger canvases catch smaller text at higher CPU cost."""
    raw = os.getenv("SHORTS_TEXT_CANVAS", "960")
    try:
        size = int(raw)
    except ValueError as exc:
        raise RuntimeError("SHORTS_TEXT_CANVAS는 640, 960, 1280 중 하나여야 합니다.") from exc
    if size not in {640, 960, 1280}:
        raise RuntimeError("SHORTS_TEXT_CANVAS는 640, 960, 1280 중 하나여야 합니다.")
    return size


def clean_video(source, output, ffmpeg):
    import cv2
    import numpy as np
    from shorts_studio.core.engine import flags
    processing_threads = text_cpu_threads()
    cv2.setNumThreads(processing_threads)
    detector = load_detector()
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError("문자 제거용 영상을 열지 못했습니다.")
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    expected = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if not width or not height or not 0 < fps <= 120:
        cap.release()
        raise RuntimeError("지원하지 않는 영상 크기 또는 FPS입니다.")
    command = [ffmpeg, "-v", "error", "-nostdin", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
               "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
               "-threads", str(processing_threads), "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p",
               "-movflags", "+faststart", str(output)]
    encoder = None
    count, detected, preview_saved = 0, 0, False
    lama_frames, telea_frames, inpainter, inpaint_backend = 0, 0, None, {"name": "not-used"}
    canvas_size = text_canvas_size()
    persistent_mask = np.zeros((height, width), dtype=np.uint8)
    persistent_samples = persistent_pixels = 0
    try:
        persistent_mask, persistent_samples = sample_persistent_text_mask(
            cap, expected, detector, (height, width),
        )
        persistent_pixels = int((persistent_mask > 0).sum())
        with tempfile.TemporaryFile() as log:
            encoder = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                **flags(low_priority=os.environ.get("SHORTS_STUDIO_LOW_PRIORITY") == "1"),
            )
            while True:
                ok, frame = cap.read()
                if not ok:
                    break
                # 빠르게 바뀌는 자막을 놓치지 않도록 매 프레임 전체 화면 탐지.
                # 960px catches small overlay text better than 640px while
                # remaining below the measured 1280px CPU cost.
                # Adapt the glyph margin: small subtitles need less dilation;
                # large outlined text needs a wider margin to remove its stroke.
                # CRAFT's original threshold fragmented the pale creator watermark on
                # 111.mp4. Detect on CLAHE luminance, but always inpaint original pixels.
                detection_frame = enhance_for_text_detection(frame)
                mask = make_text_mask(detector, detection_frame, canvas_size=canvas_size,
                                      threshold=.2, padding=None)
                if persistent_pixels:
                    mask = cv2.bitwise_or(mask, persistent_mask)
                if mask.any():
                    detected += 1
                    if (mask > 0).mean() >= .03:
                        if inpainter is None:
                            inpainter, inpaint_backend = load_inpainter(cv2, lama_model_path())
                        cleaned = lama_inpaint_crop(frame, mask, inpainter,
                                                    backend_state=inpaint_backend)
                        lama_frames += 1
                    else:
                        cleaned = cv2.inpaint(frame, mask, 3, cv2.INPAINT_TELEA)
                        telea_frames += 1
                else:
                    cleaned = frame
                if mask.any():
                    if not preview_saved:
                        outlined = frame.copy()
                        outlined[mask > 0] = (outlined[mask > 0] * .5 + np.array([0, 0, 127])).astype(np.uint8)
                        comparison = np.hstack([frame, outlined, cleaned])
                        success, jpg = cv2.imencode(".jpg", comparison)
                        if success:
                            Path(output).with_suffix(".preview.jpg").write_bytes(jpg.tobytes())
                            preview_saved = True
                encoder.stdin.write(cleaned.tobytes())
                count += 1
                print(f"out_time_us={int(min(.99, count / max(expected, 1)) * 1_000_000)}", flush=True)
            encoder.stdin.close()
            code = encoder.wait(timeout=60)
            if code:
                log.seek(0)
                raise RuntimeError(log.read(4000).decode("utf-8", "replace"))
            if not count or (expected and count < expected - 1):
                raise RuntimeError("영상 프레임을 끝까지 읽지 못했습니다.")
            Path(output).with_suffix(".report.json").write_text(json.dumps({
                "schema_version": 1,
                "text_removal_required": True,
                "frames": count, "frames_with_text": detected,
                "lama_frames": lama_frames, "telea_frames": telea_frames,
                "persistent_text_sample_frames": persistent_samples,
                "persistent_small_text_mask_pixels": persistent_pixels,
                "craft_canvas_size": canvas_size,
                "lama_backend": inpaint_backend["name"],
                "mask_padding_policy": "adaptive-per-text-group-3-8px",
                "method": "craft-pixel-mask-persistent-consensus-lama-telea-v2",
                "method_description": (
                    "Four-frame consensus for persistent small text + CRAFT pixel mask; "
                    "crop LaMa for large masks + Telea for small masks"
                ),
                "review_required": True,
            }), encoding="utf-8")
    finally:
        cap.release()
        if encoder:
            if encoder.poll() is None:
                encoder.kill()
                encoder.wait()
            if encoder.stdin and not encoder.stdin.closed:
                encoder.stdin.close()


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--prepare"]:
            load_detector(download=True)
            prepare_lama_model()
            print("Text detector and LaMa inpainting model ready")
        else:
            clean_video(*sys.argv[1:])
    except Exception as exc:
        print(f"문자 제거 실패: {exc}", file=sys.stderr)
        sys.exit(1)
