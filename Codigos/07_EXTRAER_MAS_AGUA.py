# -*- coding: utf-8 -*-
"""
EXTRACCION DE MASAS DE AGUA GRANDES + VECTORIZACION CON SUAVIZADO
==================================================================
Flujo completo en un solo script:
  1. Lee raster binario de agua (union SAR + MNDWI)
  2. Erosiona para separar componentes conectados
  3. Filtra componentes por area minima
  4. Restaura tamanio con dilatacion -> TIF intermedio
  5. Vectoriza raster a poligonos
  6. Filtra por area minima
  7. Suavizado iterativo (buffer+ / buffer-)
  8. Guarda shapefile final suavizado
"""

import os
import numpy as np
import rasterio
from scipy import ndimage
import geopandas as gpd
from rasterio.features import shapes as rio_shapes

# ============================================================
# PARAMETROS - CONFIGURA AQUI
# ============================================================

# Raster binario de entrada (agua=1, no-agua=0)
RUTA_ENTRADA = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260325\UNION_SAR_MNDWI\union_SAR_MNDWI_binario.tif"

# Carpeta de salida (se deriva automaticamente del raster de entrada)
CARPETA_SALIDA = os.path.dirname(RUTA_ENTRADA)

# --- EXTRACCION DE COMPONENTES ---
ITERACIONES_EROSION   = 1        # Erosion para separar componentes (1-2)
AREA_MINIMA_PIXELES   = 20  # Pixeles minimos para considerar masa de agua grande
GUARDAR_TIF_INTERMEDIO = True    # Guarda el TIF antes de vectorizar (util para revision)
GUARDAR_COMPONENTES_SEPARADOS = False  # True para guardar cada componente por separado

# --- VECTORIZACION Y SUAVIZADO ---
MIN_AREA_M2           = 10   # Area minima de poligonos a conservar (m2)
ITERACIONES_SUAVIZADO = 1        # Iteraciones de suavizado (mas = bordes mas suaves)
BUFFER_POR_ITERACION  = 1       # Metros de buffer por iteracion de suavizado
SIMPLIFY_INICIAL      = 1.0      # Simplificacion antes del suavizado (metros)
SIMPLIFY_FINAL        = 5.0      # Simplificacion despues del suavizado (metros)
USAR_SUAVIZADO_EXTRA  = True     # Suavizado extra con erosion-dilatacion
BUFFER_SUAVIZADO_EXTRA = 1    # Metros para suavizado extra

# ============================================================
# UTILIDADES
# ============================================================

