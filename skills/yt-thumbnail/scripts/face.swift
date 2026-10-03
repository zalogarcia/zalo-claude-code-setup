import Vision
import AppKit
for p in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: p), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print(p, "load fail"); continue }
  let req = VNDetectFaceRectanglesRequest()
  try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
  let W = CGFloat(cg.width), H = CGFloat(cg.height)
  for f in (req.results ?? []) {
    let b = f.boundingBox
    print(p.split(separator: "/").last!, Int(b.minX*W), Int((1-b.maxY)*H), Int(b.width*W), Int(b.height*H))
  }
}
