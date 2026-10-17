#!/bin/zsh
# Cutlab (монтажка Nick Editor): запускает сервер (если не запущен) и открывает монтажку отдельным окном.
cd "$(dirname "$0")"
URL="http://127.0.0.1:8777"
if ! curl -s -o /dev/null "$URL/api/ping"; then
  nohup arch -arm64 python3 studio/editor/server.py >> studio/editor/server.log 2>&1 &
  for i in {1..40}; do curl -s -o /dev/null "$URL/api/ping" && break; sleep 0.25; done
fi
if [ -d "/Applications/Google Chrome.app" ]; then
  open -na "Google Chrome" --args --app="$URL" --user-data-dir="$HOME/Library/Application Support/NickEditor" --window-size=1600,1000
else
  open "$URL"
fi
