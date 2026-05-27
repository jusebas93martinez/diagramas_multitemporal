"""
PIPELINE DE CLASIFICACIÓN DE COBERTURAS SENTINEL-2
===================================================
Input : Imagen Sentinel-2 multibanda cruda (6 bandas: B2 B3 B4 B8 B11 B12)
Output: Shapefile coberturas CLC + Shapefile ciénagas + mapas PNG

Uso:
    1. Editar las 3 rutas en la sección CONFIGURACIÓN
    2. python pipeline_coberturas.py
"""

import os
import numpy as np
import rasterio
from rasterio.features import shapes
import joblib
import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch
from shapely.geometry import shape
from scipy import ndimage
from pyproj import Transformer

# =============================================================================
# CONFIGURACIÓN — Editar solo estas 3 rutas
# =============================================================================

INPUT_IMAGE = r"F:\SYNC\ANT\2026-1\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MULTIBANDA\S2_2025-12-06_T18PUQ_SR.tif"
MODEL_PATH  = r"F:\SYNC\ANT\CODIGO_MULTITEMPORAL\CODIGOS_FULL\MODELOS\Best_RandomForest_Model.pkl"
OUTPUT_DIR  = r"F:\SYNC\ANT\2026-1\20260423\LA CHIQUITA\COBERTURAS\2"

# Parámetros opcionales
SCALE_FACTOR        = 0.0001  # Reflectancia Sentinel-2: 0–10000 → 0.0–1.0
MIN_AREA_CIENAGA_HA = 1.0     # Área mínima de ciénaga a conservar (hectáreas)
CLASE_AGUA          = 3       # Código de clase Agua en el modelo entrenado
CLASE_VEG_HUMEDA    = 4       # Código de clase Humedal/Veg.Húmeda en el modelo
ZOOM                = 1.0     # Zoom del mapa PNG: 1.0 = imagen completa, 2.0 = zoom 2× desde el centro

# Tamaño máximo del mapa PNG en pulgadas (se respeta el aspecto del raster)
# A 300 dpi: 25 pulg = 7500 px, 15 pulg = 4500 px
FIG_WIDTH  = 25.0
FIG_HEIGHT = 15.0

# Tamaño de fuente (puntos)
FONT_GRID   = 12.0   # etiquetas de coordenadas de la grilla
FONT_LEGEND = 12.0   # texto de la leyenda (convenciones)

# =============================================================================
# NOMENCLATURA CORINE LAND COVER
# =============================================================================

CLC_MAPPING = {
    1: "3.1.1 Bosque denso",
    2: "1.1.2 Tejido urbano discontinuo",
    3: "5.1.1 Ríos y corrientes de agua",
    4: "4.1.1 Humedales",
    5: "3.3.2 Zonas desnudas o degradadas",
}

CLC_COLORS = {
    1: (134, 204, 134),   # Verde pastel — Bosque denso
    2: (255, 172, 172),   # Rosa pastel — Tejido urbano discontinuo
    3: (65, 160, 232),   # Azul pastel — Ríos y corrientes de agua
    4: (86, 190, 199),   # Verde agua pastel — Humedales
    5: (230, 230, 152),   # Amarillo pastel — Zonas desnudas o degradadas
}

# =============================================================================
# PASO 1 — Calcular índices espectrales (6 → 9 bandas)
# =============================================================================

