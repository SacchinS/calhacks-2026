#!/bin/bash
# Build dist/SignBridge.app: the SwiftUI app (ui/macos) plus a bundled Python engine (app.py and its packages).
#
#   packaging/build.sh             build into dist/          (make app)
#   packaging/build.sh --install   also copy to ~/Applications/SignBridge.app
#
# Adapted from SignBridge's macos/build.sh. Differences: it bundles this repo's engine, uses its own bundle id
# (com.calhacks2026.SignBridge), and only installs with --install, since ~/Applications/SignBridge.app may be
# the earlier SignBridge app.
#
# Signs with your first "Apple Development" identity so macOS keeps Camera permission across rebuilds (an
# ad-hoc signature changes every build). Override: SIGN_IDENTITY="..." or SIGN_IDENTITY=-
#
# TODO(Person C): API keys. The bundled engine reads Resources/engine/.env, which this script doesn't create;
# decide where a packaged app gets ANTHROPIC_API_KEY and CARTESIA_API_KEY from (never commit them).
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT=$(pwd)
APP=dist/SignBridge.app
RES=$APP/Contents/Resources
ENGINE=$RES/engine

echo "== Swift app"
swift build -c release --package-path ui/macos

echo "== Bundle layout"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$ENGINE"
cp ui/macos/.build/release/SignBridge "$APP/Contents/MacOS/SignBridge"
cp packaging/Info.plist "$APP/Contents/Info.plist"

echo "== Icons"
ICONSET=$(mktemp -d)/AppIcon.iconset
swift ui/macos/Assets/render.swift ui/macos/Assets/icon.svg "$ICONSET"
iconutil -c icns "$ICONSET" -o "$RES/AppIcon.icns"
cp ui/macos/Assets/menubar.svg ui/macos/Assets/menubar-on.svg ui/macos/Assets/signs.json "$RES/"

echo "== Python runtime"
PYHOME=$("$(uv python find 3.11)" -c "import sys; print(sys.base_prefix)")  # the real install, not uv's alias
cp -R "$PYHOME" "$RES/python"
rm -rf "$RES/python/lib/python3.11/site-packages"/*
rm -rf "$RES/python/lib/python3.11/"{test,idlelib,tkinter,turtledemo,ensurepip} "$RES/python/lib/"{tcl*,tk*,itcl*} 2>/dev/null || true
find "$RES/python" -name "EXTERNALLY-MANAGED" -delete

echo "== Engine dependencies (with the camera extra)"
REQS=$(mktemp)
uv export -q --frozen --no-dev --no-hashes --no-emit-project --extra camera -o "$REQS"
uv pip install -q --python "$RES/python/bin/python3" --target "$RES/site-packages" -r "$REQS"

echo "== Engine"
rsync -a --exclude "__pycache__" app.py config.yaml shared recognition language outputs captions fixtures "$ENGINE/"
mkdir -p "$ENGINE/ui" "$ENGINE/models"
cp ui/__init__.py ui/server.py "$ENGINE/ui/"
MODEL=models/holistic_landmarker.task
if [[ ! -f "$MODEL" ]]; then
  mkdir -p models
  curl -fsSL -o "$MODEL" "$(sed -n 's/^ *holistic_model_url: *//p' config.yaml)"
fi
cp "$MODEL" "$ENGINE/models/"
find "$APP" -name "__pycache__" -type d -prune -exec rm -rf {} +

echo "== Smoke test: the engine imports with the bundled Python"
(cd "$ENGINE" && PYTHONPATH="$ROOT/$ENGINE:$ROOT/$RES/site-packages" "$ROOT/$RES/python/bin/python3" -c \
  "import app, ui.server, recognition.camera, cv2, mediapipe; print('engine imports ok')")

echo "== Sign"
IDENTITY=${SIGN_IDENTITY:-$(security find-identity -p codesigning -v | grep -m1 '"Apple Development' | awk '{print $2}' || true)}
IDENTITY=${IDENTITY:--}
# Sign nested code first (inside out), then the app.
find "$RES" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) -print0 | while IFS= read -r -d '' f; do
  if file "$f" | grep -q "Mach-O"; then codesign --force --sign "$IDENTITY" --timestamp=none "$f" 2>/dev/null || echo "  could not sign $f"; fi
done
codesign --force --sign "$IDENTITY" --timestamp=none "$APP"
codesign --verify --deep --strict "$APP" && echo "signature ok ($IDENTITY)"
du -sh "$APP"

if [[ "${1:-}" == "--install" ]]; then
  echo "== Install"
  mkdir -p ~/Applications
  pkill -f "$HOME/Applications/SignBridge.app/Contents/MacOS/SignBridge" 2>/dev/null || true
  rm -rf ~/Applications/SignBridge.app
  cp -R "$APP" ~/Applications/
  echo "Installed ~/Applications/SignBridge.app. Open it with: open ~/Applications/SignBridge.app"
else
  echo "Built $APP. Open it with: open $APP"
fi
