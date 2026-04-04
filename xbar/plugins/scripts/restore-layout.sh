#!/bin/bash
# Auto-generated window layout restore script
# Generated on: 4/3/26, 2:35 PM

osascript << 'APPLESCRIPT'

-- Terminal windows
tell application "Terminal"
    activate
    try
        set bounds of window 1 to {1625, 32, 2523, 669}
    end try
    try
        set bounds of window 2 to {1622, 681, 2534, 1332}
    end try
end tell

-- Google Chrome windows
tell application "Google Chrome"
    activate
    try
        set bounds of window 1 to {0, 31, 1606, 1338}
    end try
end tell

-- Notes windows
tell application "Notes"
    activate
    try
        set bounds of window 1 to {-913, -5, -42, 943}
    end try
end tell

APPLESCRIPT

echo "Layout restored!"
