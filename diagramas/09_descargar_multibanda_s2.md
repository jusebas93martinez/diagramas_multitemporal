# 09 — Descarga de mosaico multibanda Sentinel-2

Documenta el flujo del script
[`Codigos/09. Descargar Multibanda S2.py`](../Codigos/09.%20Descargar%20Multibanda%20S2.py),
que descarga imágenes **Sentinel-2 multibanda** (6 bandas espectrales) para una
fecha específica identificada previamente, usando **descarga por tiles** para
evitar límites de tamaño de GEE.

---

## Resumen del proceso

1. **Configurar** región de interés (centro lat/lon + lado en km), fecha
   objetivo, CRS UTM, bandas y grilla de tiles (2×2 por defecto).
2. **Inicializar Earth Engine** y crear la región con buffer.
3. **Buscar imágenes** para la fecha exacta:
   - Primero en `COPERNICUS/S2_SR_HARMONIZED` (con corrección atmosférica).
   - Fallback a `COPERNICUS/S2` (L1C/TOA) si no hay SR.
4. **Descargar por tiles:** para cada imagen encontrada, exporta cada tile
   individualmente y luego los fusiona con `rasterio.merge`.
5. **Verificar** que el raster final no tenga NoData significativo.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`09_descargar_multibanda_s2.mmd`](./09_descargar_multibanda_s2.mmd)

```mermaid
flowchart TD
    START([INICIO]) --> CFG

    CFG["Configurar:<br/>lat/lon centro, lado_km,<br/>fecha objetivo, CRS,<br/>bandas (B2/B3/B4/B8/B11/B12),<br/>tiles (2×2)"] --> INIT
    INIT["Inicializar Earth Engine"] --> REGION

    REGION["Crear región:<br/>buffer desde punto central<br/>→ cuadrado de lado_km"] --> TILES
    TILES["Dividir región en tiles<br/>(2×2 por defecto)"] --> BUSCAR

    BUSCAR["Buscar imágenes S2<br/>para fecha objetivo"] --> D1
    D1{"¿Hay imágenes<br/>SR_HARMONIZED?"} -->|"Sí"| LISTA_SR
    D1 -->|"No"| FALLBACK
    FALLBACK["Buscar imágenes<br/>Sentinel-2 L1C (TOA)"] --> D2
    D2{"¿Hay imágenes L1C?"} -->|"Sí"| LISTA_L1C
    D2 -->|"No"| ERR

    ERR["ERROR: sin imágenes<br/>para la fecha"] --> ERR_EXIT
    ERR_EXIT([FIN — error])

    LISTA_SR["Listar imágenes SR<br/>con metadatos de nubes"] --> LOOP_IMG
    LISTA_L1C["Listar imágenes L1C<br/>(advertir: sin corrección atmosférica)"] --> LOOP_IMG

    LOOP_IMG["/Para cada imagen<br/>encontrada/"] --> LOOP_TILE
    LOOP_TILE["/Para cada tile/"] --> DESC
    DESC["Exportar tile a GeoTIFF<br/>vía geemap.ee_export_image<br/>(10 m, CRS UTM)"] --> D_TILE
    D_TILE{"¿Tile descargado<br/>y no vacío?"} -->|"Sí"| GUARDAR_TILE
    D_TILE -->|"No"| OMIT_TILE
    GUARDAR_TILE["Agregar a lista<br/>de tiles válidos"] --> LOOP_TILE
    OMIT_TILE["Omitir tile"] --> LOOP_TILE
    LOOP_TILE --> MERGE

    MERGE["Merge de tiles<br/>con rasterio.merge"] --> D_MERGE
    D_MERGE{"¿Merge exitoso?"} -->|"Sí"| LIMPIAR
    D_MERGE -->|"No"| ERR_MERGE
    ERR_MERGE["ERROR: no se pudo<br/>fusionar tiles"] --> ERR_EXIT

    LIMPIAR["Eliminar tiles temporales"] --> VERIFICAR
    VERIFICAR["Verificar NoData<br/>en raster final"] --> GUARDAR
    GUARDAR["Guardar GeoTIFF final<br/>multibanda (6 bandas)"] --> SIG
    SIG{"¿Más imágenes?"} -->|"Sí"| LOOP_IMG
    SIG -->|"No"| RESUMEN

    RESUMEN["Mostrar resumen:<br/>N imágenes, directorio,<br/>estadísticas NoData"] --> END_NODE
    END_NODE([FIN: GeoTIFFs multibanda<br/>Sentinel-2 descargados])

    style START     fill:#2E4057,color:#fff
    style END_NODE  fill:#2E4057,color:#fff
    style ERR_EXIT  fill:#2E4057,color:#fff

    style CFG       fill:#048A81,color:#fff
    style INIT      fill:#048A81,color:#fff
    style REGION    fill:#048A81,color:#fff
    style TILES     fill:#048A81,color:#fff
    style BUSCAR    fill:#048A81,color:#fff
    style LISTA_SR  fill:#048A81,color:#fff
    style LISTA_L1C fill:#048A81,color:#fff
    style DESC      fill:#048A81,color:#fff
    style GUARDAR_TILE fill:#048A81,color:#fff
    style MERGE     fill:#048A81,color:#fff
    style LIMPIAR   fill:#048A81,color:#fff
    style VERIFICAR fill:#048A81,color:#fff
    style GUARDAR   fill:#048A81,color:#fff
    style RESUMEN   fill:#4CAF50,color:#fff

    style LOOP_IMG  fill:#54478C,color:#fff
    style LOOP_TILE fill:#54478C,color:#fff

    style D1        fill:#F4A261,color:#000
    style D2        fill:#F4A261,color:#000
    style D_TILE    fill:#F4A261,color:#000
    style D_MERGE   fill:#F4A261,color:#000
    style SIG       fill:#F4A261,color:#000

    style ERR       fill:#E63946,color:#fff
    style ERR_MERGE fill:#E63946,color:#fff
    style OMIT_TILE fill:#607D8B,color:#fff
```

