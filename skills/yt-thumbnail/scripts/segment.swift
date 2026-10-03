import Vision
import AppKit
import CoreImage
// usage: segment <in.jpg> <out_mask.png>   person segmentation, accurate, full image size
let a = CommandLine.arguments
guard a.count == 3, let img = NSImage(contentsOfFile: a[1]), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { print("usage/read error"); exit(2) }
let req = VNGeneratePersonSegmentationRequest()
req.qualityLevel = .accurate
req.outputPixelFormat = kCVPixelFormatType_OneComponent8
try! VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
guard let buf = req.results?.first?.pixelBuffer else { print("no mask"); exit(1) }
var ci = CIImage(cvPixelBuffer: buf)
let sx = CGFloat(cg.width) / ci.extent.width, sy = CGFloat(cg.height) / ci.extent.height
ci = ci.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
let ctx = CIContext()
let out = ctx.createCGImage(ci, from: CGRect(x: 0, y: 0, width: cg.width, height: cg.height), format: .L8, colorSpace: CGColorSpaceCreateDeviceGray())!
let rep = NSBitmapImageRep(cgImage: out)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: a[2]))
print("mask", CVPixelBufferGetWidth(buf), CVPixelBufferGetHeight(buf), "->", cg.width, cg.height)
