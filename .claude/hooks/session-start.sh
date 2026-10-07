#!/bin/bash
# Claude Code 雲端 session 啟動時安裝兩個 package（含 server 的 dev 依賴），
# 讓 core／server 測試與 tests/ 的文件守衛開箱即可執行。本機 session 不做任何事。
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(dirname "$0")/../..}"
python3 -m pip install --quiet --disable-pip-version-check \
  -e worldpane-core -e "worldpane-server[dev]"
