// macOS 原生 OCR 小工具：用 Vision 识别一张图片里的文字，输出 JSON。
// 用法: vision-ocr <图片路径>
// 输出: [{"text": "...", "confidence": 0.99, "x":.., "y":.., "w":.., "h":..}, ...]
//   bbox 为归一化坐标（原点左下）。供功能二（区域 OCR）替代 PaddleOCR。
import Foundation
import Vision
import AppKit

let args = CommandLine.arguments
guard args.count > 1 else {
    FileHandle.standardError.write("usage: vision-ocr <image>\n".data(using: .utf8)!)
    exit(2)
}
let path = args[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load image: \(path)\n".data(using: .utf8)!)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]

let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do {
    try handler.perform([request])
} catch {
    FileHandle.standardError.write("vision error: \(error)\n".data(using: .utf8)!)
    exit(1)
}

var out: [[String: Any]] = []
for obs in (request.results ?? []) {
    guard let top = obs.topCandidates(1).first else { continue }
    let bb = obs.boundingBox
    out.append([
        "text": top.string,
        "confidence": top.confidence,
        "x": bb.origin.x, "y": bb.origin.y,
        "w": bb.size.width, "h": bb.size.height,
    ])
}

let data = try JSONSerialization.data(withJSONObject: out, options: [])
FileHandle.standardOutput.write(data)
