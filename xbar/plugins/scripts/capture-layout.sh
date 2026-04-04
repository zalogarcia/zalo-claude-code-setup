#!/bin/bash
# Capture current window layout and generate a restore script
# Usage: ./capture-layout.sh [output-file]

OUTPUT="${1:-$HOME/Library/Application Support/xbar/plugins/scripts/restore-layout.sh}"

# Capture all window positions using Swift + CoreGraphics and generate AppleScript directly
swift - "$OUTPUT" << 'SWIFTEOF'
import CoreGraphics
import Foundation

let options: CGWindowListOption = [.optionOnScreenOnly, .excludeDesktopElements]
guard let windowList = CGWindowListCopyWindowInfo(options, kCGNullWindowID) as? [[String: Any]] else {
    print("Error: Could not get window list")
    exit(1)
}

let targets: Set<String> = ["Slack", "Notes", "Google Chrome", "Terminal", "Finder", "Safari", "Cursor", "Visual Studio Code", "Preview", "Messages", "WhatsApp", "Telegram", "Calendar", "TextEdit", "Discord"]

// Collect windows grouped by app
var appWindows: [String: [(x: Int, y: Int, w: Int, h: Int)]] = [:]
var appOrder: [String] = []

for window in windowList {
    guard let owner = window["kCGWindowOwnerName"] as? String,
          let layer = window["kCGWindowLayer"] as? Int,
          targets.contains(owner),
          layer == 0,
          let bounds = window["kCGWindowBounds"] as? [String: Any] else { continue }

    let x = bounds["X"] as? Int ?? 0
    let y = bounds["Y"] as? Int ?? 0
    let w = bounds["Width"] as? Int ?? 0
    let h = bounds["Height"] as? Int ?? 0

    if appWindows[owner] == nil {
        appOrder.append(owner)
        appWindows[owner] = []
    }
    appWindows[owner]?.append((x: x, y: y, w: w, h: h))
    print("  \(owner): \(w)x\(h) at (\(x),\(y))")
}

// Electron/non-scriptable apps that need System Events
let electronApps: Set<String> = ["Slack", "Discord", "WhatsApp", "Telegram"]

// Generate AppleScript
var script = """
#!/bin/bash
# Auto-generated window layout restore script
# Generated on: \(DateFormatter.localizedString(from: Date(), dateStyle: .short, timeStyle: .short))

osascript << 'APPLESCRIPT'

"""

for app in appOrder {
    guard let windows = appWindows[app] else { continue }

    if electronApps.contains(app) {
        // Use System Events for Electron apps
        script += "\n-- \(app) windows\n"
        script += "tell application \"\(app)\" to activate\n"
        script += "delay 0.3\n"
        script += "try\n"
        script += "    tell application \"System Events\"\n"
        script += "        tell process \"\(app)\"\n"
        for (i, w) in windows.enumerated() {
            script += "            set position of window \(i + 1) to {\(w.x), \(w.y)}\n"
            script += "            set size of window \(i + 1) to {\(w.w), \(w.h)}\n"
        }
        script += "        end tell\n"
        script += "    end tell\n"
        script += "end try\n"
    } else {
        // Use native AppleScript bounds
        script += "\n-- \(app) windows\n"
        script += "tell application \"\(app)\"\n"
        script += "    activate\n"
        for (i, w) in windows.enumerated() {
            let x2 = w.x + w.w
            let y2 = w.y + w.h
            script += "    try\n"
            script += "        set bounds of window \(i + 1) to {\(w.x), \(w.y), \(x2), \(y2)}\n"
            script += "    end try\n"
        }
        script += "end tell\n"
    }
}

script += "\nAPPLESCRIPT\n\necho \"Layout restored!\"\n"

// Write to file
let outputPath = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : "restore-layout.sh"
try script.write(toFile: outputPath, atomically: true, encoding: .utf8)

// Make executable
let process = Process()
process.executableURL = URL(fileURLWithPath: "/bin/chmod")
process.arguments = ["+x", outputPath]
try process.run()
process.waitUntilExit()

print("\nLayout saved to: \(outputPath)")
SWIFTEOF
