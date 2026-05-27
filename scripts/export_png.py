"""Exporta los diagramas .mmd a PNG usando mermaid-cli via npx.

Requiere: Node.js (para npx)
Usa:     @mermaid-js/mermaid-cli (instalado via npx)

Uso:
    python scripts/export_png.py diagramas/00_descarga_raster_trmm_gpm.mmd
    python scripts/export_png.py --all
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMAS_DIR = ROOT / "diagramas"
EXPORT_DIR = ROOT / "export"
SCRIPTS_DIR = ROOT / "scripts"

MERMAID_CLI = ["npx", "--yes", "@mermaid-js/mermaid-cli"]
PUPPETEER_CONFIG = SCRIPTS_DIR / "puppeteer_config.json"


def export_one(mmd_path: Path, overwrite: bool = False) -> bool:
    """Exporta un .mmd a PNG. Devuelve True si tuvo exito."""
    png_name = mmd_path.stem + ".png"
    png_path = EXPORT_DIR / png_name

    if png_path.exists() and not overwrite:
        print(f"  [skip] {png_name} ya existe (usa --overwrite para reexportar)")
        return True

    cmd = MERMAID_CLI + [
        "-i", str(mmd_path),
        "-o", str(png_path),
        "-b", "white",
        "-w", "2400",
        "-H", "1800",
        "-p", str(PUPPETEER_CONFIG),
    ]

    print(f"  Exportando {mmd_path.name} ...")
    try:
        result = subprocess.run(
            cmd,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            shell=True,
        )
        if result.returncode == 0 and png_path.exists():
            print(f"  [ok] {png_name}")
            return True
        else:
            print(f"  [fail] {mmd_path.name}")
            if result.stderr:
                print(f"         {result.stderr[:300]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"  [timeout] {mmd_path.name} (>120s)")
        return False
    except Exception as e:
        print(f"  [error] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Exporta .mmd a PNG via mermaid-cli")
    parser.add_argument("mmd", nargs="?", help="Archivo .mmd especifico")
    parser.add_argument("--all", action="store_true", help="Exportar todos los .mmd")
    parser.add_argument("--overwrite", action="store_true", help="Sobrescribir PNGs existentes")
    args = parser.parse_args()

    EXPORT_DIR.mkdir(exist_ok=True)

    if args.all:
        mmd_files = sorted(DIAGRAMAS_DIR.glob("*.mmd"))
        print(f"Exportando {len(mmd_files)} diagrama(s) a {EXPORT_DIR}")
        results = [export_one(f, args.overwrite) for f in mmd_files]
        ok = sum(results)
        print(f"\nListo: {ok}/{len(results)} exitosos")
        sys.exit(0 if ok == len(results) else 1)
    elif args.mmd:
        mmd_path = Path(args.mmd)
        ok = export_one(mmd_path, args.overwrite)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
