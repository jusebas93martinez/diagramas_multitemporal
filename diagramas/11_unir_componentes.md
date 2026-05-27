# 11 — Unión de componentes: cauce permanente preliminar

Documenta el flujo del script
[`Codigos/11 .UNIR_COMPONENTES.py`](../Codigos/11%20.UNIR_COMPONENTES.py),
que combina tres capas vectoriales (ecosistémica, geomorfológica e
hidrológica) mediante **reglas de negocio explícitas** para generar un
**polígono de cauce permanente preliminar**, suavizado y listo para revisión.

---

## Resumen del proceso

1. **Cargar** las tres capas de entrada y unificar CRS.
2. **Aplicar reglas de negocio:**
   - **Regla 1 (Agua prioritaria):** el componente hidrológico siempre se
     incluye completo.
   - **Regla 2 (Geomorfológico adaptativo):** el geomorfológico actúa como
     límite máximo, pero solo cuando está cerca de los otros componentes.
   - **Regla 3 (Prioridad):** Hidrológico > Ecosistémico > Geomorfológico.
   - **Regla 4 (Límite exterior):** si eco o hidro quedan fuera del geo, el
     límite es el más exterior de ellos (no el geomorfológico).
3. **Post-procesamiento:** eliminar huecos internos, suavizar geométricamente,
   simplificar y recalcular áreas.
4. **Generar gráfico de análisis 2×2** que muestra: capas de entrada, límite
   adaptativo, aplicación de reglas y cauce final.
5. **Guardar shapefile, PNG y TXT** con diagnóstico completo.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`11_unir_componentes.mmd`](./11_unir_componentes.mmd)

```mermaid
flowchart TD
    START([INICIO]) --> CFG

    CFG["Configurar rutas:<br/>ecosistémico, geomorfológico,<br/>hidrológico, salida,<br/>radio de suavizado"] --> CARGAR

    CARGAR["Cargar 3 shapefiles:<br/>• Ecosistémico<br/>• Geomorfológico<br/>• Hidrológico"] --> CRS
    CRS["Unificar CRS a la<br/>referencia ecosistémica"] --> PREP

    PREP["Disolver geometrías:<br/>unary_union por capa"] --> REGLAS

    subgraph REGLAS ["Aplicar reglas de negocio"]
      R1["REGLA 1: Agua prioritaria<br/>Hidrológico SIEMPRE incluido"] --> R2
      R2["REGLA 2: Geomorfológico<br/>como límite máximo adaptativo"] --> R3
      R3["REGLA 3: Prioridad<br/>Agua > Ecosistémico > Geomorfológico"] --> R4
      R4["REGLA 4: Límite exterior<br/>Si eco/hidro FUERA del geo,<br/>el más exterior define"] --> R5
      R5["Calcular:<br/>(Ecosistémico ∪ Hidrológico)<br/>∩ Geomorfológico"] --> FIN_REGLAS
      FIN_REGLAS["Cauce bruto calculado"]
    end

    REGLAS --> POST

    subgraph POST ["Post-procesamiento"]
      P1["Eliminar huecos internos<br/>(anillos interiores)"] --> P2
      P2["Suavizado geométrico:<br/>buffer+ / buffer-"] --> P3
      P3["Simplificación final<br/>(reduce vértices)"] --> P4
      P4["Re-eliminar huecos<br/>tras suavizado"] --> P5
      P5["Calcular área final (ha)"] --> P6
      P6["Guardar shapefile<br/>cauce permanente"] --> FIN_POST
      FIN_POST["Cauce final listo"]
    end

    POST --> GRAFICO

    subgraph GRAFICO ["Generar gráfico de análisis 2×2"]
      G1["Panel 1: Capas de entrada<br/>(eco + hidro + geo)"] --> G2
      G2["Panel 2: Límite adaptativo<br/>(geo cerca vs lejos)"] --> G3
      G3["Panel 3: Aplicación de reglas<br/>(interior + exterior)"] --> G4
      G4["Panel 4: Cauce permanente final"] --> G5
      G5["Guardar PNG de análisis"] --> FIN_GRAF
      FIN_GRAF["Gráfico listo"]
    end

    GRAFICO --> DIAGNOSTICO
    DIAGNOSTICO["Guardar TXT con diagnóstico<br/>de áreas y reglas aplicadas"] --> RESUMEN
    RESUMEN["Mostrar resumen de reglas<br/>y áreas finales en consola"] --> END_NODE

    END_NODE([FIN: cauce permanente<br/>+ gráfico + diagnóstico])

    style START     fill:#2E4057,color:#fff
    style END_NODE  fill:#2E4057,color:#fff

    style CFG       fill:#048A81,color:#fff
    style CARGAR    fill:#048A81,color:#fff
    style CRS       fill:#048A81,color:#fff
    style PREP      fill:#048A81,color:#fff
    style R1        fill:#048A81,color:#fff
    style R2        fill:#048A81,color:#fff
    style R3        fill:#048A81,color:#fff
    style R4        fill:#048A81,color:#fff
    style R5        fill:#048A81,color:#fff
    style P1        fill:#048A81,color:#fff
    style P2        fill:#048A81,color:#fff
    style P3        fill:#048A81,color:#fff
    style P4        fill:#048A81,color:#fff
    style P5        fill:#048A81,color:#fff
    style P6        fill:#048A81,color:#fff
    style G1        fill:#048A81,color:#fff
    style G2        fill:#048A81,color:#fff
    style G3        fill:#048A81,color:#fff
    style G4        fill:#048A81,color:#fff
    style G5        fill:#048A81,color:#fff
    style DIAGNOSTICO fill:#048A81,color:#fff
    style RESUMEN   fill:#4CAF50,color:#fff

    style FIN_REGLAS  fill:#4CAF50,color:#fff
    style FIN_POST    fill:#4CAF50,color:#fff
    style FIN_GRAF    fill:#4CAF50,color:#fff
```

