#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import subprocess
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parent
RAW_DIR = ROOT / "raw"
PROCESSED_DIR = ROOT / "processed"
CROPS_DIR = ROOT / "crops"
LINES_DIR = ROOT / "lines"
OUTPUT_DIR = ROOT / "output"

PAGE_MARGIN = 48
BLOCK_MIN_AREA = 4500
BLOCK_MIN_WIDTH = 60
BLOCK_MIN_HEIGHT = 60
MERGE_GAP = 56


def ensure_dirs() -> None:
    for path in (PROCESSED_DIR, CROPS_DIR, LINES_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def rotate_to_portrait(image: Image.Image) -> Image.Image:
    if image.width > image.height:
        return image.rotate(270, expand=True)
    return image


def otsu_threshold(gray: np.ndarray) -> int:
    hist, _ = np.histogram(gray.ravel(), bins=256, range=(0, 256))
    total = gray.size
    sum_total = np.dot(np.arange(256), hist)
    sum_bg = 0.0
    weight_bg = 0.0
    var_max = -1.0
    threshold = 0
    for idx, count in enumerate(hist):
        weight_bg += count
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += idx * count
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        between = weight_bg * weight_fg * ((mean_bg - mean_fg) ** 2)
        if between > var_max:
            var_max = between
            threshold = idx
    return threshold


def detect_page_bbox(gray: np.ndarray) -> tuple[int, int, int, int]:
    mask = gray > 150
    ys, xs = np.where(mask)
    if len(xs) == 0 or len(ys) == 0:
        return 0, 0, gray.shape[1], gray.shape[0]
    x0 = max(int(xs.min()) - PAGE_MARGIN, 0)
    y0 = max(int(ys.min()) - PAGE_MARGIN, 0)
    x1 = min(int(xs.max()) + PAGE_MARGIN, gray.shape[1])
    y1 = min(int(ys.max()) + PAGE_MARGIN, gray.shape[0])
    return x0, y0, x1, y1


def preprocess_image(path: Path) -> tuple[Image.Image, Image.Image]:
    image = Image.open(path).convert("L")
    image = rotate_to_portrait(image)
    gray = np.array(image)
    x0, y0, x1, y1 = detect_page_bbox(gray)
    image = image.crop((x0, y0, x1, y1))
    image = ImageOps.autocontrast(image, cutoff=2)
    blur = image.filter(ImageFilter.GaussianBlur(18))
    image_arr = np.array(image, dtype=np.float32)
    blur_arr = np.array(blur, dtype=np.float32)
    blur_arr[blur_arr < 1] = 1
    flat_arr = np.clip((image_arr / blur_arr) * 255.0, 0, 255).astype(np.uint8)
    flat = Image.fromarray(flat_arr, mode="L")
    flat = ImageOps.autocontrast(flat, cutoff=1)
    arr = np.array(flat)
    threshold = otsu_threshold(arr)
    binary = np.where(arr < threshold, 0, 255).astype(np.uint8)
    bw = Image.fromarray(binary, mode="L").filter(ImageFilter.MedianFilter(size=3))
    return image, bw


def connected_components(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    height, width = binary.shape
    visited = np.zeros((height, width), dtype=bool)
    boxes: list[tuple[int, int, int, int]] = []
    ink = binary == 0
    for y in range(height):
        for x in range(width):
            if visited[y, x] or not ink[y, x]:
                continue
            queue: deque[tuple[int, int]] = deque([(x, y)])
            visited[y, x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                min_x = min(min_x, cx)
                max_x = max(max_x, cx)
                min_y = min(min_y, cy)
                max_y = max(max_y, cy)
                for nx, ny in (
                    (cx - 1, cy),
                    (cx + 1, cy),
                    (cx, cy - 1),
                    (cx, cy + 1),
                    (cx - 1, cy - 1),
                    (cx + 1, cy - 1),
                    (cx - 1, cy + 1),
                    (cx + 1, cy + 1),
                ):
                    if 0 <= nx < width and 0 <= ny < height and not visited[ny, nx] and ink[ny, nx]:
                        visited[ny, nx] = True
                        queue.append((nx, ny))
            box_w = max_x - min_x + 1
            box_h = max_y - min_y + 1
            if area >= BLOCK_MIN_AREA and box_w >= BLOCK_MIN_WIDTH and box_h >= BLOCK_MIN_HEIGHT:
                boxes.append((min_x, min_y, max_x + 1, max_y + 1))
    return boxes


def merge_boxes(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    merged: list[list[int]] = []
    for box in sorted(boxes, key=lambda item: (item[1], item[0])):
        x0, y0, x1, y1 = box
        matched = False
        for current in merged:
            cx0, cy0, cx1, cy1 = current
            overlap_x = not (x0 > cx1 + MERGE_GAP or x1 < cx0 - MERGE_GAP)
            overlap_y = not (y0 > cy1 + MERGE_GAP or y1 < cy0 - MERGE_GAP)
            if overlap_x and overlap_y:
                current[0] = min(cx0, x0)
                current[1] = min(cy0, y0)
                current[2] = max(cx1, x1)
                current[3] = max(cy1, y1)
                matched = True
                break
        if not matched:
            merged.append([x0, y0, x1, y1])
    return [tuple(item) for item in merged]


def save_contact_sheet(images: list[Path], out_path: Path, columns: int = 4) -> None:
    thumbs = []
    for path in images:
        image = Image.open(path).convert("L")
        image = ImageOps.pad(image, (420, 420), color=255)
        thumbs.append(image)
    if not thumbs:
        return
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("L", (columns * 420, rows * 420), color=255)
    for index, thumb in enumerate(thumbs):
        x = (index % columns) * 420
        y = (index // columns) * 420
        sheet.paste(thumb, (x, y))
    sheet.save(out_path)


def run_tesseract(path: Path) -> str:
    try:
        result = subprocess.run(
            ["tesseract", str(path), "stdout", "-l", "chi_sim", "--psm", "7"],
            check=True,
            capture_output=True,
            text=True,
        )
        text = " ".join(line.strip() for line in result.stdout.splitlines()).strip()
        return text
    except Exception:
        return ""


def extract_line_boxes(binary: np.ndarray) -> list[tuple[int, int, int, int]]:
    height, width = binary.shape
    ink_counts = np.sum(binary == 0, axis=1)
    active = ink_counts > max(18, width // 120)
    bands: list[tuple[int, int]] = []
    start = None
    for idx, flag in enumerate(active):
        if flag and start is None:
            start = idx
        elif not flag and start is not None:
            if idx - start >= 18:
                bands.append((start, idx))
            start = None
    if start is not None and height - start >= 18:
        bands.append((start, height))

    boxes: list[tuple[int, int, int, int]] = []
    for y0, y1 in bands:
        row_slice = binary[y0:y1, :]
        col_counts = np.sum(row_slice == 0, axis=0)
        xs = np.where(col_counts > 2)[0]
        if len(xs) == 0:
            continue
        x0 = max(int(xs.min()) - 12, 0)
        x1 = min(int(xs.max()) + 12, width)
        boxes.append((x0, max(y0 - 10, 0), x1, min(y1 + 10, height)))
    return boxes


def build_preview_html(manifest: dict[str, dict[str, object]]) -> None:
    cards = []
    for page_name, page_data in manifest["pages"].items():
        clean = html.escape(str(page_data["clean"]))
        bw = html.escape(str(page_data["bw"]))
        lines = page_data.get("lines", [])
        line_html = "\n".join(
            f'<figure><img src="../{html.escape(line["path"])}" alt="{html.escape(line["id"])}"><figcaption>{html.escape(line.get("ocr", ""))}</figcaption></figure>'
            for line in lines
        )
        cards.append(
            f"""
            <section class="page-card">
              <h2>{html.escape(page_name)}</h2>
              <div class="page-pair">
                <img src="../{clean}" alt="{html.escape(page_name)} clean">
                <img src="../{bw}" alt="{html.escape(page_name)} bw">
              </div>
              <div class="lines-grid">{line_html}</div>
            </section>
            """
        )

    doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Handwriting Preview</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --card: #fffdf8;
      --ink: #171411;
      --line: #d8cfbf;
      --accent: #8d5e2a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 32px;
      background:
        radial-gradient(circle at top left, rgba(141, 94, 42, 0.18), transparent 30%),
        linear-gradient(180deg, #f7f1e4, var(--bg));
      color: var(--ink);
      font-family: "Avenir Next", "PingFang SC", sans-serif;
    }}
    h1 {{ margin-top: 0; font-size: 30px; }}
    p {{ max-width: 780px; line-height: 1.6; }}
    .summary {{
      display: inline-flex;
      gap: 12px;
      flex-wrap: wrap;
      margin: 8px 0 24px;
    }}
    .summary span {{
      padding: 8px 14px;
      border-radius: 999px;
      background: rgba(141, 94, 42, 0.1);
      color: var(--accent);
      font-size: 14px;
    }}
    .page-card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 24px;
      margin-bottom: 24px;
      box-shadow: 0 10px 28px rgba(56, 39, 21, 0.08);
    }}
    .page-pair {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 18px;
      margin-bottom: 18px;
    }}
    .page-pair img, .lines-grid img {{
      width: 100%;
      border-radius: 18px;
      border: 1px solid var(--line);
      background: white;
    }}
    .lines-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
    }}
    figure {{
      margin: 0;
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 12px;
    }}
    figcaption {{
      margin-top: 8px;
      min-height: 40px;
      color: #5a5148;
      font-size: 13px;
      white-space: pre-wrap;
    }}
  </style>
