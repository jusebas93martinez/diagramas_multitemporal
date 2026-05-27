# 10 — Clasificación de coberturas + extracción de ciénagas

Documenta el flujo del script
[`Codigos/10. COBERTURAS.py`](../Codigos/10.%20COBERTURAS.py),
que toma una imagen **Sentinel-2 multibanda** (6 bandas), calcula índices
espectrales, aplica un **modelo Random Forest pre-entrenado** para clasificar
**5 clases CORINE Land Cover**, y luego detecta **ciénagas** como componentes
conectados de agua + vegetación húmeda.

---

## Resumen del proceso

1. **Calcular índices:** a partir de 6 bandas (B2, B3, B4, B8, B11, B12)
   calcula NDVI, MNDWI y NDBI → imagen de 9 bandas.
2. **Clasificar con RF:** aplica el modelo entrenado en el
   [diagrama 12](./12_entrenar_modelo_coberturas.md), genera un raster
   clasificado (uint8), lo vectoriza a polígonos CLC y crea un mapa PNG.
3. **Extraer ciénagas:** detecta componentes conectados donde la clasificación
   es Agua (3) o Veg. Húmeda (4), filtra por área mínima, clasifica el tipo
   (Laguna / Cienaga_Abierta / Cienaga_Vegetada) y genera shapefile, raster,
   CSV y mapa PNG.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`10_coberturas.mmd`](./10_coberturas.mmd)

```mermaid
flowchart TD
    START([INICIO]) --> CFG

    CFG["Configurar:<br/>imagen S2 multibanda (6 bandas),<br/>modelo RF entrenado,<br/>directorio de salida,<br/>parámetros gráficos"] --> INDICES

    subgraph INDICES ["Paso 1: Calcular índices espectrales"]
      I1["Leer imagen Sentinel-2<br/>(6 bandas: B2,B3,B4,B8,B11,B12)"] --> I2
      I2["Aplicar factor de escala<br/>(0.0001 → reflectancia 0–1)"] --> I3
      I3["Calcular NDVI = (NIR-Red)/(NIR+Red)"] --> I4
      I4["Calcular MNDWI = (Green-SWIR1)/(Green+SWIR1)"] --> I5
      I5["Calcular NDBI = (SWIR1-NIR)/(SWIR1+NIR)"] --> I6
      I6["Máscara de píxeles inválidos<br/>(NaN o reflectancia = 0)"] --> I7
      I7["Guardar imagen intermedia<br/>9 bandas (6 + 3 índices)"] --> FIN_IND
      FIN_IND["Índices listos"]
    end

    INDICES --> CLASIF

    subgraph CLASIF ["Paso 2: Clasificar con Random Forest"]
      C1["Cargar modelo RF<br/>(.pkl entrenado)"] --> C2
      C2["Aplanar píxeles válidos<br/>→ matriz (n, 9)"] --> C3
      C3["Predecir clase para<br/>cada píxel válido"] --> C4
      C4["Reconstruir raster<br/>clasificado (uint8)"] --> C5
      C5["Guardar raster clasificado<br/>con colormap CLC embebido"] --> C6
      C6["Vectorizar a polígonos<br/>y asignar nombre CLC"] --> C7
      C7["Guardar shapefile<br/>Coberturas_CLC.shp"] --> C8
      C8["Generar mapa PNG<br/>con grilla EPSG:9377 y leyenda"] --> FIN_CLASIF
      FIN_CLASIF["Clasificación lista"]
    end

    CLASIF --> CIENAGAS

    subgraph CIENAGAS ["Paso 3: Extraer ciénagas"]
      Z1["Crear máscara combinada:<br/>Agua (clase 3) OR<br/>Veg. Húmeda (clase 4)"] --> Z2
      Z2["Etiquetar componentes<br/>conectados"] --> Z3
      Z3["Para cada componente:<br/>¿contiene al menos un píxel de agua?"} --> Z4
      Z4{"¿Área ≥ mínima<br/>configurada (ha)?"} -->|"Sí"| Z5
      Z4 -->|"No"| DESCARTAR
      DESCARTAR["Descartar componente"] --> Z4
      Z5["Calcular estadísticas:<br/>área total, agua, veg., porcentajes"] --> Z6
      Z6["Clasificar tipo:<br/>Laguna / Cienaga_Abierta /<br/>Cienaga_Vegetada"] --> Z7
      Z7["Guardar shapefile,<br/>raster, CSV y mapa PNG"] --> FIN_CIENAGAS
      FIN_CIENAGAS["Ciénagas listas"]
    end

    CIENAGAS --> RESUMEN
    RESUMEN["Mostrar resumen:<br/>N ciénagas, áreas totales<br/>por tipo y componente"] --> END_NODE

    END_NODE([FIN: coberturas CLC,<br/>ciénagas y mapas generados])

    style START     fill:#2E4057,color:#fff
    style END_NODE  fill:#2E4057,color:#fff

    style CFG       fill:#048A81,color:#fff
    style I1        fill:#048A81,color:#fff
    style I2        fill:#048A81,color:#fff
    style I3        fill:#048A81,color:#fff
    style I4        fill:#048A81,color:#fff
    style I5        fill:#048A81,color:#fff
    style I6        fill:#048A81,color:#fff
    style I7        fill:#048A81,color:#fff
    style C1        fill:#048A81,color:#fff
    style C2        fill:#048A81,color:#fff
    style C3        fill:#048A81,color:#fff
    style C4        fill:#048A81,color:#fff
    style C5        fill:#048A81,color:#fff
    style C6        fill:#048A81,color:#fff
    style C7        fill:#048A81,color:#fff
    style C8        fill:#048A81,color:#fff
    style Z1        fill:#048A81,color:#fff
    style Z2        fill:#048A81,color:#fff
    style Z3        fill:#048A81,color:#fff
    style Z5        fill:#048A81,color:#fff
    style Z6        fill:#048A81,color:#fff
    style Z7        fill:#048A81,color:#fff
    style RESUMEN   fill:#4CAF50,color:#fff

    style Z4        fill:#F4A261,color:#000

    style DESCARTAR fill:#607D8B,color:#fff
```

