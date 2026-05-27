# 14 — Mapa compuesto cartográfico con Sentinel-2

Documenta el flujo del script
[`Codigos/14. salida_graficas_compuestas.py`](../Codigos/14.%20salida_graficas_compuestas.py),
una **plantilla extensible** para generar mapas compuestos de alta calidad con
imagen Sentinel-2 (o DEM) como fondo, capas vectoriales superpuestas, grilla de
coordenadas en **EPSG:9377** (MAGNA SIRGAS Origen Nacional), escala gráfica,
flecha de norte, leyenda y diagnóstico de CRS.

---

## Resumen del proceso

1. **Configurar** todas las rutas (raster fondo, DEM opcional, capas
   vectoriales, tamaño de figura, capas activas).
2. **Diagnóstico CRS:** verifica que todos los rasters y vectoriales tengan CRS
   definido y alerta si hay diferencias con respecto a EPSG:9377.
3. **Calcular extent:** lee la capa de referencia, aplica buffer y ajusta el
   bbox al ratio de la figura.
4. **Procesar raster de fondo:** lee, reproyecta al grid exacto del mapa,
   aplica percent-clip, gamma, brillo y desaturación.
5. **Procesar DEM opcional:** recorta, reproyecta, genera hillshade con
   LightSource.
6. **Cargar capas vectoriales:** lee cada capa activa, reproyecta a EPSG:9377,
   filtra por bbox.
7. **Dibujar:** fondo raster, DEM hillshade, capas vectoriales con halo,
   etiqueta central, flecha norte, escala gráfica, grilla EPSG:9377, recuadro
   CRS, leyenda y regleta de elevación.
8. **Guardar** PNG a DPI configurado.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`14_salidas_graficas_compuestas.mmd`](./14_salidas_graficas_compuestas.mmd)

```mermaid
flowchart TD
    START([INICIO]) --> CFG

    CFG["Configurar:<br/>rutas raster fondo, capas vectoriales,<br/>CRS salida (EPSG:9377),<br/>buffer, tamaño figura,<br/>capas activas"] --> DIAGNOSTICO

    DIAGNOSTICO["Ejecutar diagnóstico CRS:<br/>verificar CRS de todos los<br/>rasters y vectoriales"] --> VALIDAR
    VALIDAR{"¿Capa de referencia<br/>encontrada?"} -->|"Sí"| REF
    VALIDAR -->|"No"| ERR
    ERR["ERROR: falta capa<br/>de referencia"] --> ERR_EXIT
    ERR_EXIT([FIN — error])

    REF["Leer shapefile de referencia<br/>y reproyectar a EPSG:9377"] --> EXTENT
    EXTENT["Calcular bbox con buffer<br/>+ ajustar a ratio figura"] --> CAPAS

    CAPAS["Para cada capa vectorial activa:<br/>leer, reproyectar, filtrar por bbox"] --> RASTER

    RASTER["Si imagen satelital activa:<br/>leer, reproyectar a grid exacto,<br/>percent-clip, gamma, brillo"] --> DEM
    DEM["Si DEM activo:<br/>recortar, reproyectar,<br/>hillshade opcional"] --> FIGURA

    FIGURA["Crear figura matplotlib"] --> DIBUJAR

    subgraph DIBUJAR ["Dibujar elementos cartográficos"]
      D1["Fondo: imagen satelital<br/>o DEM hillshade o gris"] --> D2
      D2["Capas vectoriales:<br/>polígonos, líneas, puntos<br/>con halo opcional"] --> D3
      D3["Etiqueta central<br/>(nombre del área)"] --> D4
      D4["Flecha de norte"] --> D5
      D5["Escala gráfica<br/>(coherente con grilla)"] --> D6
      D6["Grilla Norte/Este<br/>EPSG:9377 con etiquetas"] --> D7
      D7["Recuadro CRS + escala<br/>en esquina inferior"] --> D8
      D8["Leyenda de capas visibles"] --> D9
      D9["Regleta de elevación<br/>(si DEM activo)"] --> FIN_DIBUJAR
      FIN_DIBUJAR["Mapa dibujado"]
    end

    DIBUJAR --> GUARDAR
    GUARDAR["Guardar PNG a DPI configurado<br/>con fondo blanco"] --> RESUMEN
    RESUMEN["Mostrar resumen:<br/>ruta de salida, estado"] --> END_NODE

    END_NODE([FIN: mapa compuesto<br/>cartográfico generado])

    style START     fill:#2E4057,color:#fff
    style END_NODE  fill:#2E4057,color:#fff
    style ERR_EXIT  fill:#2E4057,color:#fff

    style CFG       fill:#048A81,color:#fff
    style DIAGNOSTICO fill:#048A81,color:#fff
    style REF       fill:#048A81,color:#fff
    style EXTENT    fill:#048A81,color:#fff
    style CAPAS     fill:#048A81,color:#fff
    style RASTER    fill:#048A81,color:#fff
    style DEM       fill:#048A81,color:#fff
    style FIGURA    fill:#048A81,color:#fff
    style D1        fill:#048A81,color:#fff
    style D2        fill:#048A81,color:#fff
    style D3        fill:#048A81,color:#fff
    style D4        fill:#048A81,color:#fff
    style D5        fill:#048A81,color:#fff
    style D6        fill:#048A81,color:#fff
    style D7        fill:#048A81,color:#fff
    style D8        fill:#048A81,color:#fff
    style D9        fill:#048A81,color:#fff
    style GUARDAR   fill:#048A81,color:#fff
    style RESUMEN   fill:#4CAF50,color:#fff

    style VALIDAR   fill:#F4A261,color:#000

    style ERR       fill:#E63946,color:#fff
    style FIN_DIBUJAR fill:#4CAF50,color:#fff
```