</head>
<body>
  <h1>手写样本自动整理预览</h1>
  <p>这是一版基于 4 张原始照片生成的自动清理结果，包含清理页、黑白页、文本行切片，以及 OCR 草稿。它的目的不是宣称“完整字体已完成”，而是把你的原始手写真正变成一套可继续制字的结构化素材。</p>
  <div class="summary">
    <span>原图 4 张</span>
    <span>文本块 {sum(page["crop_count"] for page in manifest["pages"].values())} 个</span>
    <span>文本行 {sum(len(page.get("lines", [])) for page in manifest["pages"].values())} 条</span>
  </div>
  {''.join(cards)}
</body>
</html>
"""
    (OUTPUT_DIR / "preview.html").write_text(doc, encoding="utf-8")


def process() -> None:
    ensure_dirs()
    manifest: dict[str, dict[str, object]] = {"pages": {}}
    crop_paths: list[Path] = []

    for image_path in sorted(RAW_DIR.glob("*.jp*g")):
        clean, bw = preprocess_image(image_path)
        processed_name = image_path.stem
        clean_path = PROCESSED_DIR / f"{processed_name}_clean.png"
        bw_path = PROCESSED_DIR / f"{processed_name}_bw.png"
        clean.save(clean_path)
        bw.save(bw_path)

        boxes = merge_boxes(connected_components(np.array(bw)))
        page_crops: list[str] = []
        for idx, (x0, y0, x1, y1) in enumerate(boxes, start=1):
            pad = 18
            crop = bw.crop(
                (
                    max(x0 - pad, 0),
                    max(y0 - pad, 0),
                    min(x1 + pad, bw.width),
                    min(y1 + pad, bw.height),
                )
            )
            crop_path = CROPS_DIR / f"{processed_name}_crop_{idx:02d}.png"
            crop.save(crop_path)
            crop_paths.append(crop_path)
            page_crops.append(str(crop_path.relative_to(ROOT)))

        line_entries: list[dict[str, str]] = []
        for idx, (x0, y0, x1, y1) in enumerate(extract_line_boxes(np.array(bw)), start=1):
            line = bw.crop((x0, y0, x1, y1))
            line_path = LINES_DIR / f"{processed_name}_line_{idx:02d}.png"
            line.save(line_path)
            line_entries.append(
                {
                    "id": f"{processed_name}_line_{idx:02d}",
                    "path": str(line_path.relative_to(ROOT)),
                    "ocr": run_tesseract(line_path),
                }
            )

        manifest["pages"][image_path.name] = {
            "clean": str(clean_path.relative_to(ROOT)),
            "bw": str(bw_path.relative_to(ROOT)),
            "crop_count": len(page_crops),
            "crops": page_crops,
            "lines": line_entries,
        }

    save_contact_sheet(crop_paths, OUTPUT_DIR / "contact_sheet.png")
    with (OUTPUT_DIR / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    build_preview_html(manifest)


if __name__ == "__main__":
    process()