def utm_epsg_from_lonlat(lon, lat):
    zone = int((lon + 180.0) // 6) + 1
    return f"EPSG:{32600 + zone}" if lat >= 0 else f"EPSG:{32700 + zone}"

def make_valid(gdf):
    gdf = gdf.copy()
    gdf['geometry'] = gdf.buffer(0)
    return gdf

def suavizar_iterativo(gdf, iteraciones, buffer_dist):
    gdf_result = gdf.copy()
    for i in range(iteraciones):
        print(f"    Iteracion {i+1}/{iteraciones}...")
        gdf_result['geometry'] = gdf_result.geometry.buffer(buffer_dist)
        gdf_result = make_valid(gdf_result)
        gdf_result['geometry'] = gdf_result.geometry.buffer(-buffer_dist)
        gdf_result = make_valid(gdf_result)
        gdf_result = gdf_result[~gdf_result.geometry.is_empty].copy()
    return gdf_result

def suavizar_con_erosion_dilatacion(gdf, buffer_dist):
    gdf_result = gdf.copy()
    gdf_result['geometry'] = gdf_result.geometry.buffer(-buffer_dist)
    gdf_result = make_valid(gdf_result)
    gdf_result = gdf_result[~gdf_result.geometry.is_empty].copy()
    gdf_result['geometry'] = gdf_result.geometry.buffer(buffer_dist)
    gdf_result = make_valid(gdf_result)
    return gdf_result

# ============================================================
# PASO 1: EXTRACCION DE MASAS DE AGUA GRANDES
# ============================================================
print("=" * 60)
print("PASO 1: EXTRACCION DE MASAS DE AGUA GRANDES")
print("=" * 60)
print(f"Entrada:      {os.path.basename(RUTA_ENTRADA)}")
print(f"Erosion:      {ITERACIONES_EROSION} iteracion(es)")
print(f"Area minima:  {AREA_MINIMA_PIXELES:,} pixeles")

if not os.path.exists(RUTA_ENTRADA):
    raise FileNotFoundError(f"No se encuentra el raster: {RUTA_ENTRADA}")

with rasterio.open(RUTA_ENTRADA) as src:
    datos     = src.read(1)
    perfil    = src.profile.copy()
    transform = src.transform
    crs_raster = src.crs

agua = (datos == 1).astype(np.uint8)
pixeles_originales = int(np.sum(agua))
print(f"Pixeles agua inicial: {pixeles_originales:,}")

estructura = ndimage.generate_binary_structure(2, 2)

# Erosion
print(f"Aplicando erosion ({ITERACIONES_EROSION} iteracion(es))...")
agua_erosionada = ndimage.binary_erosion(
    agua, structure=estructura, iterations=ITERACIONES_EROSION
).astype(np.uint8)
print(f"  Pixeles tras erosion: {int(np.sum(agua_erosionada)):,}")

# Etiquetado de componentes conectados
print("Etiquetando componentes...")
etiquetas, num_componentes = ndimage.label(agua_erosionada)
print(f"  Componentes encontrados: {num_componentes}")

tamanios = np.array(ndimage.sum(agua_erosionada, etiquetas, range(1, num_componentes + 1)))
indices_ord = np.argsort(tamanios)[::-1]

print(f"  Top 10 por area:")
res_px = perfil.get('transform', transform)[0]  # tamanio de pixel en metros
for i, idx in enumerate(indices_ord[:10]):
    px  = int(tamanios[idx])
    ha  = px * (abs(res_px) ** 2) / 10000
    print(f"    {i+1}. ID {idx+1}: {px:,} px  (~{ha:.1f} ha)")

# Filtrar componentes grandes
ids_grandes = [idx + 1 for idx in range(num_componentes) if tamanios[idx] >= AREA_MINIMA_PIXELES]
print(f"  Componentes >= {AREA_MINIMA_PIXELES:,} px: {len(ids_grandes)}")

if ids_grandes:
    mascara_grandes = np.isin(etiquetas, ids_grandes).astype(np.uint8)
else:
    mascara_grandes = np.zeros_like(agua_erosionada, dtype=np.uint8)
    print("  AVISO: Ningun componente supera el umbral. Reduce AREA_MINIMA_PIXELES.")

# Dilatacion para restaurar tamanio
print(f"Restaurando tamanio (dilatacion {ITERACIONES_EROSION} iteracion(es))...")
agua_final = ndimage.binary_dilation(
    mascara_grandes, structure=estructura, iterations=ITERACIONES_EROSION
).astype(np.uint8)
agua_final = (agua_final & agua).astype(np.uint8)   # no expandir fuera del agua real
pixeles_finales = int(np.sum(agua_final))
print(f"  Pixeles agua final: {pixeles_finales:,}")

# Guardar TIF intermedio (opcional, pero util para revision)
nombre_tif = f"masas_agua_grandes_area{AREA_MINIMA_PIXELES}.tif"
ruta_tif   = os.path.join(CARPETA_SALIDA, nombre_tif)

if GUARDAR_TIF_INTERMEDIO:
    perfil_tif = perfil.copy()
    perfil_tif.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=0)
    with rasterio.open(ruta_tif, 'w', **perfil_tif) as dst:
        dst.write(agua_final, 1)
    print(f"  TIF intermedio guardado: {nombre_tif}")

# Componentes individuales (opcional)
if GUARDAR_COMPONENTES_SEPARADOS and ids_grandes:
    carpeta_comp = os.path.join(CARPETA_SALIDA, "componentes_individuales")
    os.makedirs(carpeta_comp, exist_ok=True)
    perfil_comp = perfil.copy()
    perfil_comp.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=0)
    for i, id_comp in enumerate(ids_grandes):
        comp = ndimage.binary_dilation(
            (etiquetas == id_comp).astype(np.uint8),
            structure=estructura, iterations=ITERACIONES_EROSION
        ).astype(np.uint8)
        comp = (comp & agua).astype(np.uint8)
        px_comp = int(tamanios[id_comp - 1])
        nombre_comp = f"componente_{i+1:03d}_id{id_comp}_px{px_comp}.tif"
        with rasterio.open(os.path.join(carpeta_comp, nombre_comp), 'w', **perfil_comp) as dst:
            dst.write(comp, 1)
    print(f"  Componentes individuales: {carpeta_comp}")

