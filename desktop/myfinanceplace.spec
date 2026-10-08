# PyInstaller recipe of the desktop app (F16):  pyinstaller desktop/myfinanceplace.spec
# Before: python -m desktop.fetch_postgres  (PostgreSQL binaries in desktop/vendor/pgsql)
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
PGSQL = ROOT / "desktop" / "vendor" / "pgsql"
if not (PGSQL / "bin").is_dir():
    raise SystemExit("PostgreSQL binaries missing: run  python -m desktop.fetch_postgres  first")

datas = [
    (str(ROOT / "app" / "templates"), "app/templates"),
    (str(ROOT / "app" / "static"), "app/static"),
    (str(ROOT / "app" / "translations"), "app/translations"),
    (str(ROOT / "migrations"), "migrations"),
    (str(PGSQL), "pgsql"),
]
for package in ("apiflask", "fpdf", "flask_migrate", "pdfminer", "docx"):
    datas += collect_data_files(package)


hiddenimports = collect_submodules("app") + collect_submodules("apiflask") + ["psycopg2", "waitress", "sqlalchemy.dialects.postgresql.psycopg2",
                                             "logging.config"]
excludes = ["rapidocr_onnxruntime", "onnxruntime", "cv2", "torch", "tensorflow", "pytest", "IPython",
            "matplotlib", "tkinter"]  # the light OCR is optional: without it scans go to AI reading

a = Analysis([str(ROOT / "desktop" / "launcher.py")], pathex=[str(ROOT)], datas=datas,
             hiddenimports=hiddenimports, excludes=excludes, noarchive=False)


def _wanted(entry) -> bool:
    """Babel's locale data only for the interface languages (Italian, English): 32 MB → about 2 MB."""
    dest = entry[0].replace("\\", "/")
    if "babel/locale-data/" not in dest:
        return True
    return Path(dest).stem.split("_")[0] in ("it", "en", "root")


a.datas = [entry for entry in a.datas if _wanted(entry)]
pyz = PYZ(a.pure)
icon = None
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="MyFinancePlace", console=False, icon=icon,
          upx=False)
coll = COLLECT(exe, a.binaries, a.datas, name="MyFinancePlace", upx=False)
if sys.platform == "darwin":
    app = BUNDLE(coll, name="MyFinancePlace.app", bundle_identifier="app.myfinanceplace.desktop",
                 info_plist={"NSHighResolutionCapable": True, "CFBundleShortVersionString": "1.0.0"})