---

## Reglas de negocio en detalle

| Regla | Descripción | Fórmula geométrica |
|---|---|---|
| **1** | El agua (hidrológico) siempre está dentro del cauce final. | `Hidro ⊂ Cauce` |
| **2** | El geomorfológico es límite máximo solo cuando está cerca. | `Geo ∩ (Eco ∪ Hidro)` |
| **3** | Prioridad: agua > ecosistémico > geomorfológico. | Orden de decisión |
| **4** | Si eco/hidro se salen del geo, el más exterior gana. | `Cauce = (Eco ∪ Hidro) ∩ Geo` con excepciones |

La fórmula final implementada es:

```
Cauce = (Ecosistémico ∪ Hidrológico) ∩ Geomorfológico
```

Con la **Regla 4** como excepción automática cuando hay componentes fuera del
geomorfológico.

---

## Parámetros configurables

```python
RADIO_SUAVIZADO_GEO     = 15   # metros
TOLERANCIA_SIMPLIFY_GEO = 5    # metros
RADIO_SUAVIZADO         = 15   # metros
TOLERANCIA_SIMPLIFY     = 5    # metros
```

---

## Salidas generadas

```
<CARPETA_SALIDA>/
├── cauce_permanente_reglas.shp
├── analisis_cauce_reglas.png   ← gráfico 2×2
└── diagnostico_reglas.txt      ← áreas y reglas aplicadas
```

---

## Dependencias

```python
import geopandas as gpd, os, numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.ops import unary_union
from shapely.geometry import MultiPolygon, Polygon
```

---

## Insumos esperados

| Origen | Archivo | Uso |
|---|---|---|
| [Diagrama 10](./10_coberturas.md) | `coberturas.shp` (ciénagas) | Componente ecosistémico. |
| [Diagrama 08](./08_geomorfologico.md) | `poligono_geomorfologico_...shp` | Componente geomorfológico. |
| Usuario | `HIDROLOGICO.shp` | Componente hidrológico (límite de agua). |

---

## Edición visual del diagrama

1. **[mermaid.live](https://mermaid.live)** — copiar/pegar el `.mmd`.
2. **[Mermaid Chart](https://www.mermaidchart.com)** — drag & drop.
3. **VS Code** + extensión `tomoyukim.vscode-mermaid-editor`.

Tras editar, sincroniza con:

```bash
python scripts/sync_mmd.py diagramas/11_unir_componentes.mmd
```

---

## Changelog

| Fecha | Cambio |
|---|---|
| 2026-05-27 | Creación inicial |
