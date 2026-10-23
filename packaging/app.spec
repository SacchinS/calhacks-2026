# PyInstaller spec for the macOS .app. Build with `make app` (output in dist/).
#
# TODO(Person C): polish for a "download and run it" build: an app icon (icon=...),
# code signing, and a writable place for models/ and .env outside the bundle.
import plistlib
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (SPECPATH is set by PyInstaller)
NAME = "calhacks-2026"

with open(ROOT / "packaging" / "Info.plist", "rb") as f:
    info_plist = plistlib.load(f)

# Resources, loaded at runtime relative to shared.config.ROOT (sys._MEIPASS when bundled).
datas = [
    (str(ROOT / "config.yaml"), "."),
    (str(ROOT / "fixtures"), "fixtures"),
    (str(ROOT / "language" / "prompts"), "language/prompts"),
]
# app.py loads implementations by name (importlib), so PyInstaller can't see them.
# collect_submodules imports our packages, so the repo root must be on sys.path.
sys.path.insert(0, str(ROOT))
hiddenimports = []
for package in ("recognition", "language", "outputs", "captions", "ui"):
    hiddenimports += collect_submodules(package)

a = Analysis(  # noqa: F821
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name=NAME)  # noqa: F821
app = BUNDLE(  # noqa: F821
    coll,
    name=f"{NAME}.app",
    bundle_identifier=info_plist["CFBundleIdentifier"],
    info_plist=info_plist,
)
