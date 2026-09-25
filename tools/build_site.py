"""Build the server-less site (GitHub Pages) into site/: the same page the server serves, plus the
Python files the page runs under Pyodide and an index of the icons.

    uv run python tools/build_site.py && python -m http.server -d site 8000
"""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from teip.labels import ICON_EXT, list_icons

# What browser.py imports. app.py and backend.py (FastAPI, libusb) stay server-only.
PY_FILES = ["__init__.py", "browser.py", "config.py", "labels.py", "printers.py", "raster.py", "render.py",
            "fonts/LiberationSans-Bold.ttf", "fonts/OFL.txt"]


def build(out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "teip" / "static", out / "static")
    (out / "static" / "index.html").rename(out / "index.html")
    (out / ".nojekyll").touch()  # serve files as they are, no Jekyll pass

    icons = ROOT / "icons"
    files = {}
    for p in sorted(icons.rglob("*")):
        if p.suffix.lower() in ICON_EXT:
            rel = p.relative_to(icons).as_posix()
            files[rel.rsplit(".", 1)[0]] = rel
            (out / "icons" / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, out / "icons" / rel)
    shutil.copy2(icons / "ATTRIBUTION.md", out / "icons" / "ATTRIBUTION.md")
    (out / "icons" / "index.json").write_text(json.dumps({"icons": list_icons(icons), "files": files}))

    for f in PY_FILES:
        (out / "py" / "teip" / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "teip" / f, out / "py" / "teip" / f)
    (out / "py" / "manifest.json").write_text(json.dumps([f"teip/{f}" for f in PY_FILES]))
    print(f"built {out}: {len(files)} icons, {len(PY_FILES)} Python files")


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site")
