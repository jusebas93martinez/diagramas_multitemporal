# Diagramas Multitemporal

Repositorio de documentación técnica con **diagramas Mermaid** que describen
pipelines de análisis multitemporal sobre datos geoespaciales (precipitación,
índices de vegetación, temperatura, etc.).

Los diagramas se visualizan nativamente en GitHub y localmente en VS Code con
la extensión *Markdown Preview Mermaid Support*.

---

## Índice de análisis

| # | Análisis | Estado | Diagramas |
|---|----------|--------|-----------|
| 1 | Precipitación TRMM/GPM (Colombia) | en construcción | [ver carpeta](./diagramas/) |

> A medida que se agreguen nuevos análisis multitemporales (NDVI, LST, etc.)
> se irán listando en esta tabla con su propio set de diagramas.

---

## Estructura del repositorio

```
diagramas_multitemporal/
├── README.md                        ← índice general (este archivo)
├── CLAUDE.md                        ← contexto técnico análisis TRMM/GPM
├── diagramas/
│   ├── 01_flujo_descarga.md
│   ├── 02_flujo_procesamiento.md
│   ├── 03_arquitectura_datos.md
│   ├── 04_pipeline_gee.md
│   └── 05_decisiones_clave.md
├── scripts/
│   └── validar_mermaid.py
└── .vscode/
    └── extensions.json
```

---

## Visualización

- **En GitHub:** abrir cualquier archivo `.md` dentro de `diagramas/` y los
  bloques ```` ```mermaid ```` se renderizan automáticamente.
- **En VS Code:** `Ctrl + Shift + V` sobre el archivo `.md`.

## Convenciones

Todos los diagramas siguen una paleta de colores y nomenclatura estándar
definida en [`CLAUDE.md`](./CLAUDE.md) (sección *Convenciones de diagramas*).

## Validación local (opcional)

```bash
# Con Node.js instalado
npm install -g @mermaid-js/mermaid-cli

# O usando el script del proyecto
python scripts/validar_mermaid.py diagramas/01_flujo_descarga.md
```
