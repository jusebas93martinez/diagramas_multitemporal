# 00 — Descarga Raster TRMM / GPM

Documenta el flujo del script
[`Codigos/00._Descarga_Raster_TRMM.py`](../Codigos/00._Descarga_Raster_TRMM.py),
encargado de descargar **precipitación mensual** para Colombia desde Google
Earth Engine (GEE) entre **1997-08 y 2026-04**, normalizada a unidades de
mm/mes y resolución de 10 km.

---

## Resumen del proceso

1. **Autenticación** e inicialización de GEE (proyecto `precipitaciones-459216`).
2. **Área de interés:** Colombia, desde `FAO/GAUL/2015/level0`.
3. **Bucle** anidado año → mes en el rango `1997-08` a `2026-04`.
4. **Selección de colección** según el año:
   - `year <= 2014` → `TRMM/3B43V7`
   - `year >= 2015` → `NASA/GPM_L3/IMERG_MONTHLY_V07`
5. **Normalización de unidades:** la tasa `mm/hr` se multiplica por
   `dias_mes * 24` para obtener el acumulado `mm/mes`.
6. **Exportación:** GeoTIFF a 10 km (EPSG:4326) vía `getDownloadURL` y
   `requests`.
7. Se omiten los meses **sin datos** y los archivos que **ya existen** en
   disco.

---

## Diagrama de flujo

