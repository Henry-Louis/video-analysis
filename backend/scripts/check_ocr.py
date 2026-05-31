"""探查 PaddleOCR 3.x 的 API 与输出结构，并在给定图片上测试中文识别。

用法:
    python backend/scripts/check_ocr.py [图片路径]
默认识别 /tmp/burned_check.png（烧了字幕的帧）。
"""
import sys

from paddleocr import PaddleOCR

img = sys.argv[1] if len(sys.argv) > 1 else "/tmp/burned_check.png"
print(f"[INFO] OCR 图片: {img}")

ocr = PaddleOCR(
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
    lang="ch",
)

results = ocr.predict(img)
print(f"[INFO] 返回 {len(results)} 个结果对象")
for res in results:
    print("[INFO] 类型:", type(res).__name__)
    try:
        print("[INFO] keys:", list(res.keys()))
    except Exception as e:
        print("[WARN] 无 keys():", e)
    try:
        texts = res["rec_texts"]
        scores = res["rec_scores"]
        print("\n[识别文本]")
        for t, s in zip(texts, scores):
            print(f"  {s:.3f}  {t}")
    except Exception as e:
        print("[WARN] 取 rec_texts/rec_scores 失败:", e)
