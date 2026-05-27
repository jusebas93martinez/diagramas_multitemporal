# -*- coding: utf-8 -*-
"""
UNION SAR + MNDWI -> EXTRACCION DE MASAS GRANDES -> VECTORIZACION CON SUAVIZADO
================================================================================
Flujo completo en un solo script:
  1. Une rasters binarios SAR + MNDWI (OR logico)
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
from rasterio.warp import reproject, Resampling
from scipy import ndimage
import geopandas as gpd
from rasterio.features import shapes as rio_shapes

# ============================================================
# PARAMETROS - CONFIGURA AQUI
# ============================================================

# --- PASO 1: UNION SAR + MNDWI ---
ruta_sar    = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\SAR\S1_ASCENDING_2024_09_COMPOSITE_MERGE.tif"
ruta_mndwi  = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MEJORES_POR_AÑO\SALIDAS_humedo_MNDWI\FINALES\final_MNDWI_binario_freq2_suavizado.tif"
carpeta_salida = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\UNION_SAR_MNDWI"
os.makedirs(carpeta_salida, exist_ok=True)
archivo_union = os.path.join(carpeta_salida, 'union_SAR_MNDWI_binario.tif')

# --- PASO 2: EXTRACCION DE COMPONENTES ---
ITERACIONES_EROSION           = 1        # Erosion para separar componentes (1-2)
AREA_MINIMA_PIXELES           = 200   # Pixeles minimos para considerar masa de agua grande
GUARDAR_TIF_INTERMEDIO        = True     # Guarda el TIF antes de vectorizar
GUARDAR_COMPONENTES_SEPARADOS = False    # True para guardar cada componente por separado

# --- PASO 3: VECTORIZACION Y SUAVIZADO ---
MIN_AREA_M2           = 1000    # Area minima de poligonos a conservar (m2)
ITERACIONES_SUAVIZADO = 8       # Iteraciones de suavizado (mas = bordes mas suaves)
BUFFER_POR_ITERACION  = 10      # Metros de buffer por iteracion de suavizado
SIMPLIFY_INICIAL      = 3.0     # Simplificacion antes del suavizado (metros)
SIMPLIFY_FINAL        = 5.0     # Simplificacion despues del suavizado (metros)
USAR_SUAVIZADO_EXTRA  = True    # Suavizado extra con erosion-dilatacion
BUFFER_SUAVIZADO_EXTRA = 5.0    # Metros para suavizado extra

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
# PASO 1: UNION SAR + MNDWI
# ============================================================
print("=" * 60)
print("PASO 1: UNION TIF BINARIOS SAR + MNDWI")
print("=" * 60)
print(f"   Salida: {carpeta_salida}")

if not os.path.exists(ruta_sar):
    raise FileNotFoundError(f"No se encuentra SAR en:\n   {ruta_sar}")
if not os.path.exists(ruta_mndwi):
    raise FileNotFoundError(f"No se encuentra MNDWI en:\n   {ruta_mndwi}")

with rasterio.open(ruta_sar) as src_sar:
    with rasterio.open(ruta_mndwi) as src_mndwi:

        perfil_referencia = src_sar.profile.copy()
        sar_data = src_sar.read(1).astype('uint8')

        print(f"\n   SAR:   {src_sar.width} x {src_sar.height} px  |  CRS: {src_sar.crs}")
        print(f"   MNDWI: {src_mndwi.width} x {src_mndwi.height} px  |  CRS: {src_mndwi.crs}")

        if src_sar.crs != src_mndwi.crs or src_sar.shape != src_mndwi.shape or src_sar.bounds != src_mndwi.bounds:
            print("\n   Reproyectando MNDWI a la geometria de SAR...")
            mndwi_reproyectado = np.zeros(sar_data.shape, dtype='uint8')
            reproject(
                source=rasterio.band(src_mndwi, 1),
                destination=mndwi_reproyectado,
                src_transform=src_mndwi.transform,
                src_crs=src_mndwi.crs,
                dst_transform=src_sar.transform,
                dst_crs=src_sar.crs,
                resampling=Resampling.nearest
            )
            mndwi_data = mndwi_reproyectado
            print("   Reproyeccion completada.")
        else:
            mndwi_data = src_mndwi.read(1).astype('uint8')
            print("\n   Los rasters tienen la misma geometria (no requiere reproyeccion).")

        union_data = np.logical_or(sar_data == 1, mndwi_data == 1).astype('uint8')

        pixeles_sar   = np.sum(sar_data == 1)
        pixeles_mndwi = np.sum(mndwi_data == 1)
        pixeles_union = np.sum(union_data == 1)
        total_pixeles = union_data.size
        print(f"\n   Pixeles SAR:   {pixeles_sar:,} ({(pixeles_sar/total_pixeles)*100:.2f}%)")
        print(f"   Pixeles MNDWI: {pixeles_mndwi:,} ({(pixeles_mndwi/total_pixeles)*100:.2f}%)")
        print(f"   Pixeles UNION: {pixeles_union:,} ({(pixeles_union/total_pixeles)*100:.2f}%)")

        perfil_referencia.update({'dtype': 'uint8', 'count': 1, 'nodata': 0})
        with rasterio.open(archivo_union, 'w', **perfil_referencia) as dst:
            dst.write(union_data, 1)

        crs_raster = src_sar.crs
        transform  = src_sar.transform
        perfil     = perfil_referencia

print(f"\n   Archivo union: {archivo_union}")

# ============================================================
# PASO 2: EXTRACCION DE MASAS DE AGUA GRANDES
# ============================================================
print()
print("=" * 60)
print("PASO 2: EXTRACCION DE MASAS DE AGUA GRANDES")
print("=" * 60)
print(f"Erosion:      {ITERACIONES_EROSION} iteracion(es)")
print(f"Area minima:  {AREA_MINIMA_PIXELES:,} pixeles")

agua = union_data.copy()
pixeles_originales = int(np.sum(agua))
print(f"Pixeles agua inicial: {pixeles_originales:,}")

estructura = ndimage.generate_binary_structure(2, 2)

print(f"Aplicando erosion ({ITERACIONES_EROSION} iteracion(es))...")
agua_erosionada = ndimage.binary_erosion(
    agua, structure=estructura, iterations=ITERACIONES_EROSION
).astype(np.uint8)
print(f"  Pixeles tras erosion: {int(np.sum(agua_erosionada)):,}")

print("Etiquetando componentes...")
etiquetas, num_componentes = ndimage.label(agua_erosionada)
print(f"  Componentes encontrados: {num_componentes}")

tamanios = np.array(ndimage.sum(agua_erosionada, etiquetas, range(1, num_componentes + 1)))
indices_ord = np.argsort(tamanios)[::-1]

res_px = abs(transform[0])
print(f"  Top 10 por area:")
for i, idx in enumerate(indices_ord[:10]):
    px = int(tamanios[idx])
    ha = px * (res_px ** 2) / 10000
    print(f"    {i+1}. ID {idx+1}: {px:,} px  (~{ha:.1f} ha)")

ids_grandes = [idx + 1 for idx in range(num_componentes) if tamanios[idx] >= AREA_MINIMA_PIXELES]
print(f"  Componentes >= {AREA_MINIMA_PIXELES:,} px: {len(ids_grandes)}")

if ids_grandes:
    mascara_grandes = np.isin(etiquetas, ids_grandes).astype(np.uint8)
else:
    mascara_grandes = np.zeros_like(agua_erosionada, dtype=np.uint8)
    print("  AVISO: Ningun componente supera el umbral. Reduce AREA_MINIMA_PIXELES.")

print(f"Restaurando tamanio (dilatacion {ITERACIONES_EROSION} iteracion(es))...")
agua_final = ndimage.binary_dilation(
    mascara_grandes, structure=estructura, iterations=ITERACIONES_EROSION
).astype(np.uint8)
agua_final = (agua_final & agua).astype(np.uint8)
pixeles_finales = int(np.sum(agua_final))
print(f"  Pixeles agua final: {pixeles_finales:,}")

if GUARDAR_TIF_INTERMEDIO:
    nombre_tif = f"masas_agua_grandes_area{AREA_MINIMA_PIXELES}.tif"
    ruta_tif   = os.path.join(carpeta_salida, nombre_tif)
    perfil_tif = perfil.copy()
    perfil_tif.update(dtype=rasterio.uint8, count=1, compress='lzw', nodata=0)
    with rasterio.open(ruta_tif, 'w', **perfil_tif) as dst:
        dst.write(agua_final, 1)
    print(f"  TIF intermedio guardado: {nombre_tif}")

if GUARDAR_COMPONENTES_SEPARADOS and ids_grandes:
    carpeta_comp = os.path.join(carpeta_salida, "componentes_individuales")
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
# PASO 3: VECTORIZACION Y SUAVIZADO
# ============================================================
print()
print("=" * 60)
print("PASO 3: VECTORIZACION Y SUAVIZADO")
print("=" * 60)
print(f"Iteraciones suavizado: {ITERACIONES_SUAVIZADO}")
print(f"Buffer por iteracion:  {BUFFER_POR_ITERACION} m")
print(f"Simplificacion final:  {SIMPLIFY_FINAL} m")
print(f"Area minima poligono:  {MIN_AREA_M2} m2")

try:
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

        if gdf.crs is None or getattr(gdf.crs, 'is_geographic', False):
            bounds   = gdf.total_bounds
            cen_lon  = (bounds[0] + bounds[2]) / 2.0
            cen_lat  = (bounds[1] + bounds[3]) / 2.0
            epsg_utm = utm_epsg_from_lonlat(cen_lon, cen_lat)
            print(f"[2/5] Reproyectando a {epsg_utm}...")
            gdf = gdf.to_crs(epsg_utm)
        else:
            print(f"[2/5] CRS ya en metros ({gdf.crs.to_string()})")

        gdf['area_m2'] = gdf.geometry.area
        gdf = gdf[gdf['area_m2'] >= MIN_AREA_M2].copy()
        print(f"[3/5] Filtro area minima ({MIN_AREA_M2} m2): {len(gdf)} poligonos")

        if gdf.empty:
            print("Ningun poligono supero el umbral de area. Reduce MIN_AREA_M2.")
        else:
            print(f"[4/5] Simplificacion inicial ({SIMPLIFY_INICIAL} m)...")
            gdf['geometry'] = gdf.geometry.simplify(SIMPLIFY_INICIAL, preserve_topology=True)
            gdf = make_valid(gdf)

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
                ruta_shp   = os.path.join(carpeta_salida, nombre_shp)
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
                print(f"Union TIF:       {archivo_union}")
                if GUARDAR_TIF_INTERMEDIO:
                    print(f"TIF intermedio:  {ruta_tif}")
                print(f"Shapefile final: {ruta_shp}")
                print("=" * 60)
                print()
                print("--- Para ajustar el suavizado ---")
                print("  Mas suave:        Aumentar ITERACIONES_SUAVIZADO (5, 7, 10)")
                print("  Menos rectangular: Aumentar BUFFER_POR_ITERACION (10, 15)")
                print("  Mas detalle:      Reducir SIMPLIFY_FINAL (1, 2)")

except Exception as e:
    print(f"\nERROR en PASO 3 (vectorizacion):")
    print(f"  {e}")
    import traceback
    traceback.print_exc()
