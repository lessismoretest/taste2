import json
import sys

import fontforge
import psMat


manifest_path = sys.argv[1]
output_path = sys.argv[2]

with open(manifest_path, "r", encoding="utf-8") as handle:
    manifest = json.load(handle)

font = fontforge.font()
font.encoding = "UnicodeFull"
font.fontname = "LessiHandSubset"
font.familyname = "LessiHandSubset"
font.fullname = "LessiHandSubset"
font.em = 1000
font.ascent = 800
font.descent = 200

for item in manifest:
    codepoint = int(item["codepoint"])
    glyph = font.createChar(codepoint, item["char"])
    glyph.importOutlines(item["svg_path"])
    glyph.removeOverlap()
    bbox = glyph.boundingBox()
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    if width <= 0 or height <= 0:
        continue
    scale = min(780.0 / max(height, 1), 860.0 / max(width, 1))
    glyph.transform(psMat.scale(scale))
    bbox = glyph.boundingBox()
    tx = 70 - bbox[0]
    ty = 120 - bbox[1]
    glyph.transform(psMat.translate(tx, ty))
    bbox = glyph.boundingBox()
    glyph.width = int(max(520, min(980, bbox[2] + 90)))

font.generate(output_path)
