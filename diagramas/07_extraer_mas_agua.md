# 07 — Extracción de masas de agua grandes + vectorización

Documenta el flujo del script
[`Codigos/07_EXTRAER_MAS_AGUA.py`](../Codigos/07_EXTRAER_MAS_AGUA.py),
que toma un **raster binario de agua** (puede ser la salida del
[diagrama 06](./06_unir_mndwi_sar.md) o cualquier otro binario) y genera un
**shapefile suavizado** con las masas de agua más grandes, filtrando ruido y
artefactos pequeños.

Esencialmente es el **Paso 2 y 3 del diagrama 06** como script independiente,
útil cuando ya se tiene un raster binario de agua y solo se necesita
vectorizarlo y suavizarlo.

---

## Resumen del proceso

1. **Cargar** el raster binario de entrada.
2. **Extracción de masas grandes:**
   - Erosión morfológica para separar componentes.
   - Etiquetado de componentes conectados.
   - Filtrado por área mínima en píxeles.
   - Dilatación para restaurar tamaño original.
   - Guardar TIF intermedio opcional.
3. **Vectorización y suavizado:**
   - Vectorizar a polígonos.
   - Reproyectar a UTM si es necesario.
   - Filtrar por área mínima en m².
   - Simplificación + suavizado iterativo + suavizado extra opcional.
   - Guardar shapefile final.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`07_extraer_mas_agua.mmd`](./07_extraer_mas_agua.mmd)

```mermaid
flowchart TD
    START([INICIO]) --> CFG

    CFG["Configurar rutas:<br/>raster binario de entrada,<br/>carpeta de salida,<br/>parámetros de extracción"] --> CARGAR
    CARGAR["Cargar raster binario<br/>de agua (agua=1, no-agua=0)"] --> EXTRACCION

    subgraph EXTRACCION ["Paso 1: Extracción de masas de agua grandes"]
      E1["Convertir a máscara binaria<br/>y contar pixeles iniciales"] --> E2
      E2["Aplicar erosión morfológica<br/>(scipy.ndimage.binary_erosion)"] --> E3
      E3["Etiquetar componentes conectados"] --> E4
      E4["Calcular tamaño de cada componente"] --> E5
      E5{"¿Componente ≥<br/>AREA_MINIMA_PIXELES?"} -->|"Sí"| E6
      E5 -->|"No"| DESCARTAR
      DESCARTAR["Descartar componente"] --> E5
      E6["Construir máscara de<br/>componentes grandes"] --> E7
      E7["Restaurar tamaño original:<br/>dilatación morfológica"] --> E8
      E8["Enmascarar con agua original<br/>(evita expansión artificial)"] --> E9
      E9["Guardar TIF intermedio<br/>masas grandes (opcional)"] --> FINEXT
      FINEXT["Fin extracción"]
    end

    EXTRACCION --> VECTORIZACION

    subgraph VECTORIZACION ["Paso 2: Vectorización y suavizado"]
      V1["Vectorizar raster a polígonos<br/>(rasterio.features.shapes)"] --> V2
      V2["Reproyectar a UTM si el CRS<br/>es geográfico"] --> V3
      V3["Filtrar polígonos por área<br/>mínima (m2)"] --> V4
      V4["Simplificación inicial"] --> V5
      V5["Suavizado iterativo:<br/>buffer+ / buffer-"] --> V6
      V6{"¿Usar suavizado extra?"} -->|"Sí"| V7
      V6 -->|"No"| V8
      V7["Suavizado extra:<br/>erosión-dilatación geométrica"] --> V8
      V8["Simplificación final"] --> V9
      V9["Calcular área (m2, ha)"] --> V10
      V10["Guardar shapefile suavizado"] --> FINVEC
      FINVEC["Fin vectorización"]
    end

    VECTORIZACION --> RESUMEN
    RESUMEN["Mostrar resumen:<br/>pixeles, componentes,<br/>polígonos finales, área total"] --> END_NODE

    END_NODE([FIN: shapefile de masas<br/>de agua suavizado])

    style START     fill:#2E4057,color:#fff
    style END_NODE  fill:#2E4057,color:#fff

    style CFG       fill:#048A81,color:#fff
    style CARGAR    fill:#048A81,color:#fff
    style E2        fill:#048A81,color:#fff
    style E3        fill:#048A81,color:#fff
    style E4        fill:#048A81,color:#fff
    style E6        fill:#048A81,color:#fff
    style E7        fill:#048A81,color:#fff
    style E8        fill:#048A81,color:#fff
    style E9        fill:#048A81,color:#fff
    style V1        fill:#048A81,color:#fff
    style V2        fill:#048A81,color:#fff
    style V3        fill:#048A81,color:#fff
    style V4        fill:#048A81,color:#fff
    style V5        fill:#048A81,color:#fff
    style V7        fill:#048A81,color:#fff
    style V8        fill:#048A81,color:#fff
    style V9        fill:#048A81,color:#fff
    style V10       fill:#048A81,color:#fff
    style RESUMEN   fill:#4CAF50,color:#fff

    style E5        fill:#F4A261,color:#000
    style V6        fill:#F4A261,color:#000

    style DESCARTAR fill:#607D8B,color:#fff
```

---

## Diferencias con el diagrama 06

| Aspecto | Diagrama 06 | Diagrama 07 |
|---|---|---|
| Entrada | Dos rasters (SAR + MNDWI) | Un raster binario cualquiera |
| Paso 1 | Unión OR + extracción | Solo extracción |
| Uso típico | Fusionar sensores | Vectorizar un binario existente |

El diagrama 07 es útil cuando se quiere **refinar un shapefile** a partir de un
raster binario ya generado por otro método.

---

## Parámetros configurables

```python
RUTA_ENTRADA = r"...\union_SAR_MNDWI_binario.tif"
CARPETA_SALIDA = os.path.dirname(RUTA_ENTRADA)

ITERACIONES_EROSION   = 1
AREA_MINIMA_PIXELES   = 20
GUARDAR_TIF_INTERMEDIO = True

MIN_AREA_M2           = 10
ITERACIONES_SUAVIZADO = 1
BUFFER_POR_ITERACION  = 1
SIMPLIFY_INICIAL      = 1.0
SIMPLIFY_FINAL        = 5.0
USAR_SUAVIZADO_EXTRA  = True
BUFFER_SUAVIZADO_EXTRA = 1
```

Los valores por defecto en el 07 son **mucho más permisivos** que en el 06
(área mínima de 20 px vs 200 px), porque está pensado para trabajar con el
raster unido ya filtrado, o para capturar cuerpos de agua más pequeños.

---

## Salidas generadas

```
<CARPETA_SALIDA>/
├── masas_agua_grandes_area{AREA_MINIMA_PIXELES}.tif
└── union_SAR_MNDWI_suavizado.shp
```

---

## Dependencias

```python
import os, numpy as np, rasterio
from scipy import ndimage
import geopandas as gpd
from rasterio.features import shapes as rio_shapes
```

---

## Insumos esperados

| Origen | Archivo | Uso |
|---|---|---|
| [Diagrama 06](./06_unir_mndwi_sar.md) (o cualquier binario) | Raster binario de agua (0/1) | Entrada para extracción y vectorización. |

---

## Edición visual del diagrama

1. **[mermaid.live](https://mermaid.live)** — copiar/pegar el `.mmd`.
2. **[Mermaid Chart](https://www.mermaidchart.com)** — drag & drop.
3. **VS Code** + extensión `tomoyukim.vscode-mermaid-editor`.

Tras editar, sincroniza con:

```bash
python scripts/sync_mmd.py diagramas/07_extraer_mas_agua.mmd
```
