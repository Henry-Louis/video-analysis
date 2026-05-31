"""验证本机 macOS Vision OCR（功能二引擎）。

用法:
    python backend/scripts/check_ocr.py [图片路径]
默认识别 /tmp/burned_check.png。打印每行文本与置信度（不过滤）。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from app.ocr import ocr_image  # noqa: E402

img = sys.argv[1] if len(sys.argv) > 1 else "/tmp/burned_check.png"
print(f"[INFO] OCR 图片: {img}（引擎：macOS Vision）")
results = ocr_image(img, min_score=0.0)
if not results:
    print("[WARN] 未识别到文本")
for text, score in results:
    print(f"  {score:.3f}  {text}")