---

## Capas vectoriales configurables

| N° | Capa | Tipo | Color típico |
|---|---|---|---|
| 1 | Hidrológico | Polígono | Azul brillante |
| 2 | Geomorfológico | Polígono | Naranja oscuro |
| 3 | Ecosistémico | Polígono | Verde oscuro |
| 4 | Cauce permanente | Polígono | Azul semi-transparente |
| 5 | Drenaje sencillo | Línea | Azul oscuro |
| 6 | Drenaje doble | Polígono | Azul oscuro |
| 7 | Municipios | Polígono | Negro (solo borde) |

---

## Parámetros clave

```python
EPSG_SALIDA = 9377          # MAGNA SIRGAS Origen Nacional
BUFFER_M    = 900           # metros
DPI_SALIDA  = 150
ANCHO_PX    = 2800
ALTO_PX     = 2400
BANDAS_RGB  = (6, 4, 1)     # B12, B8, B2 para cauce
# o (3, 2, 1) para RGB natural
GAMMA_RASTER   = 1.0
BRILLO_RASTER  = 0.0
DESAT_RASTER   = 0.0
DEM_HILLSHADE  = True
DEM_AZIMUTH    = 315
DEM_ALTITUD_LUZ = 40
```

---

## Salidas generadas

```
<DIR_SALIDA>/
└── MAPA_SENTINEL.png   ← o el nombre configurado
```

---

## Dependencias

```python
import geopandas as gpd, matplotlib.pyplot as plt
import matplotlib.patches as mpatches, matplotlib.lines as mlines
from matplotlib_scalebar.scalebar import ScaleBar
from pyproj import Transformer, CRS
import rasterio, numpy as np, os
```

---

## Insumos esperados

| Origen | Archivo | Uso |
|---|---|---|
| [Diagrama 09](./09_descargar_multibanda_s2.md) | GeoTIFF multibanda S2 | Fondo satelital. |
| [Diagrama 08](./08_geomorfologico.md) | DEM microrelieve | Fondo relieve opcional. |
| [Diagrama 11](./11_unir_componentes.md) | `cauce_permanente_reglas.shp` | Capa cauce permanente. |
| Usuario | GDB cartográfica (drenaje, municipios) | Contexto geográfico. |
| Usuario | `HIDROLOGICO.shp` | Capa de referencia para zoom. |

---

## Edición visual del diagrama

1. **[mermaid.live](https://mermaid.live)** — copiar/pegar el `.mmd`.
2. **[Mermaid Chart](https://www.mermaidchart.com)** — drag & drop.
3. **VS Code** + extensión `tomoyukim.vscode-mermaid-editor`.

Tras editar, sincroniza con:

```bash
python scripts/sync_mmd.py diagramas/14_salidas_graficas_compuestas.mmd
```

---

## Changelog

| Fecha | Cambio |
|---|---|
| 2026-05-27 | Creación inicial |
