#!/usr/bin/env swift
// face-screen.swift: the expression gate for any image that shows Zalo's face.
//
// Usage: swift ~/.claude/skills/yt-thumbnail/scripts/face-screen.swift <image> [<image> ...]
//
// Apple Vision face landmarks (VNDetectFaceLandmarksRequest) on the LARGEST face in each image.
// Per file it prints: faces found, face height in px, head yaw in degrees, left and right eye
// openness, mouth openness, then PASS or REJECT with the reason.
//
//   yaw = continuous, from a separate VNDetectFaceRectanglesRequest revision 3 pass. The landmarks
//         request alone reports yaw in 45 degree bins, which read a head 26 degrees off axis as 0
//         and flipped a 20 degree head between 0 and 45 on a resize (2026-10-02).
//
//   eye openness   = height / width of that eye's landmark contour, in image pixels
//                    (left/right as Vision names them, i.e. the subject's own left/right)
//   mouth openness = height of the INNER lip contour / face box height, in image pixels
//
// Exit: 0 every file PASSES, 1 any REJECT, 2 usage or read error.
//
// Thresholds, calibrated 2026-10-02 on real 4K frames of Zalo from his whiteboard footage
// (~/Documents/Zalo Content/Whiteboard YouTube/video-0{1,5,6}*/thumbnails/stills/ and
// 1 fps scans of `video yt1/yt2/yt3.MP4`). He has naturally heavy lids, so the eye floor is
// set from his own frames, not from a generic face: the sleepy LF5 c2 source frame
// (lf5-still-yt2-t0338) REJECTS and frames picked by eye as fully open PASS. See the
// calibration table in the 2026-10-02 YT-WB-THUMBS worker report.
import AppKit
import Foundation
import Vision

let EYE_OPEN_MIN: Double = 0.30      // smaller eye of the two below this = blink or droopy lid
let MOUTH_OPEN_MAX: Double = 0.030   // inner lip gap above this fraction of face height = mid word mouth
let MIN_FACE_PX: Double = 80         // landmarks are unreliable below this; screen the full size source
let YAW_MAX_DEG: Double = 20         // head turned further than this from the lens = not facing camera
let EYE_SANE_MAX: Double = 0.90      // an eye ratio above this is a landmark failure (profile, hand, occlusion)

struct Result { let line: String; let pass: Bool; let error: Bool }

func extent(_ pts: [CGPoint]) -> (w: Double, h: Double) {
    guard let minX = pts.map({ $0.x }).min(), let maxX = pts.map({ $0.x }).max(),
          let minY = pts.map({ $0.y }).min(), let maxY = pts.map({ $0.y }).max() else { return (0, 0) }
    return (Double(maxX - minX), Double(maxY - minY))
}

func screen(_ path: String) -> Result {
    let name = (path as NSString).lastPathComponent
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return Result(line: "\(name)\tERROR cannot read image", pass: false, error: true)
    }
    let size = CGSize(width: cg.width, height: cg.height)
    let req = VNDetectFaceLandmarksRequest()
    // Yaw comes from a SEPARATE revision 3 face rectangles pass, which measures it continuously: the landmarks
    // request reports yaw in 45 degree bins (0 or 45), so a head 26 degrees off axis read as 0. Separate
    // handlers on purpose: in one handler the landmarks fit to the rev 3 boxes and the calibrated eye and
    // mouth numbers shift.
    let rects = VNDetectFaceRectanglesRequest()
    rects.revision = VNDetectFaceRectanglesRequestRevision3
    do {
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([rects])
    } catch {
        return Result(line: "\(name)\tERROR vision: \(error.localizedDescription)", pass: false, error: true)
    }
    let faces = (req.results ?? []).filter { $0.landmarks != nil }
    guard !faces.isEmpty else {
        return Result(line: "\(name)\tfaces=0\tREJECT no face", pass: false, error: false)
    }
    // Ignore tiny faces (posters, background) when counting: anything under 25% of the largest.
    let sorted = faces.sorted { $0.boundingBox.height > $1.boundingBox.height }
    let face = sorted[0]
    let others = sorted.dropFirst().filter { $0.boundingBox.height > face.boundingBox.height * 0.25 }
    let faceH = Double(face.boundingBox.height * size.height)
    guard let lm = face.landmarks, let le = lm.leftEye, let re = lm.rightEye, let il = lm.innerLips else {
        return Result(line: "\(name)\tfaces=\(faces.count)\tREJECT landmarks missing", pass: false, error: false)
    }
    let l = extent(le.pointsInImage(imageSize: size))
    let r = extent(re.pointsInImage(imageSize: size))
    let m = extent(il.pointsInImage(imageSize: size))
    let lOpen = l.w > 0 ? l.h / l.w : 0
    let rOpen = r.w > 0 ? r.h / r.w : 0
    let mouth = faceH > 0 ? m.h / faceH : 0
    // yaw of the same face from the revision 3 rectangles (largest box overlapping the landmarks face)
    let rect = (rects.results ?? []).filter { $0.boundingBox.intersects(face.boundingBox) }
        .max { $0.boundingBox.height < $1.boundingBox.height }
    let yawDeg = (rect?.yaw ?? face.yaw).map { $0.doubleValue * 180 / Double.pi }
    var reasons: [String] = []
    if !others.isEmpty { reasons.append("more than one face") }
    if faceH < MIN_FACE_PX { reasons.append("face too small to measure (\(Int(faceH)) px), screen the full size source") }
    if let y = yawDeg, abs(y) > YAW_MAX_DEG { reasons.append("head turned away from the lens") }
    if max(lOpen, rOpen) > EYE_SANE_MAX { reasons.append("eye landmarks unreliable (profile or occlusion)") }
    if min(lOpen, rOpen) < EYE_OPEN_MIN { reasons.append("blink or droopy lid") }
    if mouth > MOUTH_OPEN_MAX { reasons.append("mid word mouth") }
    let verdict = reasons.isEmpty ? "PASS" : "REJECT " + reasons.joined(separator: ", ")
    let yawText = yawDeg.map { String(format: "%.0f", $0) } ?? "na"
    let line = String(format: "%@\tfaces=%d\tface_px=%d\tyaw=%@\teye_L=%.3f\teye_R=%.3f\tmouth=%.3f\t%@",
                      name, faces.count, Int(faceH), yawText, lOpen, rOpen, mouth, verdict)
    return Result(line: line, pass: reasons.isEmpty, error: false)
}

let files = Array(CommandLine.arguments.dropFirst())
if files.isEmpty {
    FileHandle.standardError.write("usage: face-screen.swift <image> [<image> ...]\n".data(using: .utf8)!)
    exit(2)
}
var anyReject = false, anyError = false
for f in files {
    let r = screen(f)
    print(r.line)
    if r.error { anyError = true } else if !r.pass { anyReject = true }
}
exit(anyError ? 2 : (anyReject ? 1 : 0))
