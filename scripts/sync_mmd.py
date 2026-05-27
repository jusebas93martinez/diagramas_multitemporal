"""Sincroniza diagramas .mmd dentro del bloque ```mermaid de su .md hermano.

Cada diagrama vive en dos archivos:

    diagramas/NN_nombre.mmd   <- fuente editable (se abre en mermaid.live, etc.)
    diagramas/NN_nombre.md    <- documentacion con el diagrama embebido

Este script toma el contenido del .mmd y lo inyecta dentro del primer bloque
```mermaid ... ``` que encuentre en el .md correspondiente, sustituyendo el
contenido anterior. El resto del .md (texto, secciones, notas) no se toca.

Uso:
    python scripts/sync_mmd.py diagramas/00_descarga_raster_trmm_gpm.mmd
    python scripts/sync_mmd.py --all
    python scripts/sync_mmd.py --check         # falla si algo esta desincronizado
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAGRAMAS_DIR = ROOT / "diagramas"

# Captura el primer bloque ```mermaid ... ```
MERMAID_BLOCK = re.compile(
    r"(```mermaid\s*\n)(.*?)(\n```)",
    re.DOTALL,
)


def sync_one(mmd_path: Path, check_only: bool = False) -> bool:
    """Devuelve True si el .md ya estaba (o quedo) sincronizado."""
    md_path = mmd_path.with_suffix(".md")
    if not md_path.exists():
        print(f"  [skip] no existe el .md hermano: {md_path.name}")
        return True

    mmd_content = mmd_path.read_text(encoding="utf-8").rstrip("\n")
    md_content = md_path.read_text(encoding="utf-8")

    match = MERMAID_BLOCK.search(md_content)
    if not match:
        print(f"  [warn] {md_path.name} no tiene un bloque ```mermaid```")
        return True

    current_inside = match.group(2)
    if current_inside.strip() == mmd_content.strip():
        print(f"  [ok]   {md_path.name} ya esta sincronizado")
        return True

    if check_only:
        print(f"  [DIFF] {md_path.name} esta desincronizado con {mmd_path.name}")
        return False

    new_md = MERMAID_BLOCK.sub(
        lambda m: m.group(1) + mmd_content + m.group(3),
        md_content,
        count=1,
    )
    md_path.write_text(new_md, encoding="utf-8")
    print(f"  [sync] {md_path.name} <- {mmd_path.name}")
    return True


def collect_targets(args: argparse.Namespace) -> list[Path]:
    if args.all or args.check:
        return sorted(DIAGRAMAS_DIR.glob("*.mmd"))
    return [Path(p).resolve() for p in args.paths]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Uno o mas archivos .mmd")
    parser.add_argument("--all", action="store_true", help="Procesa todos los .mmd de diagramas/")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo verifica sincronizacion. Sale con codigo != 0 si algo difiere.",
    )
    args = parser.parse_args()

    targets = collect_targets(args)
    if not targets:
        parser.error("Indica un archivo .mmd, o usa --all / --check")

    print(f"Procesando {len(targets)} archivo(s)...")
    all_ok = True
    for mmd in targets:
        if not mmd.exists() or mmd.suffix != ".mmd":
            print(f"  [skip] no es un .mmd valido: {mmd}")
            continue
        if not sync_one(mmd, check_only=args.check):
            all_ok = False

    if args.check and not all_ok:
        print("\nERROR: hay diagramas desincronizados. Ejecuta sin --check para arreglarlos.")
        return 1
    print("\nListo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