# ============================================================
# PASO 2: VECTORIZACION Y SUAVIZADO
# ============================================================
print()
print("=" * 60)
print("PASO 2: VECTORIZACION Y SUAVIZADO")
print("=" * 60)
print(f"Iteraciones suavizado: {ITERACIONES_SUAVIZADO}")
print(f"Buffer por iteracion:  {BUFFER_POR_ITERACION} m")
print(f"Simplificacion final:  {SIMPLIFY_FINAL} m")
print(f"Area minima poligono:  {MIN_AREA_M2} m2")

# Usar array en memoria (agua_final) directamente, sin releer el TIF
mask_bool = (agua_final == 1)

results = [
    {'properties': {'raster_val': v}, 'geometry': s}
    for (s, v) in rio_shapes(agua_final, mask=mask_bool, transform=transform)
]

if not results:
    print("No se encontraron areas para vectorizar. Revisa AREA_MINIMA_PIXELES.")
else:
    gdf = gpd.GeoDataFrame.from_features(results, crs=crs_raster)
    print(f"\n[1/5] Vectorizacion: {len(gdf)} poligonos iniciales")

    # Reproyectar a UTM si es geografico
    if gdf.crs is None or getattr(gdf.crs, 'is_geographic', False):
        bounds    = gdf.total_bounds
        cen_lon   = (bounds[0] + bounds[2]) / 2.0
        cen_lat   = (bounds[1] + bounds[3]) / 2.0
        epsg_utm  = utm_epsg_from_lonlat(cen_lon, cen_lat)
        print(f"[2/5] Reproyectando a {epsg_utm}...")
        gdf = gdf.to_crs(epsg_utm)
    else:
        print(f"[2/5] CRS ya en metros ({gdf.crs.to_string()})")

    # Filtrar por area minima
    gdf['area_m2'] = gdf.geometry.area
    gdf = gdf[gdf['area_m2'] >= MIN_AREA_M2].copy()
    print(f"[3/5] Filtro area minima ({MIN_AREA_M2} m2): {len(gdf)} poligonos")

    if gdf.empty:
        print("Ningun poligono supero el umbral de area. Reduce MIN_AREA_M2.")
    else:
        # Simplificacion inicial
        print(f"[4/5] Simplificacion inicial ({SIMPLIFY_INICIAL} m)...")
        gdf['geometry'] = gdf.geometry.simplify(SIMPLIFY_INICIAL, preserve_topology=True)
        gdf = make_valid(gdf)

        # Suavizado iterativo
        print(f"[5/5] Suavizado iterativo ({ITERACIONES_SUAVIZADO} iteraciones x {BUFFER_POR_ITERACION} m)...")
        gdf = suavizar_iterativo(gdf, ITERACIONES_SUAVIZADO, BUFFER_POR_ITERACION)

        if USAR_SUAVIZADO_EXTRA:
            print(f"  Suavizado extra ({BUFFER_SUAVIZADO_EXTRA} m)...")
            gdf = suavizar_con_erosion_dilatacion(gdf, BUFFER_SUAVIZADO_EXTRA)

        print(f"  Simplificacion final ({SIMPLIFY_FINAL} m)...")
        gdf['geometry'] = gdf.geometry.simplify(SIMPLIFY_FINAL, preserve_topology=True)
        gdf = make_valid(gdf)
        gdf = gdf[~gdf.geometry.is_empty].copy()

        if gdf.empty:
            print("Los poligonos quedaron vacios tras el suavizado. Reduce los buffers.")
        else:
            gdf['area_m2'] = gdf.geometry.area
            gdf['area_ha'] = gdf['area_m2'] / 10000

            nombre_shp = 'union_SAR_MNDWI_suavizado.shp'
            ruta_shp   = os.path.join(CARPETA_SALIDA, nombre_shp)
            gdf.to_file(ruta_shp, driver='ESRI Shapefile')

            # ============================================================
            # RESUMEN FINAL
            # ============================================================
            print()
            print("=" * 60)
            print("RESUMEN FINAL")
            print("=" * 60)
            print(f"Pixeles agua original:   {pixeles_originales:,}")
            print(f"Pixeles agua extraidos:  {pixeles_finales:,}")
            print(f"Componentes grandes:     {len(ids_grandes)}")
            print(f"Poligonos finales:       {len(gdf)}")
            print(f"Area total:              {gdf['area_ha'].sum():.2f} ha")
            print()
            if GUARDAR_TIF_INTERMEDIO:
                print(f"TIF intermedio: {ruta_tif}")
            print(f"Shapefile final: {ruta_shp}")
            print("=" * 60)
