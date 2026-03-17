import Foundation
import Vision
import ImageIO

struct OCRBox: Codable {
    let text: String
    let x: Double
    let y: Double
    let width: Double
    let height: Double
    let characters: [OCRBox]?
}

struct OCRResult: Codable {
    let image: String
    let observations: [OCRBox]
}

func loadImage(_ path: String) -> CGImage? {
    let url = URL(fileURLWithPath: path) as CFURL
    guard let source = CGImageSourceCreateWithURL(url, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(source, 0, nil)
}

func recognize(_ path: String) throws -> OCRResult {
    guard let image = loadImage(path) else {
        throw NSError(domain: "vision_ocr", code: 1, userInfo: [NSLocalizedDescriptionKey: "Unable to load image"])
    }

    var boxes: [OCRBox] = []
    let request = VNRecognizeTextRequest { request, error in
        if let error {
            fputs("Vision error: \(error.localizedDescription)\n", stderr)
            return
        }
        guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
        for observation in observations {
            guard let candidate = observation.topCandidates(1).first else { continue }
            let rect = observation.boundingBox
            boxes.append(
                OCRBox(
                    text: candidate.string,
                    x: rect.origin.x,
                    y: rect.origin.y,
                    width: rect.width,
                    height: rect.height,
                    characters: characterBoxes(for: candidate)
                )
            )
        }
    }

    request.recognitionLanguages = ["zh-Hans", "en-US"]
    request.usesLanguageCorrection = false
    request.recognitionLevel = .accurate
    request.minimumTextHeight = 0.02

    let handler = VNImageRequestHandler(cgImage: image, options: [:])
    try handler.perform([request])
    return OCRResult(image: path, observations: boxes)
}

func characterBoxes(for candidate: VNRecognizedText) -> [OCRBox] {
    var items: [OCRBox] = []
    for charIndex in candidate.string.indices {
        let next = candidate.string.index(after: charIndex)
        let range = charIndex ..< next
        guard let rect = try? candidate.boundingBox(for: range) else { continue }
        let char = String(candidate.string[range])
        items.append(
            OCRBox(
                text: char,
                x: rect.boundingBox.origin.x,
                y: rect.boundingBox.origin.y,
                width: rect.boundingBox.width,
                height: rect.boundingBox.height,
                characters: nil
            )
        )
    }
    return items
}

let args = CommandLine.arguments.dropFirst()
if args.isEmpty {
    fputs("usage: swift vision_ocr.swift image1 [image2 ...]\n", stderr)
    exit(1)
}

let encoder = JSONEncoder()
encoder.outputFormatting = [.prettyPrinted, .sortedKeys]

for path in args {
    do {
        let result = try recognize(path)
        let data = try encoder.encode(result)
        if let text = String(data: data, encoding: .utf8) {
            print(text)
        }
    } catch {
        fputs("Failed on \(path): \(error.localizedDescription)\n", stderr)
    }
}