def calcular_indices(input_path: str, output_path: str) -> None:
    """
    Lee imagen de 6 bandas Sentinel-2, calcula NDVI/MNDWI/NDBI
    y guarda un GeoTIFF de 9 bandas.
    """
    NAN_VAL = -1.0
    print("[1/3] Calculando índices espectrales (NDVI, MNDWI, NDBI)...")

    with rasterio.open(input_path) as src:
        profile = src.profile.copy()
        bands = [src.read(i + 1).astype(np.float32) * SCALE_FACTOR
                 for i in range(src.count)]

    B2, B3, B4, B8, B11, B12 = bands

    # Máscara de píxeles inválidos
    invalid = np.zeros_like(B2, dtype=bool)
    for b in bands:
        invalid |= np.isnan(b) | (b == 0)

    def safe_div(a, b):
        with np.errstate(divide='ignore', invalid='ignore'):
            out = np.full_like(a, np.nan, dtype=np.float32)
            ok = (b != 0) & ~np.isnan(a) & ~np.isnan(b)
            out[ok] = a[ok] / b[ok]
        return out

    NDVI  = safe_div(B8 - B4,  B8 + B4)
    MNDWI = safe_div(B3 - B11, B3 + B11)
    NDBI  = safe_div(B11 - B8, B11 + B8)

    for idx in [NDVI, MNDWI, NDBI]:
        idx[invalid] = np.nan

    all_bands = bands + [NDVI, MNDWI, NDBI]
    all_bands = [np.where(np.isnan(b), NAN_VAL, b) for b in all_bands]

    band_names = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'NDVI', 'MNDWI', 'NDBI']
    profile.update(count=9, dtype='float32', nodata=NAN_VAL, compress='deflate')

    with rasterio.open(output_path, 'w', **profile) as dst:
        for i, band in enumerate(all_bands):
            dst.write(band, i + 1)
            dst.set_band_description(i + 1, band_names[i])

    print(f"    Imagen con índices guardada: {output_path}")


# =============================================================================
# PASO 2 — Clasificar con modelo RF y exportar coberturas
# =============================================================================