> 📝 **Fuente editable:** [`00_descarga_raster_trmm_gpm.mmd`](./00_descarga_raster_trmm_gpm.mmd)
> — el bloque que sigue es una copia para que GitHub lo renderice. Si editas
> el `.mmd`, pega aquí el contenido actualizado (ver sección
> [Edición visual del diagrama](#edición-visual-del-diagrama)).

```mermaid
flowchart TD
    S1([INICIO]) --> S2
    S2["Autenticarse en<br/>Google Earth Engine"] --> S3
    S3["Cargar el área de estudio: Colombia<br/>y obtener su rectángulo envolvente"] --> S5
    S5["Definir parámetros:<br/>• Rango temporal: ago-1997 a abr-2026<br/>• Resolución: 10 km por píxel<br/>• Carpeta local de salida"] --> S6
    S6["Crear la carpeta de salida<br/>si todavía no existe"] --> L1
    L1[/"Para cada año<br/>desde 1997 hasta 2026"/] --> S7
    S7["Determinar el primer y último mes<br/>que corresponden a este año<br/>(el rango se acorta en años extremos)"] --> L2
    L2[/"Para cada mes del año<br/>dentro del rango calculado"/] --> S8
    S8["Calcular las fechas de inicio y fin<br/>del mes y cuántos días tiene"] --> D1
    D1{"¿El año es 2014<br/>o anterior?"}
    D1 -->|"Sí"| C1["Usar colección satelital TRMM<br/>(precipitación en mm/hora)"]
    D1 -->|"No"| C2["Usar colección satelital GPM IMERG mensual<br/>(precipitación en mm/hora)"]
    C1 --> S9
    C2 --> S9
    S9["Filtrar la colección al mes actual"] --> D2
    D2{"¿Existen datos satelitales<br/>para este mes?"}
    D2 -->|"No"| SK1["Reportar mes sin datos<br/>y pasar al siguiente mes"]
    D2 -->|"Sí"| S10
    S10["Convertir la tasa de precipitación<br/>(mm/hora) en acumulado del mes (mm)<br/>multiplicando por las horas del mes"] --> S11
    S11["Construir el nombre del archivo<br/>de salida para este mes"] --> D3
    D3{"¿El archivo del mes<br/>ya está descargado?"}
    D3 -->|"Sí"| SK2["Omitir descarga<br/>(el mes ya estaba listo)"]
    D3 -->|"No"| T1
    T1["Solicitar a Google Earth Engine<br/>una URL de descarga del raster<br/>(formato GeoTIFF, EPSG:4326, 10 km)"] --> S12
    S12["Descargar el archivo<br/>desde la URL"] --> D4
    D4{"¿La descarga vino<br/>comprimida en ZIP?"}
    D4 -->|"Sí"| Z1["Descomprimir el ZIP<br/>y extraer el GeoTIFF"]
    D4 -->|"No"| Z2["Guardar el GeoTIFF<br/>directamente"]
    Z1 --> OK
    Z2 --> OK
    OK["Mes descargado y<br/>guardado correctamente"]

    S12 -.->|"Si ocurre un error"| ERR["Reportar error de descarga<br/>(sin detener el proceso)"]

    OK  --> L2
    ERR --> L2
    SK1 --> L2
    SK2 --> L2

    L2 -.->|"fin del mes"| L1
    L1 -.->|"fin del año"| FIN
    FIN([FIN:<br/>todos los meses procesados])

    style S1   fill:#2E4057,color:#fff
    style FIN  fill:#2E4057,color:#fff

    style S2   fill:#048A81,color:#fff
    style S3   fill:#048A81,color:#fff
    style S5   fill:#048A81,color:#fff
    style S6   fill:#048A81,color:#fff
    style S7   fill:#048A81,color:#fff
    style S8   fill:#048A81,color:#fff
    style S9   fill:#048A81,color:#fff
    style S10  fill:#048A81,color:#fff
    style S11  fill:#048A81,color:#fff
    style S12  fill:#048A81,color:#fff
    style T1   fill:#048A81,color:#fff
    style Z1   fill:#048A81,color:#fff
    style Z2   fill:#048A81,color:#fff

    style L1   fill:#54478C,color:#fff
    style L2   fill:#54478C,color:#fff

    style D1   fill:#F4A261,color:#000
    style D2   fill:#F4A261,color:#000
    style D3   fill:#F4A261,color:#000
    style D4   fill:#F4A261,color:#000

    style C1   fill:#2196F3,color:#fff
    style C2   fill:#9C27B0,color:#fff

    style SK1  fill:#E63946,color:#fff
    style SK2  fill:#607D8B,color:#fff
    style ERR  fill:#E63946,color:#fff

    style OK   fill:#4CAF50,color:#fff
```

---

## Notas técnicas

### Colecciones GEE utilizadas

| Periodo cubierto | Colección | Banda usada | Unidad nativa |
|---|---|---|---|
| `year <= 2014` | [`TRMM/3B43V7`](https://developers.google.com/earth-engine/datasets/catalog/TRMM_3B43V7) | `precipitation` | mm/hr |
| `year >= 2015` | [`NASA/GPM_L3/IMERG_MONTHLY_V07`](https://developers.google.com/earth-engine/datasets/catalog/NASA_GPM_L3_IMERG_MONTHLY_V07) | `precipitation` | mm/hr |

> ⚠️ **Importante:** el script usa la versión **mensual** de IMERG
> (`IMERG_MONTHLY_V07`), no la diaria. Ambas colecciones devuelven la banda
> `precipitation` en `mm/hr`, por eso aplica la misma conversión.

### Conversión de unidades

```
mm_mes = (mm/hr) * dias_del_mes * 24
```

`dias_del_mes` se obtiene con `calendar.monthrange(year, month)[1]` (maneja
febrero y años bisiestos automáticamente).

### Parámetros de exportación

| Parámetro | Valor |
|---|---|
| `scale` | `10000` metros (10 km) |
| `crs` | `EPSG:4326` |
| `region` | `geometry.getInfo()['coordinates']` (bounds de Colombia) |
| `format` | `GEO_TIFF` |

### Mecanismos de robustez

- **`coll_period.size() == 0`** → se omite el mes con un mensaje
  `❌ No hay datos`.
- **`os.path.exists(out_path)`** → idempotencia: si el TIF ya existe se omite
  la descarga (`👍 ya existe`).
- **`try/except`** envolviendo `getDownloadURL` + `requests.get` → captura
  cualquier error de red o del servidor de GEE sin detener el bucle
  (`⛔ Error al procesar`).
- **Detección automática de ZIP** (`zipfile.is_zipfile`) → algunos endpoints
  de GEE devuelven el `.tif` empaquetado en `.zip`; el script extrae el primer
  `.tif` que encuentra.

### Estructura de salida

```
precipitacion_mensual_colombia_10km/
├── precip_mensual_1997_08_colombia_10km.tif
├── precip_mensual_1997_09_colombia_10km.tif
├── ...
├── precip_mensual_2014_12_colombia_10km.tif   ← último mes TRMM
├── precip_mensual_2015_01_colombia_10km.tif   ← primer mes GPM
├── ...
└── precip_mensual_2026_04_colombia_10km.tif
```

---

## Dependencias

```python
import ee                       # earthengine-api
import requests                 # descarga HTTP
import os, io, zipfile          # stdlib
from calendar import monthrange # dias del mes
```

Instalación:

```bash
pip install earthengine-api requests
earthengine authenticate
```

---

## Edición visual del diagrama

El archivo [`00_descarga_raster_trmm_gpm.mmd`](./00_descarga_raster_trmm_gpm.mmd)
contiene **solo el código Mermaid** (sin Markdown alrededor) para que puedas
editarlo en herramientas visuales:

### Opción 1 — mermaid.live (rápido, sin cuenta)

1. Abre https://mermaid.live
2. En el panel izquierdo, **borra el contenido por defecto**.
3. Abre `00_descarga_raster_trmm_gpm.mmd` en cualquier editor → copia todo →
   pégalo en mermaid.live.
4. La preview del centro se actualiza en vivo.
5. Para guardar los cambios: copia el código modificado de vuelta al `.mmd` y
   actualiza también el bloque ```` ```mermaid ```` de este `.md` para que
   GitHub lo renderice.

### Opción 2 — Mermaid Chart (drag & drop visual)

1. Crea cuenta gratis en https://www.mermaidchart.com
2. **New diagram → Import → Mermaid file** → sube el `.mmd`.
3. Cambia a modo *Visual editor* para mover nodos con el mouse.
4. Cuando termines: **Export → Mermaid code** → reemplaza el `.mmd` y el
   bloque en este `.md`.

### Opción 3 — VS Code (preview lateral local)

1. Instala la extensión recomendada
   [`tomoyukim.vscode-mermaid-editor`](https://marketplace.visualstudio.com/items?itemName=tomoyukim.vscode-mermaid-editor).
2. Abre el `.mmd` → `Ctrl+Shift+P` → **Mermaid Editor: Preview to the Side**.
3. Edita el `.mmd` y ve los cambios al instante.

> 🔁 **Importante:** mientras no haya un script de sincronización, debes
> mantener el `.mmd` y el bloque ```` ```mermaid ```` de este `.md`
> **idénticos**. El `.mmd` es la fuente editable; el bloque del `.md` es la
> copia que GitHub renderiza.

---

## Changelog

| Fecha | Cambio |
|---|---|
| 2026-05-27 | Creación inicial |
