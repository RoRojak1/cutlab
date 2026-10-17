#!/bin/zsh
# Сборка Cutlab.app (нативное окно) → ~/Applications/Cutlab.app
set -e
cd "$(dirname "$0")"
A="$HOME/Applications/Cutlab.app"
mkdir -p "$A/Contents/MacOS" "$A/Contents/Resources"
rm -rf "$A/Contents/MacOS" && mkdir -p "$A/Contents/MacOS"   # старый скрипт cutlab = Cutlab на регистронезависимом диске
xcrun swiftc -O -swift-version 5 -target arm64-apple-macos13 -framework Cocoa -framework WebKit -o "$A/Contents/MacOS/Cutlab" main.swift
cp Info.plist "$A/Contents/Info.plist"
cp ../../assets/ui/icon/NickEditor.icns "$A/Contents/Resources/Cutlab.icns"
codesign --force --deep -s - "$A"
touch "$A"
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "$A"
echo "OK: $A"