def clasificar(image_path: str, model_path: str, output_dir: str):
    """
    Aplica el modelo Random Forest sobre la imagen de 9 bandas.
    Genera:
      - Sentinel2_Clasificado.tif  (raster con clases)
      - Coberturas_CLC.shp         (shapefile de coberturas)
      - Mapa_Coberturas.png        (mapa PNG)

    Retorna: (classified_raster, crs, transform, meta)
    """
    print("[2/3] Clasificando imagen con modelo Random Forest...")
    model = joblib.load(model_path)

    with rasterio.open(image_path) as src:
        raster_data = src.read()
        meta        = src.meta.copy()
        crs         = src.crs
        transform   = src.transform
        nodata_val  = src.nodata

    n_bands, height, width = raster_data.shape
    X = raster_data.reshape(n_bands, -1).T  # (pixels, bandas)

    # Máscara de píxeles válidos
    valid = np.ones(X.shape[0], dtype=bool)
    valid &= ~np.any(np.isnan(X), axis=1)
    if nodata_val is not None:
        valid &= ~np.any(X == nodata_val, axis=1)
    valid &= ~np.all(X == 0, axis=1)

    classified = np.zeros(height * width, dtype=np.uint8)
    classified[valid] = model.predict(X[valid]).astype(np.uint8)
    classified_raster = classified.reshape(height, width)

    # --- Raster clasificado ---
    meta_out = meta.copy()
    meta_out.update(dtype='uint8', count=1, nodata=0)
    raster_out = os.path.join(output_dir, "Sentinel2_Clasificado.tif")
    with rasterio.open(raster_out, "w", **meta_out) as dst:
        dst.write(classified_raster, 1)
        dst.write_colormap(1, {i: CLC_COLORS.get(i, (0, 0, 0)) for i in range(256)})

    # --- Shapefile de coberturas ---
    mask_shp = classified_raster != 0
    features = [
        {'properties': {'CLC_Code': int(v), 'Cobertura': CLC_MAPPING.get(int(v), "N/A")},
         'geometry': s}
        for s, v in shapes(classified_raster, mask=mask_shp, transform=transform)
    ]
    gdf = gpd.GeoDataFrame.from_features(features, crs=crs)
    shp_out = os.path.join(output_dir, "Coberturas_CLC.shp")
    gdf.to_file(shp_out)

    # --- Mapa PNG (pastel, apaisado, grilla EPSG:9377) ---
    n_clases = len(CLC_MAPPING)
    colors_list = [(0, 0, 0, 0)] + [
        (r / 255, g / 255, b / 255, 1.0)
        for r, g, b in (CLC_COLORS[i] for i in range(1, n_clases + 1))
    ]
    cmap = ListedColormap(colors_list)
    norm = BoundaryNorm(np.arange(0, n_clases + 2), cmap.N)

    h_px, w_px = classified_raster.shape
    cx, cy = w_px / 2.0, h_px / 2.0
    hw = w_px / (2.0 * ZOOM)
    hh = hw * (FIG_HEIGHT / FIG_WIDTH)  # recorte vertical ajustado al aspecto de la figura
    xlim_left, xlim_right = cx - hw, cx + hw
    ylim_top,  ylim_bot   = cy - hh, cy + hh

    fig, ax = plt.subplots(figsize=(FIG_WIDTH, FIG_HEIGHT))
    ax.imshow(classified_raster, cmap=cmap, norm=norm, origin='upper')
    ax.set_aspect('auto')
    ax.set_xlim(xlim_left, xlim_right)
    ax.set_ylim(ylim_bot, ylim_top)
    ax.axis('off')

    # Conversión píxel ↔ coordenadas nativas (raster north-up sin rotación)
    def _px2xy(col, row):
        return (transform.c + col * transform.a + row * transform.b,
                transform.f + col * transform.d + row * transform.e)

    def _xy2px(x, y):
        return (x - transform.c) / transform.a, (y - transform.f) / transform.e

    # Grilla de coordenadas EPSG:9377
    try:
        tr_fwd = Transformer.from_crs(crs.to_wkt(), 'EPSG:9377', always_xy=True)
        tr_inv = Transformer.from_crs('EPSG:9377', crs.to_wkt(), always_xy=True)
        use_grid = True
    except Exception:
        use_grid = False

    if use_grid:
        # Esquinas visibles → nativo → EPSG:9377
        x9_tl, y9_tl = tr_fwd.transform(*_px2xy(xlim_left,  ylim_top))
        x9_br, y9_br = tr_fwd.transform(*_px2xy(xlim_right, ylim_bot))
        x9_min, x9_max = min(x9_tl, x9_br), max(x9_tl, x9_br)
        y9_min, y9_max = min(y9_tl, y9_br), max(y9_tl, y9_br)

        # Intervalo «limpio» para ~5-7 líneas de grilla
        span = max(x9_max - x9_min, y9_max - y9_min)
        exp  = int(np.floor(np.log10(max(span, 1.0) / 5)))
        base = 10 ** exp
        interval = next(
            (m * base for m in (1, 2, 5, 10) if span / (m * base) <= 8),
            10 * base
        )

        def _fmt(v):
            return f'{v:,.0f}'   # número completo en metros con separador de miles

        N = 40   # puntos por línea (absorbe curvatura entre proyecciones)

        # Líneas verticales — Easting constante en EPSG:9377
        y_samp = np.linspace(y9_min, y9_max, N)
        for xg in np.arange(np.ceil(x9_min / interval) * interval, x9_max, interval):
            xn, yn = tr_inv.transform(np.full(N, xg), y_samp)
            col_v, row_v = _xy2px(xn, yn)
            ax.plot(col_v, row_v, color='#787878', lw=0.5, ls='--',
                    alpha=0.55, zorder=4, clip_on=True)
            col_b, _ = _xy2px(*tr_inv.transform(xg, y9_min))
            ax.annotate(_fmt(xg), xy=(col_b, ylim_bot),
                        xytext=(0, -4), textcoords='offset points',
                        ha='center', va='top', fontsize=FONT_GRID, rotation=0,
                        color='#3c3c3c', clip_on=False)

        # Líneas horizontales — Northing constante en EPSG:9377
        x_samp = np.linspace(x9_min, x9_max, N)
        for yg in np.arange(np.ceil(y9_min / interval) * interval, y9_max, interval):
            xn, yn = tr_inv.transform(x_samp, np.full(N, yg))
            col_v, row_v = _xy2px(xn, yn)
            ax.plot(col_v, row_v, color='#787878', lw=0.5, ls='--',
                    alpha=0.55, zorder=4, clip_on=True)
            _, row_l = _xy2px(*tr_inv.transform(x9_min, yg))
            ax.annotate(_fmt(yg), xy=(xlim_left, row_l),
                        xytext=(-5, 0), textcoords='offset points',
                        ha='right', va='center', fontsize=FONT_GRID,
                        color='#3c3c3c', clip_on=False)

        ax.text(0.005, 0.012,
                'Grilla: EPSG:9377 — Origen Único Nacional de Colombia (m)',
                transform=ax.transAxes, fontsize=FONT_GRID * 0.85, color='#555555',
                ha='left', va='bottom', style='italic')

    legend_elements = [
        Patch(facecolor=tuple(c / 255 for c in CLC_COLORS[i]), label=CLC_MAPPING[i])
        for i in range(1, n_clases + 1)
    ]
    ax.legend(handles=legend_elements, loc='upper right',
              title='Corine Land Cover', fontsize=FONT_LEGEND, title_fontsize=FONT_LEGEND,
              framealpha=0.92, facecolor='white', edgecolor='#999999')
    ax.set_title('MAPA DE COBERTURAS — CLASIFICACIÓN SENTINEL-2',
                 fontsize=FONT_LEGEND * 1.3, fontweight='bold', pad=12)

    fig.subplots_adjust(left=0.07, right=0.98, top=0.94, bottom=0.04)
    png_out = os.path.join(output_dir, 'Mapa_Coberturas.png')
    fig.savefig(png_out, dpi=300, bbox_inches='tight')
    plt.close(fig)

    print(f"    Raster clasificado : {raster_out}")
    print(f"    Shapefile coberturas: {shp_out}")
    print(f"    Mapa PNG           : {png_out}")

    return classified_raster, crs, transform, meta_out


