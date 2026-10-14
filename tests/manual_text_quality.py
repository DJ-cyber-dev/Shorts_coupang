"""Optional real-model check. Run on Windows after setup-text-removal.ps1."""
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import numpy as np
from shorts_studio.core import Engine, Job
from shorts_studio.text_removal.service import remove_text
from shorts_studio.text_removal.worker import load_detector, make_text_mask


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # Each run gets an isolated folder so existing evidence is never overwritten.
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = Path(os.environ.get("SHORTS_TEXT_QUALITY_DIR", f"build/manual-text-quality-{run_id}"))
    folder.mkdir(parents=True, exist_ok=False)
    image = Image.new("RGB", (360, 640), (225, 235, 240))
    draw = ImageDraw.Draw(image)
    rows = [("Hello WORLD", "malgun.ttf", 80), ("한글 문자 제거", "malgun.ttf", 250),
            ("中文文字测试", "msyh.ttc", 430)]
    rects = []
    for text, font_name, y in rows:
        font = ImageFont.truetype(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_name), 32)
        draw.text((30, y), text, font=font, fill="black")
        rects.append(draw.textbbox((30, y), text, font=font))
    image.save(folder / "multilingual.png")
    frame = np.asarray(image)[:, :, ::-1].copy()
    detector = load_detector()
    mask = make_text_mask(detector, frame, canvas_size=640, threshold=.2, padding=None)
    for (text, _, _), (x1, y1, x2, y2) in zip(rows, rects):
        ink = frame[y1:y2, x1:x2].mean(axis=2) < 100
        coverage = (mask[y1:y2, x1:x2][ink] > 0).mean()
        print(f"{text}: ink mask coverage={coverage:.3f}", flush=True)
        assert coverage > .95, f"Insufficient text detection: {text}"
    del detector
    engine = Engine()
    source = folder / "input.mp4"
    subprocess.run([engine.ffmpeg, "-v", "error", "-y", "-loop", "1", "-i", str(folder / "multilingual.png"),
                    "-frames:v", "1", "-r", "30", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-threads", "2", str(source)], check=True)
    output = folder / "cleaned-pixel-mask.mp4"
    remove_text(engine, Job(source, output, width=360, height=640))
    report = json.loads(output.with_suffix(".report.json").read_text())
    assert report["frames"] == 1 and report["frames_with_text"] == 1, report
    assert output.with_suffix(".preview.jpg").is_file()
    assert engine.probe(output)["duration"] > 0, report
    print(f"Real-model multilingual one-frame video check OK: {folder}")


if __name__ == "__main__":
    main()