---

## Clases CORINE Land Cover

| Código | Clase | Color |
|---|---|---|
| 1 | 3.1.1 Bosque denso | Verde pastel |
| 2 | 1.1.2 Tejido urbano discontinuo | Rosa pastel |
| 3 | 5.1.1 Ríos y corrientes de agua | Azul pastel |
| 4 | 4.1.1 Humedales | Verde agua |
| 5 | 3.3.2 Zonas desnudas o degradadas | Amarillo pastel |

---

## Tipos de ciénaga detectados

| Tipo | Criterio |
|---|---|
| **Laguna** | > 70 % de agua |
| **Cienaga_Abierta** | 40–70 % de agua |
| **Cienaga_Vegetada** | < 40 % de agua |

---

## Parámetros configurables

```python
INPUT_IMAGE = r"...\S2_2025-12-06_T18PUQ_SR.tif"
MODEL_PATH  = r"...\Best_RandomForest_Model.pkl"
OUTPUT_DIR  = r"...\COBERTURAS"
SCALE_FACTOR        = 0.0001
MIN_AREA_CIENAGA_HA = 1.0
CLASE_AGUA          = 3
CLASE_VEG_HUMEDA    = 4
ZOOM                = 1.0
FIG_WIDTH  = 25.0
FIG_HEIGHT = 15.0
```

---

## Salidas generadas

```
<OUTPUT_DIR>/
├── Coberturas/
│   ├── Sentinel2_Clasificado.tif
│   ├── Coberturas_CLC.shp
│   └── Mapa_Coberturas.png
└── Cienagas/
    ├── Cienagas_Delimitadas.shp
    ├── Cienagas_Raster.tif
    ├── Cienagas_Estadisticas.csv
    └── Cienagas_Mapa.png
```

---

## Dependencias

```python
import os, numpy as np, rasterio, joblib, geopandas as gpd, pandas as pd
import matplotlib.pyplot as plt
from rasterio.features import shapes
from shapely.geometry import shape
from scipy import ndimage
from pyproj import Transformer
```

---

## Insumos esperados

| Origen | Archivo | Uso |
|---|---|---|
| [Diagrama 09](./09_descargar_multibanda_s2.md) | GeoTIFF multibanda S2 (6 bandas) | Imagen a clasificar. |
| [Diagrama 12](./12_entrenar_modelo_coberturas.md) | `Best_RandomForest_Model.pkl` | Modelo entrenado. |

---

## Edición visual del diagrama

1. **[mermaid.live](https://mermaid.live)** — copiar/pegar el `.mmd`.
2. **[Mermaid Chart](https://www.mermaidchart.com)** — drag & drop.
3. **VS Code** + extensión `tomoyukim.vscode-mermaid-editor`.

Tras editar, sincroniza con:

```bash
python scripts/sync_mmd.py diagramas/10_coberturas.mmd
```
