# Diagramas Multitemporal

Repositorio de **documentación técnica con diagramas Mermaid** de un pipeline
geoespacial multitemporal: descarga de precipitación satelital, procesamiento
de imágenes ópticas y SAR (Sentinel-1/2), generación de máscaras de agua,
análisis geomorfológico, clasificación de coberturas y generación de salidas
gráficas para informes.

Cada diagrama documenta **un script Python** ubicado en
[`Codigos/`](./Codigos/) y se visualiza nativamente en GitHub.

---

## Índice de diagramas

Cada entrada documentada incluye **dos archivos** en `diagramas/`:
un `.md` (que GitHub renderiza directamente) y un `.mmd` (código Mermaid puro,
editable en [mermaid.live](https://mermaid.live) o
[Mermaid Chart](https://www.mermaidchart.com)).

| # | Código fuente | Descripción | Doc (`.md`) | Editable (`.mmd`) |
|---|---|---|---|---|
| 00 | [`00._Descarga_Raster_TRMM.py`](./Codigos/00._Descarga_Raster_TRMM.py) | Descarga precipitación mensual TRMM/GPM desde GEE | ✅ [ver](./diagramas/00_descarga_raster_trmm_gpm.md) | ✅ [abrir](./diagramas/00_descarga_raster_trmm_gpm.mmd) |
| 01 | [`01_Grafica_ideam.py`](./Codigos/01_Grafica_ideam.py) | Análisis estadístico de serie IDEAM (4 PNG + informe TXT) | ✅ [ver](./diagramas/01_grafica_ideam.md) | ✅ [abrir](./diagramas/01_grafica_ideam.mmd) |
| 01b | [`01_Grafica_ideam_Linumetrica.py`](./Codigos/01_Grafica_ideam_Linumetrica.py) | Análisis de estación limnimétrica IDEAM (6 PNG + 2 TXT) | ✅ [ver](./diagramas/01b_grafica_ideam_linumetrica.md) | ✅ [abrir](./diagramas/01b_grafica_ideam_linumetrica.mmd) |
| 02 | [`02_GraficaPrecipitacionSatelital_TRMM.py`](./Codigos/02_GraficaPrecipitacionSatelital_TRMM.py) | Gráficas de precipitación satelital | ⏳ | ⏳ |
| 03 | [`03_DESCARGA_IMAGENES_PRO.py`](./Codigos/03_DESCARGA_IMAGENES_PRO.py) | Descarga imágenes ópticas (Sentinel-2) | ⏳ | ⏳ |
| 04 | [`04_SELECION_MEJORES_IMAGENES.py`](./Codigos/04_SELECION_MEJORES_IMAGENES.py) | Selección de mejores imágenes por nubosidad | ⏳ | ⏳ |
| 05 | [`05_DESCARGA_IMAGEN_SAR.py`](./Codigos/05_DESCARGA_IMAGEN_SAR.py) | Descarga Sentinel-1 SAR | ⏳ | ⏳ |
| 06 | [`06_UNIR_MNDWI_SAR.py`](./Codigos/06_UNIR_MNDWI_SAR.py) | Fusión MNDWI (S2) + SAR para detección de agua | ⏳ | ⏳ |
| 07 | [`07_EXTRAER_MAS_AGUA.py`](./Codigos/07_EXTRAER_MAS_AGUA.py) | Extracción de cuerpos de agua | ⏳ | ⏳ |
| 08 | [`08_GEOMORFOLOGICO.py`](./Codigos/08_GEOMORFOLOGICO.py) | Análisis geomorfológico | ⏳ | ⏳ |
| 09 | [`09. Descargar Multibanda S2.py`](./Codigos/09.%20Descargar%20Multibanda%20S2.py) | Descarga multibanda Sentinel-2 | ⏳ | ⏳ |
| 10 | [`10. COBERTURAS.py`](./Codigos/10.%20COBERTURAS.py) | Generación de capas de coberturas | ⏳ | ⏳ |
| 11 | [`11 .UNIR_COMPONENTES.py`](./Codigos/11%20.UNIR_COMPONENTES.py) | Unión de componentes (insumos modelo) | ⏳ | ⏳ |
| 12 | [`12. ENTRENAR_MODELO_COBERTURAS.py`](./Codigos/12.%20ENTRENAR_MODELO_COBERTURAS.py) | Entrenamiento modelo clasificación coberturas | ⏳ | ⏳ |
| 13 | [`13. SALIDAS_GRAFICAS_INFORME.py`](./Codigos/13.%20SALIDAS_GRAFICAS_INFORME.py) | Salidas gráficas para informe | ⏳ | ⏳ |
| 14 | [`14. salida_graficas_compuestas.py`](./Codigos/14.%20salida_graficas_compuestas.py) | Salidas gráficas compuestas | ⏳ | ⏳ |
| ▣ | — | **Diagrama general del pipeline completo** | ⏳ | ⏳ |

> Leyenda: ✅ documentado · ⏳ pendiente · 🔧 en revisión

### Cómo editar un diagrama visualmente

1. Abre el `.mmd` correspondiente (ej. `diagramas/00_descarga_raster_trmm_gpm.mmd`).
2. Copia todo su contenido.
3. Pégalo en [mermaid.live](https://mermaid.live) (preview en vivo) o impórtalo
   en [Mermaid Chart](https://www.mermaidchart.com) (editor drag & drop).
4. Edita y vuelve a pegar el resultado en el `.mmd` **y** en el bloque
   ```` ```mermaid ```` del `.md` (deben quedar idénticos para que GitHub lo
   muestre actualizado).

> Hay instrucciones detalladas en la sección *Edición visual del diagrama*
> de cada `.md` (ej. [diagramas/00_descarga_raster_trmm_gpm.md](./diagramas/00_descarga_raster_trmm_gpm.md#edición-visual-del-diagrama)).

---

## Estructura del repositorio

```
diagramas_multitemporal/
├── README.md                       ← este archivo (índice general)
├── CLAUDE.md                       ← contexto técnico (TRMM/GPM y convenciones)
├── Codigos/                        ← scripts Python originales (16)
│   ├── 00._Descarga_Raster_TRMM.py
│   ├── 01_Grafica_ideam.py
│   └── ...
├── diagramas/                      ← un .md + .mmd por script
│   ├── 00_descarga_raster_trmm_gpm.md
│   ├── 00_descarga_raster_trmm_gpm.mmd
│   ├── 01_grafica_ideam.md
│   └── 01_grafica_ideam.mmd
└── scripts/
    └── sync_mmd.py                 ← inyecta el .mmd dentro del .md
```

### Sincronización `.mmd` → `.md`

Cuando edites un `.mmd`, ejecuta para reflejar el cambio en el `.md`:

```bash
python scripts/sync_mmd.py diagramas/01_grafica_ideam.mmd   # uno solo
python scripts/sync_mmd.py --all                            # todos
python scripts/sync_mmd.py --check                          # verifica sin tocar
```

---

## Visualización

- **En GitHub:** abre cualquier `.md` dentro de `diagramas/` y los bloques
  ```` ```mermaid ```` se renderizan automáticamente.
- **En VS Code:** `Ctrl + Shift + V` sobre el archivo `.md`.
  Se recomiendan las extensiones listadas en `.vscode/extensions.json`.

## Convenciones

Todos los diagramas siguen una **paleta de colores y nomenclatura estándar**
definida en [`CLAUDE.md`](./CLAUDE.md) (sección *Convenciones de diagramas*):

| Color | Uso |
|---|---|
| 🟦 `#2E4057` | Terminadores (INICIO / FIN) |
| 🟩 `#048A81` | Procesos |
| 🟪 `#54478C` | Bucles FOR |
| 🟧 `#F4A261` | Decisiones |
| 🟦 `#2196F3` | Fuente TRMM |
| 🟪 `#9C27B0` | Fuente GPM |
| 🟥 `#E63946` | Error / sin datos |
| ⬜ `#607D8B` | Omitir (archivo ya existe) |
| 🟢 `#4CAF50` | OK / éxito |
