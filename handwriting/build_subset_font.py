#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
LINES_DIR = ROOT / "lines"
GLYPH_DIR = ROOT / "glyphs"
RAW_GLYPH_DIR = GLYPH_DIR / "raw"
SVG_GLYPH_DIR = GLYPH_DIR / "svg"
OUTPUT_DIR = ROOT / "output"
VISION_SCRIPT = ROOT / "vision_ocr.swift"
FONTFORGE_SCRIPT = ROOT / "make_subset_font.py"


def ensure_dirs() -> None:
    for path in (RAW_GLYPH_DIR, SVG_GLYPH_DIR, OUTPUT_DIR):
        path.mkdir(parents=True, exist_ok=True)


def vision_ocr(image_path: Path) -> dict:
    result = subprocess.run(
        ["swift", str(VISION_SCRIPT), str(image_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def crop_character(line_path: Path, entry: dict) -> Image.Image:
    image = Image.open(line_path).convert("L")
    width, height = image.size
    x0 = int(entry["x"] * width)
    y0 = int((1 - (entry["y"] + entry["height"])) * height)
    x1 = int((entry["x"] + entry["width"]) * width)
    y1 = int((1 - entry["y"]) * height)
    pad = max(8, int(min(width, height) * 0.02))
    crop = image.crop((max(x0 - pad, 0), max(y0 - pad, 0), min(x1 + pad, width), min(y1 + pad, height)))
    crop = ImageOps.expand(crop, border=18, fill=255)
    return crop


def save_vector_glyph(char: str, image: Image.Image) -> tuple[Path, Path]:
    code = f"U+{ord(char):04X}"
    pbm_path = RAW_GLYPH_DIR / f"{code}.pbm"
    svg_path = SVG_GLYPH_DIR / f"{code}.svg"
    image.save(pbm_path)
    subprocess.run(["potrace", "-s", "-o", str(svg_path), str(pbm_path)], check=True)
    return pbm_path, svg_path


def select_glyphs() -> list[dict]:
    best: dict[str, dict] = {}
    for line_path in sorted(LINES_DIR.glob("*.png")):
        result = vision_ocr(line_path)
        for observation in result.get("observations", []):
            for char_entry in observation.get("characters") or []:
                char = char_entry["text"]
                if not char.strip():
                    continue
                score = char_entry["width"] * char_entry["height"]
                current = best.get(char)
                if current is None or score > current["score"]:
                    best[char] = {
                        "char": char,
                        "score": score,
                        "line_path": str(line_path),
                        "entry": char_entry,
                    }

    manifest: list[dict] = []
    for char, item in sorted(best.items(), key=lambda pair: ord(pair[0])):
        crop = crop_character(Path(item["line_path"]), item["entry"])
        pbm_path, svg_path = save_vector_glyph(char, crop)
        manifest.append(
            {
                "char": char,
                "codepoint": ord(char),
                "pbm_path": str(pbm_path),
                "svg_path": str(svg_path),
                "source_line": item["line_path"],
            }
        )
    return manifest


def build_preview(manifest: list[dict]) -> None:
    available = {item["char"] for item in manifest}
    preferred_lines = [
        "我要的被坚定选择",
        "稳定动作 不分析 只标记",
        "断写一周了 先估动记",
        "审美不是大脑活动",
    ]
    sample_lines = [line for line in preferred_lines if all(char == " " or char in available for char in line)]
    if not sample_lines:
        sample_lines = ["".join(item["char"] for item in manifest[:80])]
    sample_text = "<br>".join(sample_lines)
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Subset Font Preview</title>
  <style>
    @font-face {{
      font-family: "LessiHandSubset";
      src: url("./LessiHandSubset.ttf") format("truetype");
    }}
    body {{
      margin: 0;
      padding: 32px;
      background: linear-gradient(180deg, #f7f0e3, #efe5d5);
      color: #1d1712;
      font-family: "PingFang SC", sans-serif;
    }}
    .card {{
      max-width: 960px;
      margin: 0 auto;
      background: rgba(255,255,255,0.82);
      backdrop-filter: blur(8px);
      padding: 28px;
      border-radius: 24px;
      box-shadow: 0 18px 40px rgba(48, 33, 16, 0.1);
    }}
    .font {{
      font-family: "LessiHandSubset", "PingFang SC", sans-serif;
      font-size: 42px;
      line-height: 1.5;
      word-break: break-all;
      background: #fff;
      border-radius: 18px;
      padding: 20px;
      border: 1px solid #e6dbc7;
    }}
    .meta {{
      margin-top: 18px;
      color: #5b5247;
      font-size: 14px;
    }}
  </style>
</head>
<body>
  <div class="card">
    <h1>LessiHandSubset 测试字体</h1>
    <p>这是一版从 4 张手写照片自动提取并封装出的中文子集测试字体。字形映射依赖 Vision OCR，因此存在误识别，但已经是可安装、可输入的实验版结果。</p>
    <div class="font">{sample_text}</div>
    <div class="meta">收录字符数：{len(manifest)}</div>
  </div>
</body>
</html>
"""
    (OUTPUT_DIR / "font_preview.html").write_text(html, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    manifest = select_glyphs()
    manifest_path = OUTPUT_DIR / "glyph_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run(
        ["fontforge", "-script", str(FONTFORGE_SCRIPT), str(manifest_path), str(OUTPUT_DIR / "LessiHandSubset.ttf")],
        check=True,
    )
    build_preview(manifest)


if __name__ == "__main__":
    main()