---

## Bandas descargadas

| Banda | Nombre | Uso típico |
|---|---|---|
| B2 | Blue (490 nm) | Agua, aerosoles |
| B3 | Green (560 nm) | Vegetación saludable |
| B4 | Red (665 nm) | Clorofila, suelo |
| B8 | NIR (842 nm) | Biomasa, índices |
| B11 | SWIR1 (1610 nm) | Humedad del suelo |
| B12 | SWIR2 (2190 nm) | Minerales, quemado |

---

## Diferencia SR vs L1C

| Característica | SR (Surface Reflectance) | L1C (Top Of Atmosphere) |
|---|---|---|
| Corrección atmosférica | Sí | No |
| Valores | Reflectancia de superficie | Reflectancia TOA |
| Calidad | Mejor para clasificación | Aceptable si no hay SR |
| Disponibilidad | Menor (con nubes) | Mayor |

> El script advierte explícitamente cuando usa L1C para que el usuario lo tenga
> en cuenta en el análisis posterior.

---

## Parámetros configurables

```python
latitud      = 8.729069
longitud     = -75.909675
lado_km      = 4
CRS_EXPORTACION = 'EPSG:32618'
FECHA_OBJETIVO = '2025-12-06'
UMBRAL_NUBES_ESCENA = 50
UMBRAL_NUBES_LOCAL  = 32
bandas_s2 = ['B2','B3','B4','B8','B11','B12']
TILES_COLS = 2
TILES_FILAS = 2
```

---

## Salidas generadas

```
<DIRECTORIO_SALIDA>/
├── S2_2025-12-06_T18PUQ_SR.tif   ← ejemplo con SR
└── S2_2025-12-06_T18PUQ_TOA.tif  ← ejemplo con L1C (si fallback)
```

---

## Dependencias

```python
import ee, geemap, os, sys, rasterio, numpy as np
from rasterio.merge import merge
from datetime import datetime, timedelta
```

---

## Insumos esperados

| Origen | Dato | Uso |
|---|---|---|
| Usuario | Lat/lon centro + lado_km | Define el área de estudio. |
| Usuario | Fecha objetivo | Fecha exacta de la imagen deseada. |

---

## Edición visual del diagrama

1. **[mermaid.live](https://mermaid.live)** — copiar/pegar el `.mmd`.
2. **[Mermaid Chart](https://www.mermaidchart.com)** — drag & drop.
3. **VS Code** + extensión `tomoyukim.vscode-mermaid-editor`.

Tras editar, sincroniza con:

```bash
python scripts/sync_mmd.py diagramas/09_descargar_multibanda_s2.mmd
```

---

## Changelog

| Fecha | Cambio |
|---|---|
| 2026-05-27 | Creación inicial |