# =============================================================================
# PASO 3 — Extraer ciénagas (agua + vegetación húmeda conectada)
# =============================================================================

def extraer_cienagas(classified_raster: np.ndarray, crs, transform,
                     output_dir: str) -> list:
    """
    Detecta ciénagas como componentes conectados de clases Agua + Veg.Húmeda.
    Genera:
      - Cienagas_Delimitadas.shp   (shapefile de ciénagas)
      - Cienagas_Raster.tif        (raster con ID de cada ciénaga)
      - Cienagas_Estadisticas.csv  (tabla de áreas)
      - Cienagas_Mapa.png          (mapa PNG)

    Retorna: lista de dicts con estadísticas por ciénaga.
    """
    print("[3/3] Extrayendo ciénagas...")

    pixel_size    = abs(transform[0])
    pixel_area_ha = (pixel_size ** 2) / 10000
    min_pixels    = int(MIN_AREA_CIENAGA_HA / pixel_area_ha)

    mask_comb = ((classified_raster == CLASE_AGUA) |
                 (classified_raster == CLASE_VEG_HUMEDA)).astype(np.uint8)
    labeled, n_comp = ndimage.label(mask_comb)
    mask_agua = classified_raster == CLASE_AGUA

    print(f"    Componentes conectados detectados: {n_comp}")

    cienagas_validas = []
    for i in range(1, n_comp + 1):
        comp = labeled == i
        if np.any(comp & mask_agua):
            total = int(np.sum(comp))
            agua  = int(np.sum(comp & mask_agua))
            if total >= min_pixels:
                cienagas_validas.append({'label': i, 'total': total,
                                         'agua': agua, 'veg': total - agua})

    print(f"    Ciénagas válidas (≥{MIN_AREA_CIENAGA_HA} ha): {len(cienagas_validas)}")

    # Raster de ciénagas y estadísticas
    cienagas_raster = np.zeros_like(classified_raster, dtype=np.uint8)
    cienagas_info   = []

    for idx, c in enumerate(cienagas_validas):
        cid      = idx + 1
        total_ha = c['total'] * pixel_area_ha
        agua_ha  = c['agua']  * pixel_area_ha
        veg_ha   = c['veg']   * pixel_area_ha

        cienagas_raster[labeled == c['label']] = cid
        cienagas_info.append({
            'Cienaga_ID':   cid,
            'Area_Total_ha': round(total_ha, 2),
            'Area_Agua_ha':  round(agua_ha,  2),
            'Area_VegHum_ha': round(veg_ha,  2),
            'Pct_Agua':      round(agua_ha / total_ha * 100, 1),
            'Pct_VegHum':    round(veg_ha  / total_ha * 100, 1),
        })
        print(f"      Ciénaga {cid}: {total_ha:.1f} ha "
              f"(Agua: {agua_ha:.1f}, Veg: {veg_ha:.1f})")

    # --- Vectorizar ---
    mask_v = cienagas_raster > 0
    polygons, ids = [], []
    for geom, val in shapes(cienagas_raster.astype(np.int32),
                            mask=mask_v, transform=transform):
        polygons.append(shape(geom))
        ids.append(int(val))

    gdf = gpd.GeoDataFrame({'geometry': polygons, 'Cienaga_ID': ids}, crs=crs)
    gdf = gdf.dissolve(by='Cienaga_ID', as_index=False)
    gdf = gdf.merge(pd.DataFrame(cienagas_info), on='Cienaga_ID')

    # Suavizar bordes pixelados
    buf = pixel_size * 0.5
    tol = pixel_size * 0.8

    def suavizar(geom):
        try:
            s = geom.buffer(buf).buffer(-buf).simplify(tol, preserve_topology=True)
            return s if s.is_valid else geom
        except Exception:
            return geom

    gdf['geometry'] = gdf['geometry'].apply(suavizar)

    def tipo_cienaga(row):
        if row['Pct_Agua'] > 70:
            return "Laguna"
        if row['Pct_Agua'] > 40:
            return "Cienaga_Abierta"
        return "Cienaga_Vegetada"

    gdf['Tipo'] = gdf.apply(tipo_cienaga, axis=1)

    # --- Guardar shapefile ---
    shp_out = os.path.join(output_dir, "Cienagas_Delimitadas.shp")
    gdf.to_file(shp_out)

    # --- Guardar raster de ciénagas ---
    raster_out = os.path.join(output_dir, "Cienagas_Raster.tif")
    profile = {
        'driver': 'GTiff', 'dtype': 'uint8', 'count': 1, 'nodata': 0,
        'width': cienagas_raster.shape[1], 'height': cienagas_raster.shape[0],
        'crs': crs, 'transform': transform,
    }
    with rasterio.open(raster_out, 'w', **profile) as dst:
        dst.write(cienagas_raster, 1)

    # --- CSV ---
    csv_out = os.path.join(output_dir, "Cienagas_Estadisticas.csv")
    pd.DataFrame(cienagas_info).to_csv(csv_out, index=False)

    # --- Mapa PNG ---
    n = len(cienagas_info)
    colors = ['white'] + [plt.cm.tab20(i % 20) for i in range(n)]
    cmap_c = ListedColormap(colors)
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.imshow(cienagas_raster, cmap=cmap_c, vmin=0, vmax=max(n, 1))
    ax.set_title(f'Ciénagas detectadas: {n}', fontsize=13, fontweight='bold')
    ax.axis('off')
    plt.tight_layout()
    png_out = os.path.join(output_dir, "Cienagas_Mapa.png")
    plt.savefig(png_out, dpi=150, bbox_inches='tight')
    plt.close()

    print(f"    Shapefile ciénagas : {shp_out}")
    print(f"    CSV estadísticas   : {csv_out}")
    print(f"    Mapa PNG           : {png_out}")

    return cienagas_info


# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    # Subdirectorios de salida
    dir_coberturas = os.path.join(OUTPUT_DIR, "Coberturas")
    dir_cienagas   = os.path.join(OUTPUT_DIR, "Cienagas")
    os.makedirs(dir_coberturas, exist_ok=True)
    os.makedirs(dir_cienagas,   exist_ok=True)

    # Archivo intermedio con índices (en carpeta raíz de OUTPUT_DIR)
    indices_path = os.path.join(OUTPUT_DIR, "multibanda_indices.tif")

    # ── Pipeline completo ──────────────────────────────────────────────────
    calcular_indices(INPUT_IMAGE, indices_path)

    classified_raster, crs, transform, meta = clasificar(
        indices_path, MODEL_PATH, dir_coberturas
    )

    cienagas_info = extraer_cienagas(
        classified_raster, crs, transform, dir_cienagas
    )

    # ── Resumen final ──────────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("RESUMEN FINAL")
    print("=" * 55)
    print(f"  Ciénagas detectadas : {len(cienagas_info)}")
    if cienagas_info:
        print(f"  Área total          : {sum(c['Area_Total_ha'] for c in cienagas_info):.1f} ha")
        print(f"    ├─ Agua           : {sum(c['Area_Agua_ha']  for c in cienagas_info):.1f} ha")
        print(f"    └─ Veg. Húmeda    : {sum(c['Area_VegHum_ha'] for c in cienagas_info):.1f} ha")
    print("=" * 55)
    print("Pipeline completado.")
