# -*- coding: utf-8 -*-
"""
ANALISIS GEOMORFOLOGICO - SCRIPT UNIFICADO
Ejecuta secuencialmente:
  PASO 1: Descarga DEM Copernicus GLO-30 desde Google Earth Engine
  PASO 2: Genera DEM con microrelieve exagerado
  PASO 3: Calcula HAND + TWI y clasifica zonas de inundacion
  PASO 4: Genera graficos cartograficos
"""

# ============================================================
# PARAMETROS GLOBALES - MODIFICAR AQUI
# ============================================================
CARPETA_BASE    = r'F:\SYNC\ANT\2026-1\20260423\LA CHIQUITA'
SHAPEFILE_AOI   = r"F:\SYNC\ANT\2026-1\20260423\LA CHIQUITA\HIDROLOGICO\HIDROLOGICO.shp"
SHAPEFILE_HIDRO = r"F:\SYNC\ANT\2026-1\20260423\LA CHIQUITA\HIDROLOGICO\HIDROLOGICO.shp"
GEE_PROJECT     = 'precipitaciones-459216'

# DEM local de alta resolucion (ej. 12 m).
# Si la ruta existe se usa directamente y se omite la descarga GEE.
# Dejar en None para usar siempre el ALOS descargado desde GEE.
DEM_LOCAL_12M = r"None"  # Ejemplo: r"C:\ruta\al\dem_12m.tif" "None"

# Buffer para descarga del DEM geomorfologico (en metros).
# Debe ser mayor que el buffer del analisis hidrologico para que HAND/TWI/slope
# no se corten en los bordes de la cuenca. Recomendado: 10000-20000 m.
BUFFER_GEOMORFOLOGICO_M = 3000

# Buffer de zoom para los mapas PNG (en metros alrededor del poligono hidrologico).
# Los graficos se recortan a esta extension, no al DEM completo.
BUFFER_ZOOM_MAPAS_M = 1890

# --- Parametros de salida grafica (PASO 4) ---
# Resolucion en DPI (300 = alta calidad para impresion, 150 = ligero, 96 = pantalla)
MAPA_DPI      = 180
# Tamano de cada mapa individual (pixeles).
# El mapa compuesto 2x2 se genera automaticamente al doble de estas dimensiones.
# Ejemplos landscape: 4800x3000 (A3), 3508x2480 (A4), 5800x2800 (panoramico)
MAPA_ANCHO_PX = 3200
MAPA_ALTO_PX  = 1800

# --- Parametros capa Tipo de Relieve (PASO 4B) ---
GDB_RELIEVE_PATH  = r"F:\SYNC\ANT\GEOMORFOLOGIA Y COBERTURAS\GEOMORFOLOGIA\CORDOBA\S_Cordoba_2025_25K.gdb"
GDB_RELIEVE_CAPA  = "S_Cordoba_2025_25K"   # nombre de la capa dentro de la GDB
GDB_RELIEVE_CAMPO = "TIPO_RELIEVE"          # campo que define los colores
# Transparencia de la capa de relieve sobre el DEM (0=invisible, 1=solido)
GDB_RELIEVE_ALPHA = 0.55
# Unidades geomorfologicas asociadas a zonas inundables (IGAC, ambiente fluvial).
# Se resaltan en azul/cian y con menor transparencia.
# Ajustar segun los valores reales que imprima el script al ejecutar.
GDB_TIPOS_INUNDABLES = [
    "Planicie aluvial de desbordamiento",
    "Cubeta de desbordamiento",
    "Cubeta de decantacion",
    "Vega",
    "Napa de desbordamiento",
    "Complejo de orillares",
    "Banca aluvial",
    "Plano de inundacion",
    "Plano aluvial",
    "Complejo cenagoso",
    "Cienaga",
    "Terraza aluvial baja",
    "Vallecito aluvial",
]

# --- PASO 5: Parametros Geomorfologico (modificar aqui) ---
# Opciones: "HAND_TWI", "INDICE"
TIPO_ANALISIS_GEO             = "INDICE"
UMBRAL_INDICE_GEO             = 0.4     # umbral para TIPO_ANALISIS_GEO == "INDICE"
MAX_ITERACIONES_GEO           = 100
AREA_MINIMA_GEO_HA            = 0.5
AREA_MINIMA_FALLBACK_GEO_HA   = 0.01
  
SUAVIZADO_MORF_GEO            = True
TAMANO_KERNEL_GEO             = 3

SUAVIZAR_GEO                  = True
ITERACIONES_SUAVIZADO_GEO     = 5
BUFFER_POR_ITERACION_GEO      = 2    # metros

SUAVIZADO_EROSION_GEO         = True
PASADAS_EROSION_GEO           = 1
BUFFER_EROSION_GEO            = 3       # metros

SIMPLIFY_TOLERANCIA_GEO       = 4       # metros

# Smooth Polygon (Chaikin corner-cutting) - elimina bordes cuadrados
SMOOTH_CHAIKIN_GEO            = True
CHAIKIN_ITERACIONES_GEO       = 5      # iteraciones (mas = mas suave, tipico 3-6)

import os
import sys

# Forzar PROJ de Python antes de cualquier import geoespacial.
# Evita conflicto con el PROJ de PostgreSQL/PostGIS que se cuela en PATH.
for _sp in sys.path:
    _proj_dir = os.path.join(_sp, 'pyproj', 'proj_dir', 'share', 'proj')
    if os.path.exists(_proj_dir):
        os.environ['PROJ_DATA'] = _proj_dir
        os.environ['PROJ_LIB']  = _proj_dir
        break

import numpy as np

CARPETA_DEM      = os.path.join(CARPETA_BASE, 'DEM')
CARPETA_GEO      = os.path.join(CARPETA_DEM, 'resultados_Geomorfologico')
CARPETA_GRAFICOS = os.path.join(CARPETA_GEO, 'graficos')

# DEM que se usara en los pasos 2-5 (puede ser cualquiera de los descargados).
# Opciones de nombres descargados en PASO 1:
#   copernicus_dem_glo30_30m_buffer.tif
#   nasadem_30m_buffer.tif
#   alos_aw3d30_30m_buffer.tif
#   srtm_gl1_30m_buffer.tif
DEM_SELECCIONADO = 'copernicus_dem_glo30_30m_buffer.tif'   # <-- CAMBIAR AQUI
DEM_CRUDO        = os.path.join(CARPETA_DEM, DEM_SELECCIONADO)
DEM_MICRORELIEF  = os.path.join(CARPETA_DEM, DEM_SELECCIONADO.replace('.tif', '_microrelief_exag10x_local.tif'))

os.makedirs(CARPETA_DEM,      exist_ok=True)
os.makedirs(CARPETA_GEO,      exist_ok=True)
os.makedirs(CARPETA_GRAFICOS, exist_ok=True)

# ============================================================
# PASO 1 - FUENTE DEL DEM (LOCAL 12m o Copernicus GLO-30 GEE)
# ============================================================
print("=" * 60)
print("PASO 1: FUENTE DEL DEM")
print("=" * 60)

if DEM_LOCAL_12M and os.path.exists(DEM_LOCAL_12M):
    DEM_CRUDO = DEM_LOCAL_12M
    print(f"DEM local 12m encontrado -> usando: {DEM_CRUDO}")
    print("Omitiendo descarga GEE.")
else:
    if DEM_LOCAL_12M:
        print(f"ADVERTENCIA: DEM_LOCAL_12M definido pero no encontrado: {DEM_LOCAL_12M}")
    print("Descargando multiples DEMs 30m desde GEE para comparacion...")

    import ee
    import geemap

    ee.Initialize(project=GEE_PROJECT)

    fc          = geemap.shp_to_ee(SHAPEFILE_AOI)
    buffer_geom = fc.geometry().buffer(BUFFER_GEOMORFOLOGICO_M)
    region_geo  = buffer_geom.getInfo()['coordinates']

    # ---- definicion de las 4 fuentes ----
    fuentes_dem = [
        {
            "nombre":     "Copernicus GLO-30 (TanDEM-X radar 2011-2015, mejor precision global)",
            "archivo":    os.path.join(CARPETA_DEM, 'copernicus_dem_glo30_30m_buffer.tif'),
            "imagen":     ee.ImageCollection("COPERNICUS/DEM/GLO30")
                            .filterBounds(buffer_geom)
                            .select('DEM')
                            .mosaic()
                            .clip(buffer_geom),
        },
        {
            "nombre":     "NASADEM (SRTM reprocessado NASA 2000, version mejorada)",
            "archivo":    os.path.join(CARPETA_DEM, 'nasadem_30m_buffer.tif'),
            "imagen":     ee.Image("NASA/NASADEM_HGT/001")
                            .select('elevation')
                            .clip(buffer_geom),
        },
        {
            "nombre":     "ALOS AW3D30 (optico estereo JAXA 2006-2011)",
            "archivo":    os.path.join(CARPETA_DEM, 'alos_aw3d30_30m_buffer.tif'),
            "imagen":     ee.ImageCollection("JAXA/ALOS/AW3D30/V3_2")
                            .filterBounds(buffer_geom)
                            .select('DSM')
                            .mosaic()
                            .clip(buffer_geom),
        },
        {
            "nombre":     "SRTM GL1 (radar C-band NASA/USGS 2000, referencia clasica)",
            "archivo":    os.path.join(CARPETA_DEM, 'srtm_gl1_30m_buffer.tif'),
            "imagen":     ee.Image("USGS/SRTMGL1_003")
                            .select('elevation')
                            .clip(buffer_geom),
        },
    ]

    # ---- descarga de cada fuente ----
    for i, fuente in enumerate(fuentes_dem, 1):
        if os.path.exists(fuente["archivo"]):
            print(f"\n[{i}/4] YA EXISTE (omitiendo): {os.path.basename(fuente['archivo'])}")
            continue
        print(f"\n[{i}/4] Descargando: {fuente['nombre']}")
        print(f"       Destino: {os.path.basename(fuente['archivo'])}")
        try:
            geemap.ee_export_image(
                fuente["imagen"],
                fuente["archivo"],
                scale=30,
                region=region_geo,
                file_per_band=False
            )
            print(f"       OK: {os.path.basename(fuente['archivo'])}")
        except Exception as _e_dem:
            print(f"       ERROR: {_e_dem}")

    print(f"\nDEMs disponibles en: {CARPETA_DEM}")
    for fuente in fuentes_dem:
        existe = "OK" if os.path.exists(fuente["archivo"]) else "NO DESCARGADO"
        print(f"  [{existe}] {os.path.basename(fuente['archivo'])}")
    print(f"\nDEM seleccionado para analisis: {DEM_SELECCIONADO}")
    print("  -> Para cambiar, editar DEM_SELECCIONADO en los parametros globales.")

print(f"DEM a procesar: {DEM_CRUDO}")

# ============================================================
# PASO 2 - GENERAR DEM CON MICRORELIEVE EXAGERADO
# ============================================================
print("\n" + "=" * 60)
print("PASO 2: MICRORELIEVE EXAGERADO")
print("=" * 60)

import rasterio
from rasterio.fill import fillnodata
from scipy.ndimage import gaussian_filter

FACTOR_EXAG     = 10.0
SIGMA_PIXELS    = 7.0
FILL_MAX_SEARCH = 100
OUTLIER_STD     = 3.0

print(f"\nLeyendo DEM: {os.path.basename(DEM_CRUDO)}")
with rasterio.open(DEM_CRUDO) as src:
    profile_dem    = src.profile.copy()
    dem            = src.read(1).astype(np.float32)
    nodata_original = src.nodata

print(f"  Tamano: {dem.shape[1]}x{dem.shape[0]} px")
print(f"  Nodata original: {nodata_original}")
print(f"  Rango crudo: {np.nanmin(dem):.2f} - {np.nanmax(dem):.2f} m")

print("\nDetectando valores anomalos...")
mask = np.ones(dem.shape, dtype=np.uint8)

if nodata_original is not None:
    n_nodata = np.sum(dem == nodata_original)
    dem[dem == nodata_original] = np.nan
    mask[np.isnan(dem)] = 0
    print(f"  Nodata originales marcados: {n_nodata} px")

n_ceros = np.sum(dem == 0)
if n_ceros > 0:
    dem[dem == 0] = np.nan
    mask[np.isnan(dem)] = 0
    print(f"  Valores en cero marcados: {n_ceros} px")

n_negativos = np.sum(dem < 0)
if n_negativos > 0:
    dem[dem < 0] = np.nan
    mask[np.isnan(dem)] = 0
    print(f"  Valores negativos marcados: {n_negativos} px")

datos_validos = dem[~np.isnan(dem)]
mediana       = np.median(datos_validos)
desv_std      = np.std(datos_validos)
umbral_bajo   = mediana - OUTLIER_STD * desv_std
umbral_alto   = mediana + OUTLIER_STD * desv_std

n_out_bajo = np.sum((dem < umbral_bajo) & ~np.isnan(dem))
n_out_alto = np.sum((dem > umbral_alto) & ~np.isnan(dem))
dem[(dem < umbral_bajo) | (dem > umbral_alto)] = np.nan
mask[np.isnan(dem)] = 0

print(f"  Mediana: {mediana:.2f} m | Std: {desv_std:.2f} m")
print(f"  Rango valido: [{umbral_bajo:.2f}, {umbral_alto:.2f}] m")
print(f"  Outliers bajos: {n_out_bajo} px | altos: {n_out_alto} px")

total_anomalos = np.sum(mask == 0)
print(f"  TOTAL pixeles a rellenar: {total_anomalos} ({(total_anomalos / dem.size) * 100:.2f}%)")

print(f"\nRellenando huecos (max_search_distance={FILL_MAX_SEARCH})...")
dem_fill = np.copy(dem)
dem_fill[np.isnan(dem_fill)] = 0
dem_filled = fillnodata(dem_fill, mask=mask, max_search_distance=FILL_MAX_SEARCH)

print(f"  Rango despues de fill: {np.min(dem_filled):.2f} - {np.max(dem_filled):.2f} m")

if np.any(dem_filled == 0):
    n_sin_rellenar = np.sum(dem_filled == 0)
    dem_filled[dem_filled == 0] = mediana
    print(f"  {n_sin_rellenar} px sin rellenar -> asignados a mediana ({mediana:.2f} m)")

dem = dem_filled
print("  Huecos rellenados OK.")

print(f"\nAplicando suavizado gaussiano (sigma={SIGMA_PIXELS} px)...")
dem_smooth = gaussian_filter(dem, sigma=SIGMA_PIXELS)

print(f"Calculando microrelieve x{FACTOR_EXAG}...")
microrelief = dem - dem_smooth
micro_exag  = microrelief * FACTOR_EXAG
dem_exag    = dem_smooth + micro_exag

n_neg_final = np.sum(dem_exag < 0)
if n_neg_final > 0:
    print(f"  Negativos generados por exageracion: {n_neg_final} px -> clampeados a 0")
    dem_exag[dem_exag < 0] = 0

print(f"  Rango final: {np.min(dem_exag):.2f} - {np.max(dem_exag):.2f} m")

print(f"\nGuardando: {os.path.basename(DEM_MICRORELIEF)}")
profile_dem.update(dtype=rasterio.float32, count=1, compress='lzw', nodata=None)
with rasterio.open(DEM_MICRORELIEF, 'w', **profile_dem) as dst:
    dst.write(dem_exag.astype(np.float32), 1)

print(f"DEM con microrelieve (x{FACTOR_EXAG}) generado: {DEM_MICRORELIEF}")

# ============================================================
# PASO 3 - HAND + TWI: ZONAS DE INUNDACION
# ============================================================
print("\n" + "=" * 60)
print("PASO 3: HAND + TWI - ZONAS DE INUNDACION")
print("=" * 60)

from whitebox import WhiteboxTools
from scipy.ndimage import binary_closing, binary_opening

# ---------- parametros de corrientes ----------
THRESH_ACCUM = 2000

# ---------- umbrales HAND (metros) ----------
HAND_MUY_BAJO = 0.5
HAND_BAJO     = 1.0
HAND_MEDIO    = 2.0
HAND_ALTO     = 5.0

# ---------- pesos ----------
PESO_HAND = 0.6
PESO_TWI  = 0.4

# ---------- pendiente maxima inundable ----------
PENDIENTE_MAX = 5.0

# ---------- suavizado morfologico ----------
SUAVIZAR_RESULTADO = True
TAMANO_SUAVIZADO   = 3

# ---------- forzar recalculo ----------
FORZAR_RECALCULO = True

wbt = WhiteboxTools()
wbt.verbose = False
wbt.set_working_dir(CARPETA_GEO)

filled_dem  = os.path.join(CARPETA_GEO, "dem_filled.tif")
flow_ptr    = os.path.join(CARPETA_GEO, "flow_pointer.tif")
flow_accum  = os.path.join(CARPETA_GEO, "flow_accumulation.tif")
streams     = os.path.join(CARPETA_GEO, "streams_inundacion.tif")
slope_deg   = os.path.join(CARPETA_GEO, "slope_degrees.tif")
hand_raster = os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif")
twi_raster  = os.path.join(CARPETA_GEO, "TWI_wetness_index.tif")

zonas_hand_twi       = os.path.join(CARPETA_GEO, "zonas_HAND_TWI_combinado.tif")
indice_inundabilidad = os.path.join(CARPETA_GEO, "indice_inundabilidad.tif")

if FORZAR_RECALCULO:
    print("FORZAR_RECALCULO = True -> Borrando archivos previos...")
    for archivo in [filled_dem, flow_ptr, flow_accum, slope_deg,
                    streams, hand_raster, twi_raster, zonas_hand_twi, indice_inundabilidad]:
        if os.path.exists(archivo):
            try:
                os.remove(archivo)
                print(f"   Borrado: {os.path.basename(archivo)}")
            except Exception:
                pass

print(f"\nPesos: HAND={PESO_HAND}, TWI={PESO_TWI} | Pendiente max: {PENDIENTE_MAX}deg")

print("\n[1/6] Rellenando depresiones...")
if not os.path.exists(filled_dem):
    wbt.fill_depressions(DEM_MICRORELIEF, filled_dem)
else:
    print("   (usando existente)")

print("[2/6] Calculando direccion de flujo D8...")
if not os.path.exists(flow_ptr):
    wbt.d8_pointer(filled_dem, flow_ptr)
else:
    print("   (usando existente)")

print("[3/6] Calculando acumulacion de flujo...")
if not os.path.exists(flow_accum):
    wbt.d8_flow_accumulation(filled_dem, flow_accum, out_type="cells")
else:
    print("   (usando existente)")

print("[4/6] Extrayendo red de drenaje...")
wbt.extract_streams(flow_accum, streams, threshold=THRESH_ACCUM)

print("[5/6] Calculando pendiente...")
if not os.path.exists(slope_deg):
    wbt.slope(filled_dem, slope_deg, units="degrees")
else:
    print("   (usando existente)")

print("[6/6] Calculando HAND...")
wbt.elevation_above_stream(filled_dem, streams, hand_raster)

print("Calculando TWI...")
wbt.wetness_index(flow_accum, slope_deg, twi_raster)

# --- cargar rasters ---
print("\nCargando rasters...")
with rasterio.open(hand_raster) as src:
    hand         = src.read(1).astype(np.float32)
    profile_hand = src.profile

with rasterio.open(slope_deg) as src:
    slope = src.read(1).astype(np.float32)

with rasterio.open(twi_raster) as src:
    twi = src.read(1).astype(np.float32)

hand = np.where((hand < 0) | (hand > 1000), np.nan, hand)
twi  = np.where((twi  < 0) | (twi  > 30),  np.nan, twi)

print(f"  HAND: min={np.nanmin(hand):.2f}, max={np.nanmax(hand):.2f}")
print(f"  TWI:  min={np.nanmin(twi):.2f},  max={np.nanmax(twi):.2f}")

# --- normalizar y combinar ---
hand_norm = 1 - np.clip(hand / HAND_ALTO, 0, 1)
hand_norm = np.where(np.isnan(hand), np.nan, hand_norm)

twi_min  = np.nanpercentile(twi, 5)
twi_max  = np.nanpercentile(twi, 95)
twi_norm = np.clip((twi - twi_min) / (twi_max - twi_min), 0, 1)
twi_norm = np.where(np.isnan(twi), np.nan, twi_norm)

indice            = (PESO_HAND * hand_norm) + (PESO_TWI * twi_norm)
mascara_pendiente = slope <= PENDIENTE_MAX
indice            = np.where(mascara_pendiente, indice, 0)

# --- clasificar ---
UMBRAL_1 = 0.9; UMBRAL_2 = 0.8; UMBRAL_3 = 0.7; UMBRAL_4 = 0.6; UMBRAL_5 = 0.5
UMBRAL_6 = 0.4; UMBRAL_7 = 0.3; UMBRAL_8 = 0.2; UMBRAL_9 = 0.1

clasificacion = np.zeros_like(hand, dtype=np.uint8)
clasificacion = np.where(indice >= UMBRAL_1, 1, clasificacion)
clasificacion = np.where((indice >= UMBRAL_2) & (indice < UMBRAL_1), 2, clasificacion)
clasificacion = np.where((indice >= UMBRAL_3) & (indice < UMBRAL_2), 3, clasificacion)
clasificacion = np.where((indice >= UMBRAL_4) & (indice < UMBRAL_3), 4, clasificacion)
clasificacion = np.where((indice >= UMBRAL_5) & (indice < UMBRAL_4), 5, clasificacion)
clasificacion = np.where((indice >= UMBRAL_6) & (indice < UMBRAL_5), 6, clasificacion)
clasificacion = np.where((indice >= UMBRAL_7) & (indice < UMBRAL_6), 7, clasificacion)
clasificacion = np.where((indice >= UMBRAL_8) & (indice < UMBRAL_7), 8, clasificacion)
clasificacion = np.where((indice >= UMBRAL_9) & (indice < UMBRAL_8), 9, clasificacion)
clasificacion = np.where(~mascara_pendiente, 0, clasificacion)

if SUAVIZAR_RESULTADO:
    print("Aplicando suavizado morfologico...")
    estructura       = np.ones((TAMANO_SUAVIZADO, TAMANO_SUAVIZADO))
    mascara_inundable = (clasificacion > 0).astype(np.uint8)
    mascara_inundable = binary_closing(mascara_inundable, structure=estructura, iterations=1).astype(np.uint8)
    mascara_inundable = binary_opening(mascara_inundable, structure=estructura, iterations=1).astype(np.uint8)
    clasificacion    = np.where(mascara_inundable == 0, 0, clasificacion)

# --- estadisticas ---
with rasterio.open(DEM_MICRORELIEF) as src:
    res_raw = abs(src.transform[0])
    if src.crs.is_geographic:
        lat_c      = (src.bounds.top + src.bounds.bottom) / 2
        res_metros = res_raw * 111000 * np.cos(np.radians(lat_c))
    else:
        res_metros = res_raw

area_pixel_ha   = (res_metros ** 2) / 10000
total_validos   = np.sum(~np.isnan(hand))
area_total_iund = 0.0

print("\nDistribucion por clase:")
for clase, nombre, rango in [
    (1, "Humedal seguro",     f">{UMBRAL_1}"),
    (2, "Muy inundable",      f"{UMBRAL_2}-{UMBRAL_1}"),
    (3, "Inundable alto",     f"{UMBRAL_3}-{UMBRAL_2}"),
    (4, "Inundable",          f"{UMBRAL_4}-{UMBRAL_3}"),
    (5, "Inundable moderado", f"{UMBRAL_5}-{UMBRAL_4}"),
    (6, "Transicion alta",    f"{UMBRAL_6}-{UMBRAL_5}"),
    (7, "Transicion",         f"{UMBRAL_7}-{UMBRAL_6}"),
    (8, "Transicion baja",    f"{UMBRAL_8}-{UMBRAL_7}"),
    (9, "Influencia",         f"{UMBRAL_9}-{UMBRAL_8}"),
    (0, "Barrera/Dique",      f"<{UMBRAL_9} o pend>{PENDIENTE_MAX}deg"),
]:
    count   = np.sum(clasificacion == clase)
    area_ha = count * area_pixel_ha
    pct     = (count / total_validos) * 100 if total_validos > 0 else 0
    if clase > 0:
        area_total_iund += area_ha
    print(f"  Clase {clase} ({nombre}): {count:,} px = {area_ha:.1f} ha ({pct:.1f}%)")

print(f"\n  AREA INUNDABLE TOTAL (clases 1-9): {area_total_iund:.1f} ha")

# --- guardar clasificacion e indice ---
profile_hand.update(dtype='uint8', nodata=255, count=1, compress='lzw')
with rasterio.open(zonas_hand_twi, 'w', **profile_hand) as dst:
    dst.write(clasificacion, 1)
print(f"  Clasificacion: {os.path.basename(zonas_hand_twi)}")

profile_float = profile_hand.copy()
profile_float.update(dtype='float32', nodata=-9999)
indice_guardar = np.where(np.isnan(indice), -9999, indice)
with rasterio.open(indice_inundabilidad, 'w', **profile_float) as dst:
    dst.write(indice_guardar.astype(np.float32), 1)
print(f"  Indice continuo: {os.path.basename(indice_inundabilidad)}")

# --- leyenda QGIS ---
qml_path    = os.path.join(CARPETA_GEO, "zonas_HAND_TWI_combinado.qml")
qml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<qgis version="3.0">
  <pipe>
    <rasterrenderer type="paletted" opacity="0.85" band="1">
      <colorPalette>
        <paletteEntry value="0" color="#d9d9d9" alpha="180" label="0 - Barrera/Dique"/>
        <paletteEntry value="1" color="#08306b" alpha="255" label="1 - Humedal seguro (>{UMBRAL_1})"/>
        <paletteEntry value="2" color="#08519c" alpha="255" label="2 - Muy inundable ({UMBRAL_2}-{UMBRAL_1})"/>
        <paletteEntry value="3" color="#2171b5" alpha="255" label="3 - Inundable alto ({UMBRAL_3}-{UMBRAL_2})"/>
        <paletteEntry value="4" color="#4292c6" alpha="255" label="4 - Inundable ({UMBRAL_4}-{UMBRAL_3})"/>
        <paletteEntry value="5" color="#6baed6" alpha="255" label="5 - Inundable moderado ({UMBRAL_5}-{UMBRAL_4})"/>
        <paletteEntry value="6" color="#9ecae1" alpha="255" label="6 - Transicion alta ({UMBRAL_6}-{UMBRAL_5})"/>
        <paletteEntry value="7" color="#c6dbef" alpha="255" label="7 - Transicion ({UMBRAL_7}-{UMBRAL_6})"/>
        <paletteEntry value="8" color="#deebf7" alpha="255" label="8 - Transicion baja ({UMBRAL_8}-{UMBRAL_7})"/>
        <paletteEntry value="9" color="#f7fbff" alpha="255" label="9 - Influencia ({UMBRAL_9}-{UMBRAL_8})"/>
      </colorPalette>
    </rasterrenderer>
  </pipe>
</qgis>'''
with open(qml_path, 'w', encoding='utf-8') as f:
    f.write(qml_content)
print(f"  Leyenda QGIS: {os.path.basename(qml_path)}")

print("\nPASO 3 COMPLETADO")

# ============================================================
# PASO 4 - GENERAR GRAFICOS
# ============================================================
print("\n" + "=" * 60)
print("PASO 4: GENERACION DE GRAFICOS")
print("=" * 60)

import math
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import ListedColormap, BoundaryNorm, LightSource
from matplotlib_scalebar.scalebar import ScaleBar
import geopandas as gpd
import pyproj
from pyproj import Transformer as _Transformer
from mpl_toolkits.axes_grid1 import make_axes_locatable

rasters_config = {
    "slope_degrees": {
        "archivo":       os.path.join(CARPETA_GEO, "slope_degrees.tif"),
        "titulo":        "MAPA DE PENDIENTES",
        "cmap":          "YlOrRd",
        "label":         "Pendiente (grados)",
        "color_ref":     "blue",
        "hillshade":     True,
        "dem_hillshade": os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif"),
    },
    "flow_accumulation": {
        "archivo":       os.path.join(CARPETA_GEO, "flow_accumulation.tif"),
        "titulo":        "MAPA DE ACUMULACION DE FLUJO",
        "cmap":          "Blues",
        "label":         "Acumulacion (celdas)",
        "log_scale":     True,
        "hillshade":     True,
        "dem_hillshade": os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif"),
    },
    "streams_inundacion": {
        "archivo":       os.path.join(CARPETA_GEO, "streams_inundacion.tif"),
        "titulo":        "RED DE DRENAJE",
        "categorico":    True,
        "hillshade":     True,
        "dem_hillshade": os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif"),
    },
    "HAND": {
        "archivo":       os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif"),
        "titulo":        "HAND - ALTURA SOBRE DRENAJE",
        "cmap":          "terrain",
        "label":         "Altura (m)",
        "color_ref":     "red",
        "hillshade":     True,
        "dem_hillshade": os.path.join(CARPETA_GEO, "HAND_altura_sobre_drenaje.tif"),
    },
    "zonas_inundacion": {
        "archivo":       zonas_hand_twi,
        "titulo":        "ZONAS DE INUNDACION CLASIFICADAS HAND + TWI",
        "categorico":    True,
        "hillshade":     True,
        "dem_hillshade": DEM_MICRORELIEF,
        "clases": {
            1: ("Zonas de Susceptibilidad a la Inundacion", "#08306b"),
            2: ("", "#2171b5"),
            3: ("", "#6baed6"),
            4: ("", "#74c476"),
            5: ("", "#bae4b3"),
            6: ("", "#f7f4bf"),
            7: ("", "#fdda6e"),
            8: ("", "#f5b47a"),
            9: ("", "#e8d5c4")
        },
        "label_min": "Mayor susceptibilidad",
        "label_max": "Menor susceptibilidad",
    }
}

def crear_flecha_norte(ax, x, y, size=0.08):
    ax_north = ax.inset_axes([x, y, size, size * 1.5])
    ax_north.annotate('', xy=(0.5, 1), xytext=(0.5, 0),
                      arrowprops=dict(arrowstyle='->', lw=2, color='black'),
                      xycoords='axes fraction')
    ax_north.text(0.5, 1.1, 'N', ha='center', va='bottom', fontsize=12, fontweight='bold')
    ax_north.axis('off')
    return ax_north

def calcular_metros_por_unidad(src):
    res_raw = abs(src.transform[0])
    if src.crs and src.crs.is_geographic:
        lat_c = (src.bounds.top + src.bounds.bottom) / 2
        return res_raw * 111000 * np.cos(np.radians(lat_c)), 111000 * np.cos(np.radians(lat_c))
    return res_raw, 1

def _intervalo_grilla(rango_m, n_div=5):
    """Elige el intervalo de grilla más 'limpio' para el rango dado (en metros)."""
    target = rango_m / n_div
    if target <= 0:
        return 1000.0
    mag = 10 ** math.floor(math.log10(target))
    for factor in [1, 2, 2.5, 5, 10]:
        if factor * mag >= target:
            return factor * mag
    return 10.0 * mag

def agregar_grilla_magna_sirgas(ax, crs_raster, fontsize=7, n_div=5):
    """
    Dibuja grilla y etiquetas de coordenadas en MAGNA-SIRGAS 2018 / Origen-Nacional
    (EPSG:9377). Etiquetas en km. El intervalo se calcula automáticamente según escala.
    Funciona independientemente del CRS del raster de entrada.
    """
    CRS_MAGNA = pyproj.CRS.from_epsg(9377)
    try:
        crs_src = pyproj.CRS.from_user_input(crs_raster) if crs_raster else CRS_MAGNA
        t_fwd = _Transformer.from_crs(crs_src, CRS_MAGNA, always_xy=True)
        t_inv = _Transformer.from_crs(CRS_MAGNA, crs_src, always_xy=True)
    except Exception:
        ax.set_xticks([]); ax.set_yticks([])
        return

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    # Esquinas del viewport en MAGNA-SIRGAS
    cxs = [xlim[0], xlim[1], xlim[0], xlim[1]]
    cys = [ylim[0], ylim[0], ylim[1], ylim[1]]
    try:
        mxs, mys = t_fwd.transform(cxs, cys)
    except Exception:
        ax.set_xticks([]); ax.set_yticks([])
        return

    xmn, xmx = min(mxs), max(mxs)
    ymn, ymx = min(mys), max(mys)
    rango = max(xmx - xmn, ymx - ymn)
    if rango <= 0:
        ax.set_xticks([]); ax.set_yticks([])
        return

    iv = _intervalo_grilla(rango, n_div)

    xt_m = np.arange(math.ceil(xmn / iv) * iv, xmx + iv * 0.01, iv)
    yt_m = np.arange(math.ceil(ymn / iv) * iv, ymx + iv * 0.01, iv)
    xt_m = xt_m[(xt_m >= xmn) & (xt_m <= xmx)]
    yt_m = yt_m[(yt_m >= ymn) & (yt_m <= ymx)]

    ym_c = (ymn + ymx) / 2
    xm_c = (xmn + xmx) / 2
    try:
        xt_p = [t_inv.transform(xm, ym_c)[0] for xm in xt_m]
        yt_p = [t_inv.transform(xm_c, ym)[1] for ym in yt_m]
    except Exception:
        ax.set_xticks([]); ax.set_yticks([])
        return

    def _fmt(v):
        # Muestra en metros enteros con separador de miles (punto)
        return f"{int(round(v)):,}".replace(",", ".")

    ax.set_xticks(xt_p)
    ax.set_yticks(yt_p)
    ax.set_xticklabels([_fmt(xm) for xm in xt_m],
                       fontsize=fontsize, rotation=0, ha='center')
    ax.set_yticklabels([_fmt(ym) for ym in yt_m],
                       fontsize=fontsize, rotation=0, ha='right')
    ax.tick_params(axis='both', direction='in', length=4, width=0.6,
                   color='black', zorder=10, pad=1)
    ax.grid(True, color='#444444', linewidth=0.35, alpha=0.45,
            linestyle='-', zorder=3)
    ax.set_xlabel("")
    ax.set_ylabel("")
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(0.8)
        spine.set_color('black')
    # Nota del sistema de referencia
    ax.text(0.01, 0.01, "MAGNA-SIRGAS 2018 / Origen-Nacional (m)",
            transform=ax.transAxes, fontsize=max(fontsize - 1, 5),
            va='bottom', ha='left', color='#333333',
            bbox=dict(boxstyle='round,pad=0.2', facecolor='white',
                      alpha=0.75, edgecolor='none'), zorder=11)

print("Cargando capa de referencia hidrologica...")
try:
    gdf_referencia          = gpd.read_file(SHAPEFILE_HIDRO)
    gdf_referencia_disuelto = gdf_referencia.dissolve()
    tiene_referencia        = True
    print(f"  Cargada: {len(gdf_referencia)} elementos")
except Exception as e:
    print(f"  Advertencia: no se pudo cargar ({e})")
    tiene_referencia = False

print("\nCalculando extension de zoom para mapas...")
zoom_bounds    = None   # bounds en el CRS del primer raster (para referencia)
zoom_bounds_crs = None  # CRS en que zoom_bounds fue calculado
if tiene_referencia:
    for _cfg in rasters_config.values():
        if os.path.exists(_cfg["archivo"]):
            with rasterio.open(_cfg["archivo"]) as _src:
                _crs_zoom = _src.crs
            # Siempre buffer en CRS proyectado (metros) para que BUFFER_ZOOM_MAPAS_M sea correcto
            from shapely.ops import unary_union as _uu_z
            import pyproj
            try:
                # Intentar usar el CRS del raster si es proyectado (unidades en metros)
                if _crs_zoom and not _crs_zoom.is_geographic:
                    _gdf_z = gdf_referencia_disuelto.to_crs(_crs_zoom)
                    _buf_geom = _uu_z(_gdf_z.geometry).buffer(BUFFER_ZOOM_MAPAS_M)
                    zoom_bounds = _buf_geom.bounds
                    zoom_bounds_crs = _crs_zoom
                else:
                    # CRS geografico: buffer en CRS proyectado EPSG:9377 y guardar en ese CRS
                    _gdf_proj = gdf_referencia_disuelto.to_crs(epsg=9377)
                    _buf_geom = _uu_z(_gdf_proj.geometry).buffer(BUFFER_ZOOM_MAPAS_M)
                    zoom_bounds = _buf_geom.bounds
                    import pyproj
                    zoom_bounds_crs = pyproj.CRS.from_epsg(9377)
            except Exception as _e:
                print(f"  Advertencia al calcular zoom: {_e}")
                _gdf_proj = gdf_referencia_disuelto.to_crs(epsg=9377)
                _buf_geom = _uu_z(_gdf_proj.geometry).buffer(BUFFER_ZOOM_MAPAS_M)
                zoom_bounds = _buf_geom.bounds
                zoom_bounds_crs = pyproj.CRS.from_epsg(9377)
            print(f"  Zoom (CRS: {zoom_bounds_crs}): xmin={zoom_bounds[0]:.1f} xmax={zoom_bounds[2]:.1f} "
                  f"ymin={zoom_bounds[1]:.1f} ymax={zoom_bounds[3]:.1f}")
            # Ajustar extension geografica al ratio del formato de figura.
            # Fraccion del ancho ocupada por el mapa (el resto son colorbar + margenes).
            _FRAC_X = 0.87
            _fig_ratio = (MAPA_ANCHO_PX * _FRAC_X) / MAPA_ALTO_PX
            _zcx = (zoom_bounds[0] + zoom_bounds[2]) / 2
            _zcy = (zoom_bounds[1] + zoom_bounds[3]) / 2
            _zhw = (zoom_bounds[2] - zoom_bounds[0]) / 2   # semiancho geografico
            _zhh = (zoom_bounds[3] - zoom_bounds[1]) / 2   # semialto geografico
            if (_zhw / _zhh) < _fig_ratio:
                _zhw = _zhh * _fig_ratio   # extender en X
            else:
                _zhh = _zhw / _fig_ratio   # extender en Y
            zoom_bounds = (_zcx - _zhw, _zcy - _zhh, _zcx + _zhw, _zcy + _zhh)
            print(f"  Zoom ajustado al ratio {_fig_ratio:.2f}: "
                  f"ancho={_zhw*2:.0f}m  alto={_zhh*2:.0f}m")
            break

print("\nGenerando mapas individuales...")

for nombre, config in rasters_config.items():
    archivo   = config["archivo"]
    color_ref = config.get("color_ref", "red")

    if not os.path.exists(archivo):
        print(f"\n[SKIP] {nombre}: archivo no encontrado")
        continue

    print(f"\n[+] {nombre}")

    with rasterio.open(archivo) as src:
        data   = src.read(1)
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
        crs    = src.crs
        _, metros_por_unidad = calcular_metros_por_unidad(src)

    fig, ax = plt.subplots(1, 1, figsize=(MAPA_ANCHO_PX / MAPA_DPI, MAPA_ALTO_PX / MAPA_DPI))

    if config.get("categorico") and "clases" in config and config.get("hillshade"):
        clases  = config["clases"]
        valores = list(clases.keys())
        colores = [clases[v][1] for v in valores]
        cmap    = ListedColormap(colores)
        bounds  = valores + [max(valores) + 1]
        norm    = BoundaryNorm(bounds, cmap.N)

        dem_path = config.get("dem_hillshade")
        if dem_path and os.path.exists(dem_path):
            from scipy.ndimage import zoom as scipy_zoom
            with rasterio.open(dem_path) as dem_src:
                dem_data = dem_src.read(1).astype(float)
                dem_data = np.where(dem_data < 0, 0, dem_data)

            if dem_data.shape != data.shape:
                zy = data.shape[0] / dem_data.shape[0]
                zx = data.shape[1] / dem_data.shape[1]
                dem_data = scipy_zoom(dem_data, (zy, zx), order=1)

            # --- DEM de fondo con tono cafe/tierra ---
            from matplotlib.colors import LinearSegmentedColormap
            _colores_cafe = [
                (0.96, 0.93, 0.86),   # crema claro (valles)
                (0.87, 0.76, 0.60),   # arena dorada
                (0.72, 0.55, 0.35),   # cafe medio
                (0.52, 0.35, 0.18),   # cafe oscuro
                (0.32, 0.20, 0.09),   # cafe muy oscuro (cumbres)
            ]
            _cmap_cafe = LinearSegmentedColormap.from_list('cafe_terrain', _colores_cafe)

            ls        = LightSource(azdeg=330, altdeg=40)
            dem_valid = np.where(dem_data > 0, dem_data, np.nan)
            dv_min, dv_max = np.nanmin(dem_valid), np.nanmax(dem_valid)
            dem_norm  = np.where(np.isnan(dem_valid), 0,
                                 (dem_valid - dv_min) / (dv_max - dv_min + 1e-10))
            rgb_elev  = _cmap_cafe(dem_norm)[:, :, :3]
            mask_nan  = np.isnan(dem_valid)
            rgb_elev[mask_nan] = [0.97, 0.97, 0.97]
            shaded_elev = ls.shade_rgb(rgb_elev, dem_data, vert_exag=3,
                                       blend_mode='overlay')
            shaded_elev = np.clip(shaded_elev, 0, 1)
            shaded_elev[mask_nan] = [0.97, 0.97, 0.97]
            ax.imshow(shaded_elev, extent=extent, alpha=1.0)

            # --- Zonas de inundacion semitransparentes encima ---
            mask_nodata = (data == 0)
            rgba        = cmap(norm(data))
            rgba[mask_nodata]    = [1.0, 1.0, 1.0, 0.0]
            rgba[~mask_nodata, 3] = 0.62
            ax.imshow(rgba, extent=extent)

            sm_elev = plt.cm.ScalarMappable(cmap=_cmap_cafe,
                                            norm=plt.Normalize(vmin=dv_min, vmax=dv_max))
            sm_elev.set_array([])
            divider   = make_axes_locatable(ax)
            cax_elev  = divider.append_axes("right", size="3%", pad=0.1)
            cbar_elev = plt.colorbar(sm_elev, cax=cax_elev)
            cbar_elev.set_label("Elevacion (m)", fontsize=10)
        else:
            ax.imshow(data, extent=extent, cmap=cmap, norm=norm)

        from matplotlib.lines import Line2D
        patches = [mpatches.Patch(color=colores[0], label=clases[valores[0]][0])]
        patches.append(Line2D([0], [0], marker='s', color='w',
                              markerfacecolor=colores[1], markersize=10,
                              label=config.get("label_min", "")))
        patches.append(Line2D([0], [0], marker='s', color='w',
                              markerfacecolor=colores[-1], markersize=10,
                              label=config.get("label_max", "")))
        if tiene_referencia:
            patches.append(mpatches.Patch(facecolor='none', edgecolor=color_ref,
                                          linewidth=2, label='Componente Hidrologico'))
        legend = ax.legend(handles=patches, loc='lower right', fontsize=9,
                           title="Leyenda", framealpha=0.95,
                           bbox_to_anchor=(0.99, 0.01))
        legend.get_frame().set_edgecolor('black')

    elif config.get("categorico") and "clases" in config:
        clases  = config["clases"]
        valores = list(clases.keys())
        colores = [clases[v][1] for v in valores]
        nombres = [clases[v][0] for v in valores]
        cmap    = ListedColormap(colores)
        bounds  = valores + [max(valores) + 1]
        norm    = BoundaryNorm(bounds, cmap.N)
        ax.imshow(data, extent=extent, cmap=cmap, norm=norm)
        patches = [mpatches.Patch(color=colores[i], label=nombres[i])
                   for i in range(len(valores))]
        if tiene_referencia:
            patches.append(mpatches.Patch(facecolor='none', edgecolor=color_ref,
                                          linewidth=2, label='Componente Hidrologico'))
        legend = ax.legend(handles=patches, loc='lower right', fontsize=9,
                           title="Leyenda", framealpha=0.95,
                           bbox_to_anchor=(0.99, 0.01))
        legend.get_frame().set_edgecolor('black')

    elif config.get("categorico"):
        dem_path = config.get("dem_hillshade")
        if config.get("hillshade") and dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as dem_src:
                dem_data = dem_src.read(1).astype(float)
                dem_data = np.where(dem_data < 0, 0, dem_data)
            ls       = LightSource(azdeg=315, altdeg=45)
            rgb_base = np.full((*data.shape, 3), 0.92)
            rgb_base[data == 1] = [0.13, 0.44, 0.71]
            shaded   = ls.shade_rgb(rgb_base, dem_data, vert_exag=3, blend_mode='soft')
            ax.imshow(shaded, extent=extent)
        else:
            data_masked = np.ma.masked_where(data == 0, data)
            ax.imshow(data_masked, extent=extent, cmap='Blues', interpolation='nearest')

    else:
        data_plot = data.copy().astype(float)
        data_plot = np.where(data_plot < 0, np.nan, data_plot)

        if config.get("log_scale"):
            data_plot = np.where(data_plot > 0, np.log10(data_plot + 1), np.nan)
            label     = f"{config['label']} (log10)"
        else:
            p2, p98   = np.nanpercentile(data_plot, [2, 98])
            data_plot = np.clip(data_plot, p2, p98)
            label     = config['label']

        vmin, vmax = np.nanmin(data_plot), np.nanmax(data_plot)
        dem_path   = config.get("dem_hillshade")

        if config.get("hillshade") and dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as dem_src:
                dem_data = dem_src.read(1).astype(float)
                dem_data = np.where(dem_data < 0, 0, dem_data)
            ls        = LightSource(azdeg=315, altdeg=45)
            data_norm = np.where(np.isnan(data_plot), 0,
                                 (data_plot - vmin) / (vmax - vmin + 1e-10))
            cmap_obj  = plt.cm.get_cmap(config['cmap'])
            rgb       = cmap_obj(data_norm)[:, :, :3]
            mask_nan  = np.isnan(data_plot)
            rgb[mask_nan] = [1.0, 1.0, 1.0]
            shaded    = ls.shade_rgb(rgb, dem_data, vert_exag=3, blend_mode='soft')
            shaded[mask_nan] = [1.0, 1.0, 1.0]
            ax.imshow(shaded, extent=extent)
            sm = plt.cm.ScalarMappable(cmap=config['cmap'],
                                       norm=plt.Normalize(vmin=vmin, vmax=vmax))
            sm.set_array([])
            divider = make_axes_locatable(ax)
            cax     = divider.append_axes("right", size="3%", pad=0.1)
            cbar    = plt.colorbar(sm, cax=cax)
            cbar.set_label(label, fontsize=10)
        else:
            im = ax.imshow(data_plot, extent=extent, cmap=config['cmap'])
            divider = make_axes_locatable(ax)
            cax     = divider.append_axes("right", size="3%", pad=0.1)
            cbar    = plt.colorbar(im, cax=cax)
            cbar.set_label(label, fontsize=10)

    if tiene_referencia:
        try:
            gdf_plot = gdf_referencia_disuelto.to_crs(crs)
            gdf_plot.boundary.plot(ax=ax, color='white', linewidth=4)
            gdf_plot.boundary.plot(ax=ax, color=color_ref, linewidth=2)
        except Exception as e:
            print(f"    Advertencia al plotear referencia: {e}")

    if zoom_bounds:
        try:
            if zoom_bounds_crs and crs and not pyproj.CRS(crs).equals(zoom_bounds_crs):
                from shapely.geometry import box
                import geopandas as _gpd_z
                _box = box(zoom_bounds[0], zoom_bounds[1], zoom_bounds[2], zoom_bounds[3])
                _gs  = _gpd_z.GeoSeries([_box], crs=zoom_bounds_crs).to_crs(crs)
                _b   = _gs.total_bounds  # (minx, miny, maxx, maxy)
                ax.set_xlim(_b[0], _b[2])
                ax.set_ylim(_b[1], _b[3])
            else:
                ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
                ax.set_ylim(zoom_bounds[1], zoom_bounds[3])
        except Exception as _ze:
            print(f"    Advertencia zoom: {_ze}")
            ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
            ax.set_ylim(zoom_bounds[1], zoom_bounds[3])

    agregar_grilla_magna_sirgas(ax, crs, fontsize=7)
    ax.set_title("", pad=0)

    crear_flecha_norte(ax, 0.01, 0.83)

    try:
        scalebar = ScaleBar(
            dx=metros_por_unidad,
            units="m",
            length_fraction=0.2,
            location='lower left',
            box_alpha=0.9,
            sep=5, pad=0.5,
            font_properties={'size': 10},
            fixed_units="km",
            bbox_to_anchor=(0.02, 0.02),
            bbox_transform=ax.transAxes
        )
        ax.add_artist(scalebar)
    except Exception as e:
        print(f"    Error en escala: {e}")

    if tiene_referencia and not config.get("categorico"):
        ax.plot([], [], color=color_ref, linewidth=2, label='Componente Hidrologico')
        ax.legend(loc='upper right', fontsize=9, framealpha=0.95)

    plt.tight_layout(pad=0.4)
    output_path = os.path.join(CARPETA_GRAFICOS, f"mapa_{nombre}.png")
    plt.savefig(output_path, dpi=MAPA_DPI, bbox_inches='tight',
                pad_inches=0.02, facecolor='white')
    plt.close()
    print(f"    Guardado: {os.path.basename(output_path)}")

# --- mapa compuesto 2x2 ---
print("\n[+] Generando mapa compuesto...")
fig, axes = plt.subplots(2, 2, figsize=(2 * MAPA_ANCHO_PX / MAPA_DPI, 2 * MAPA_ALTO_PX / MAPA_DPI))
axes      = axes.flatten()

for idx, nombre in enumerate(["slope_degrees", "flow_accumulation", "HAND", "zonas_inundacion"]):
    if nombre not in rasters_config:
        continue
    config    = rasters_config[nombre]
    archivo   = config["archivo"]
    color_ref = config.get("color_ref", "red")

    if not os.path.exists(archivo):
        continue

    ax = axes[idx]
    with rasterio.open(archivo) as src:
        data   = src.read(1)
        extent = [src.bounds.left, src.bounds.right, src.bounds.bottom, src.bounds.top]
        crs    = src.crs

    if config.get("categorico") and "clases" in config:
        clases  = config["clases"]
        valores = list(clases.keys())
        colores = [clases[v][1] for v in valores]
        cmap    = ListedColormap(colores)
        bounds  = valores + [max(valores) + 1]
        norm    = BoundaryNorm(bounds, cmap.N)
        dem_path = config.get("dem_hillshade")
        if config.get("hillshade") and dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as dem_src:
                dem_data = dem_src.read(1).astype(float)
                dem_data = np.where(dem_data < 0, 0, dem_data)
            if dem_data.shape != data.shape:
                from scipy.ndimage import zoom as nd_zoom
                zoom_r = data.shape[0] / dem_data.shape[0]
                zoom_c = data.shape[1] / dem_data.shape[1]
                dem_data = nd_zoom(dem_data, (zoom_r, zoom_c), order=1)
            ls          = LightSource(azdeg=315, altdeg=45)
            mask_nodata = (data == 0)
            rgb         = cmap(norm(data))[:, :, :3]
            shaded      = ls.shade_rgb(rgb, dem_data, vert_exag=3, blend_mode='soft')
            shaded[mask_nodata] = [1.0, 1.0, 1.0]
            ax.imshow(shaded, extent=extent)
        else:
            ax.imshow(data, extent=extent, cmap=cmap, norm=norm)
    else:
        data_plot = np.where(data.astype(float) < 0, np.nan, data.astype(float))
        if config.get("log_scale"):
            data_plot = np.where(data_plot > 0, np.log10(data_plot + 1), np.nan)
        else:
            p2, p98   = np.nanpercentile(data_plot, [2, 98])
            data_plot = np.clip(data_plot, p2, p98)
        dem_path = config.get("dem_hillshade")
        if config.get("hillshade") and dem_path and os.path.exists(dem_path):
            with rasterio.open(dem_path) as dem_src:
                dem_data = dem_src.read(1).astype(float)
                dem_data = np.where(dem_data < 0, 0, dem_data)
            if dem_data.shape != data.shape:
                from scipy.ndimage import zoom as nd_zoom
                zoom_r = data.shape[0] / dem_data.shape[0]
                zoom_c = data.shape[1] / dem_data.shape[1]
                dem_data = nd_zoom(dem_data, (zoom_r, zoom_c), order=1)
            ls   = LightSource(azdeg=315, altdeg=45)
            vmin, vmax = np.nanmin(data_plot), np.nanmax(data_plot)
            data_norm  = np.where(np.isnan(data_plot), 0,
                                  (data_plot - vmin) / (vmax - vmin + 1e-10))
            cmap_obj   = plt.cm.get_cmap(config.get('cmap', 'viridis'))
            rgb        = cmap_obj(data_norm)[:, :, :3]
            mask_nan   = np.isnan(data_plot)
            rgb[mask_nan] = [1.0, 1.0, 1.0]
            shaded     = ls.shade_rgb(rgb, dem_data, vert_exag=3, blend_mode='soft')
            shaded[mask_nan] = [1.0, 1.0, 1.0]
            ax.imshow(shaded, extent=extent)
        else:
            ax.imshow(data_plot, extent=extent, cmap=config.get('cmap', 'viridis'))

    if tiene_referencia:
        try:
            gdf_plot = gdf_referencia_disuelto.to_crs(crs)
            gdf_plot.boundary.plot(ax=ax, color='white', linewidth=3)
            gdf_plot.boundary.plot(ax=ax, color=color_ref, linewidth=1.5)
        except Exception:
            pass

    if zoom_bounds:
        try:
            if zoom_bounds_crs and crs and not pyproj.CRS(crs).equals(zoom_bounds_crs):
                from shapely.geometry import box as _box2
                import geopandas as _gpd_z2
                _b2 = _gpd_z2.GeoSeries(
                    [_box2(zoom_bounds[0], zoom_bounds[1], zoom_bounds[2], zoom_bounds[3])],
                    crs=zoom_bounds_crs
                ).to_crs(crs).total_bounds
                ax.set_xlim(_b2[0], _b2[2])
                ax.set_ylim(_b2[1], _b2[3])
            else:
                ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
                ax.set_ylim(zoom_bounds[1], zoom_bounds[3])
        except Exception:
            ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
            ax.set_ylim(zoom_bounds[1], zoom_bounds[3])

    ax.set_title("", pad=0)
    agregar_grilla_magna_sirgas(ax, crs, fontsize=6)

plt.tight_layout(rect=[0, 0, 1, 1], h_pad=0.8, w_pad=0.8)

output_compuesto = os.path.join(CARPETA_GRAFICOS, "mapa_compuesto_HAND.png")
plt.savefig(output_compuesto, dpi=MAPA_DPI, bbox_inches='tight',
            pad_inches=0.02, facecolor='white')
plt.close()
print(f"    Guardado: {os.path.basename(output_compuesto)}")

# ============================================================
# PASO 4B - MAPA DE TIPO DE RELIEVE (GDB)
# ============================================================
print("\n" + "=" * 60)
print("PASO 4B: MAPA DE TIPO DE RELIEVE")
print("=" * 60)

try:
    # Intentar leer la capa directamente.
    # Si GDB_RELIEVE_CAPA no existe, geopandas lanza ValueError
    # con la lista de capas disponibles en el mensaje de error.
    try:
        gdf_relieve = gpd.read_file(GDB_RELIEVE_PATH, layer=GDB_RELIEVE_CAPA)
    except Exception as _e_layer:
        # Intentar con gpd.list_layers (geopandas >= 1.0)
        print(f"  Capa '{GDB_RELIEVE_CAPA}' no encontrada: {_e_layer}")
        try:
            _capas = gpd.list_layers(GDB_RELIEVE_PATH)
            print(f"  Capas disponibles:\n{_capas}")
        except Exception:
            pass
        raise
    print(f"  Capa: {GDB_RELIEVE_CAPA} | {len(gdf_relieve)} poligonos | CRS: {gdf_relieve.crs}")

    if GDB_RELIEVE_CAMPO not in gdf_relieve.columns:
        print(f"  ERROR: campo '{GDB_RELIEVE_CAMPO}' no encontrado.")
        print(f"  Columnas disponibles: {list(gdf_relieve.columns)}")
        raise ValueError("Campo no encontrado")

    # Reproyectar al CRS del DEM
    with rasterio.open(DEM_MICRORELIEF) as _src_r:
        _crs_dem_r      = _src_r.crs
        _extent_dem_r   = [_src_r.bounds.left, _src_r.bounds.right,
                           _src_r.bounds.bottom, _src_r.bounds.top]
        _dem_rel        = _src_r.read(1).astype(float)
        _dem_rel        = np.where(_dem_rel < 0, 0, _dem_rel)
        _, _mpu_r       = calcular_metros_por_unidad(_src_r)

    gdf_rel_proj = gdf_relieve.to_crs(_crs_dem_r)

    # Paleta de colores geomorfologicos (tonos naturales)
    _tipos = sorted(gdf_rel_proj[GDB_RELIEVE_CAMPO].dropna().unique())
    print(f"  Valores de {GDB_RELIEVE_CAMPO}: {_tipos}")
    _paleta_geo = [
        '#C8A882', '#8DB87B', '#E8C86A', '#A0C4A0', '#D4956A',
        '#7BA8C8', '#C8A0C8', '#88B890', '#D4C07A', '#A8887A',
        '#B8C890', '#D4A888', '#90A8C0', '#C8B078', '#98C0A0',
        '#D08878', '#A8C8B8', '#C0A070', '#88A8B8', '#D4B890',
    ]
    _color_tipo = {t: _paleta_geo[i % len(_paleta_geo)] for i, t in enumerate(_tipos)}

    # ---- figura ----
    fig, ax = plt.subplots(1, 1, figsize=(MAPA_ANCHO_PX / MAPA_DPI, MAPA_ALTO_PX / MAPA_DPI))

    # 1. DEM de fondo con hillshade cafe
    from matplotlib.colors import LinearSegmentedColormap as _LSC
    _cmap_cafe2 = _LSC.from_list('cafe2', [
        (0.96, 0.93, 0.86), (0.87, 0.76, 0.60),
        (0.72, 0.55, 0.35), (0.52, 0.35, 0.18), (0.32, 0.20, 0.09)
    ])
    _ls_r     = LightSource(azdeg=330, altdeg=40)
    _dv       = np.where(_dem_rel > 0, _dem_rel, np.nan)
    _dmin, _dmax = np.nanmin(_dv), np.nanmax(_dv)
    _dnorm    = np.where(np.isnan(_dv), 0, (_dv - _dmin) / (_dmax - _dmin + 1e-10))
    _rgb_c    = _cmap_cafe2(_dnorm)[:, :, :3]
    _mnan     = np.isnan(_dv)
    _rgb_c[_mnan] = [0.97, 0.97, 0.97]
    _shaded_r = _ls_r.shade_rgb(_rgb_c, _dem_rel, vert_exag=3, blend_mode='overlay')
    _shaded_r = np.clip(_shaded_r, 0, 1)
    _shaded_r[_mnan] = [0.97, 0.97, 0.97]
    ax.imshow(_shaded_r, extent=_extent_dem_r, alpha=1.0)

    # 2. Capa de tipo de relieve: todos los tipos con mismo estilo
    for _tipo in _tipos:
        _sub = gdf_rel_proj[gdf_rel_proj[GDB_RELIEVE_CAMPO] == _tipo]
        if len(_sub) == 0:
            continue
        _sub.plot(ax=ax, color=_color_tipo[_tipo], alpha=GDB_RELIEVE_ALPHA,
                  edgecolor='white', linewidth=0.3)

    # 3. Zoom igual que los demas mapas
    if zoom_bounds:
        try:
            if zoom_bounds_crs and _crs_dem_r and \
               not pyproj.CRS(_crs_dem_r).equals(zoom_bounds_crs):
                from shapely.geometry import box as _bx4b
                _b4b = gpd.GeoSeries([_bx4b(*zoom_bounds)],
                                     crs=zoom_bounds_crs).to_crs(_crs_dem_r).total_bounds
                ax.set_xlim(_b4b[0], _b4b[2]); ax.set_ylim(_b4b[1], _b4b[3])
            else:
                ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
                ax.set_ylim(zoom_bounds[1], zoom_bounds[3])
        except Exception:
            ax.set_xlim(zoom_bounds[0], zoom_bounds[2])
            ax.set_ylim(zoom_bounds[1], zoom_bounds[3])

    # 4. Poligono de referencia encima
    if tiene_referencia:
        try:
            _gdf_ref4b = gdf_referencia_disuelto.to_crs(_crs_dem_r)
            _gdf_ref4b.boundary.plot(ax=ax, color='white', linewidth=4)
            _gdf_ref4b.boundary.plot(ax=ax, color='red',   linewidth=2)
        except Exception as _e4b:
            print(f"    Advertencia referencia: {_e4b}")

    # 5. Leyenda
    _patches_r = [mpatches.Patch(facecolor=_color_tipo[_t], edgecolor='grey',
                                 linewidth=0.4, label=_t, alpha=0.85)
                  for _t in _tipos]
    if tiene_referencia:
        _patches_r.append(mpatches.Patch(facecolor='none', edgecolor='red',
                                         linewidth=2, label='Componente Hidrologico'))
    _leg_r = ax.legend(handles=_patches_r, loc='lower right', fontsize=7,
                       title="Tipo de Relieve (IGAC)",
                       framealpha=0.95, bbox_to_anchor=(0.99, 0.01))
    _leg_r.get_frame().set_edgecolor('black')

    # 6. Elementos cartograficos
    crear_flecha_norte(ax, 0.01, 0.78)
    try:
        ax.add_artist(ScaleBar(dx=_mpu_r, units="m", length_fraction=0.2,
                               location='lower left', box_alpha=0.9,
                               sep=5, pad=0.5, font_properties={'size': 10},
                               fixed_units="km",
                               bbox_to_anchor=(0.02, 0.02),
                               bbox_transform=ax.transAxes))
    except Exception as _e_sb4b:
        print(f"    Error escala: {_e_sb4b}")

    agregar_grilla_magna_sirgas(ax, _crs_dem_r, fontsize=7)
    ax.set_title("", pad=0)

    plt.tight_layout(pad=0.4)
    _out_relieve = os.path.join(CARPETA_GRAFICOS, "mapa_tipo_relieve.png")
    plt.savefig(_out_relieve, dpi=MAPA_DPI, bbox_inches='tight',
                pad_inches=0.02, facecolor='white')
    plt.close()
    print(f"    Guardado: {os.path.basename(_out_relieve)}")

except Exception as _e_4b:
    print(f"  PASO 4B ERROR: {_e_4b}")
    import traceback; traceback.print_exc()

# ============================================================
# RESUMEN FINAL
# ============================================================
print("\n" + "=" * 60)
print("PASOS 1-4 COMPLETADOS")
print("=" * 60)
print(f"\nDEM crudo:        {DEM_CRUDO}")
print(f"DEM microrelieve: {DEM_MICRORELIEF}")
print(f"Resultados geo:   {CARPETA_GEO}")
print(f"Graficos:         {CARPETA_GRAFICOS}")
print("\nArchivos graficos generados:")
for fname in sorted(os.listdir(CARPETA_GRAFICOS)):
    if fname.endswith('.png'):
        print(f"  - {fname}")

# ============================================================
# PASO 5 - GENERAR POLIGONO GEOMORFOLOGICO
# ============================================================
print("\n" + "=" * 60)
print("PASO 5: GENERAR POLIGONO GEOMORFOLOGICO")
print("(Un solo poligono, sin islas ni huecos)")
print("=" * 60)

from rasterio.features import shapes as rio_shapes, rasterize
import geopandas as gpd
from scipy.ndimage import binary_dilation, binary_fill_holes
from shapely.ops import unary_union
from shapely.geometry import Polygon, MultiPolygon

# ---------- tipo de analisis ----------
if TIPO_ANALISIS_GEO == "HAND_TWI":
    raster_geo = zonas_hand_twi
    CLASES_INUNDABLES_GEO = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    USAR_INDICE_CONTINUO_GEO = False
elif TIPO_ANALISIS_GEO == "INDICE":
    raster_geo = indice_inundabilidad
    USAR_INDICE_CONTINUO_GEO = True
else:
    raise ValueError(f"TIPO_ANALISIS_GEO '{TIPO_ANALISIS_GEO}' no valido. Usar: HAND_TWI o INDICE")

# ---------- salidas ----------
nombre_geo_crudo = f"poligono_geomorfologico_{TIPO_ANALISIS_GEO}_CRUDO.shp"
nombre_geo_final = f"poligono_geomorfologico_{TIPO_ANALISIS_GEO}.shp"
ruta_geo_crudo   = os.path.join(CARPETA_GEO, nombre_geo_crudo)
ruta_geo_final   = os.path.join(CARPETA_GEO, nombre_geo_final)

# ---------- funciones auxiliares ----------
def _obtener_utm_epsg(lon, lat):
    zone = int((lon + 180) / 6) + 1
    return f"EPSG:{32600 + zone}" if lat >= 0 else f"EPSG:{32700 + zone}"

def _eliminar_huecos(geom):
    if geom.is_empty:
        return geom
    if isinstance(geom, Polygon):
        return Polygon(geom.exterior)
    elif isinstance(geom, MultiPolygon):
        return MultiPolygon([Polygon(p.exterior) for p in geom.geoms])
    return geom

def _forzar_poligono_unico(gdf, geom_hidro_ref):
    if len(gdf) == 0:
        return gdf
    geom_unida = unary_union(gdf.geometry)
    geom_unida = _eliminar_huecos(geom_unida)
    if isinstance(geom_unida, MultiPolygon):
        partes = list(geom_unida.geoms)
        print(f"    Detectadas {len(partes)} islas separadas, unificando...")
        partes.sort(key=lambda p: p.area, reverse=True)
        envolvente = geom_hidro_ref.convex_hull
        for buf_dist in [10, 25, 50, 100, 200, 500]:
            partes_buf      = [p.buffer(buf_dist, resolution=16) for p in partes]
            union_buf       = unary_union(partes_buf)
            env_margen      = envolvente.buffer(buf_dist * 2, resolution=16)
            union_recortada = union_buf.intersection(env_margen)
            if isinstance(union_recortada, Polygon):
                candidato = union_recortada.buffer(-buf_dist, resolution=16)
                if not candidato.is_empty:
                    geom_unida = candidato
                    print(f"    Islas unidas con buffer de {buf_dist}m")
                    break
        else:
            print("    Usando convex hull para unir todas las partes")
            geom_unida = unary_union(partes).convex_hull
    geom_unida = _eliminar_huecos(geom_unida)
    if isinstance(geom_unida, MultiPolygon):
        partes = sorted(geom_unida.geoms, key=lambda p: p.area, reverse=True)
        geom_unida = _eliminar_huecos(partes[0])
        print(f"    Se tomo el poligono mas grande ({partes[0].area/10000:.2f} ha)")
    geom_unida = geom_unida.buffer(0)
    return gpd.GeoDataFrame(
        {'clase': ['geomorfologico'], 'tipo': [TIPO_ANALISIS_GEO]},
        geometry=[geom_unida], crs=gdf.crs
    )

def _suavizar_iterativo(gdf, iteraciones, buf):
    gdf_r = gdf.copy()
    for i in range(iteraciones):
        print(f"    Iteracion {i+1}/{iteraciones}...")
        gdf_r['geometry'] = gdf_r.geometry.buffer(buf, resolution=16)
        gdf_r['geometry'] = gdf_r.buffer(0)
        gdf_r['geometry'] = gdf_r.geometry.buffer(-buf, resolution=16)
        gdf_r['geometry'] = gdf_r.buffer(0)
        gdf_r = gdf_r[~gdf_r.geometry.is_empty].copy()
    return gdf_r

def _suavizar_erosion(gdf, buf, pasadas=1):
    gdf_r = gdf.copy()
    for p in range(pasadas):
        print(f"    Pasada {p+1}/{pasadas}: erosion-dilatacion {buf}m...")
        gdf_r['geometry'] = gdf_r.geometry.buffer(-buf, resolution=32)
        gdf_r['geometry'] = gdf_r.buffer(0)
        gdf_r = gdf_r[~gdf_r.geometry.is_empty].copy()
        gdf_r['geometry'] = gdf_r.geometry.buffer(buf, resolution=32)
        gdf_r['geometry'] = gdf_r.buffer(0)
    return gdf_r

def _chaikin_smooth_gdf(gdf, iteraciones=4):
    """Suaviza poligonos con el algoritmo Chaikin (corner-cutting).
    Elimina los bordes cuadrados/pixelados generando curvas suaves."""
    def _chaikin_coords(coords, n):
        pts = list(coords)
        for _ in range(n):
            new_pts = []
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]
                q = (0.75*p0[0] + 0.25*p1[0], 0.75*p0[1] + 0.25*p1[1])
                r = (0.25*p0[0] + 0.75*p1[0], 0.25*p0[1] + 0.75*p1[1])
                new_pts.extend([q, r])
            new_pts.append(new_pts[0])
            pts = new_pts
        return pts

    def _smooth_geom(geom):
        if isinstance(geom, Polygon):
            ext = _chaikin_coords(list(geom.exterior.coords), iteraciones)
            return Polygon(ext)
        elif isinstance(geom, MultiPolygon):
            return MultiPolygon([
                Polygon(_chaikin_coords(list(p.exterior.coords), iteraciones))
                for p in geom.geoms
            ])
        return geom

    gdf_r = gdf.copy()
    gdf_r['geometry'] = gdf_r.geometry.apply(_smooth_geom)
    gdf_r['geometry'] = gdf_r.buffer(0)
    return gdf_r[~gdf_r.geometry.is_empty].copy()

# ---------- procesamiento ----------
print(f"\nTipo de analisis: {TIPO_ANALISIS_GEO}")
print(f"Raster: {os.path.basename(raster_geo)}")

if not os.path.exists(raster_geo):
    print(f"\nERROR: No se encontro el raster: {raster_geo}")
elif not os.path.exists(SHAPEFILE_HIDRO):
    print(f"\nERROR: No se encontro el shapefile hidrologico: {SHAPEFILE_HIDRO}")
else:
    print("\n[1/8] Cargando datos...")
    with rasterio.open(raster_geo) as src:
        raster_data_geo = src.read(1)
        transform_geo   = src.transform
        crs_raster_geo  = src.crs
    print(f"  Raster: {raster_data_geo.shape} | CRS: {crs_raster_geo}")
    print(f"  Rango: {np.nanmin(raster_data_geo):.3f} - {np.nanmax(raster_data_geo):.3f}")

    gdf_hidro_geo = gpd.read_file(SHAPEFILE_HIDRO)
    if gdf_hidro_geo.crs != crs_raster_geo:
        try:
            gdf_hidro_geo = gdf_hidro_geo.to_crs(crs_raster_geo)
        except Exception as _e_crs:
            # LOCAL_CS o CRS no reconocido por conflicto PROJ: intentar EPSG:9377
            # (MAGNA-SIRGAS 2018 / Origen-Nacional, CRS nacional de Colombia)
            print(f"  Advertencia CRS to_crs fallo ({_e_crs}). Intentando EPSG:9377...")
            try:
                gdf_hidro_geo = gdf_hidro_geo.to_crs(epsg=9377)
            except Exception as _e2:
                print(f"  Advertencia: EPSG:9377 tambien fallo ({_e2}). Usando CRS original del shape.")
    print("  Eliminando huecos del poligono hidrologico...")
    gdf_hidro_geo['geometry'] = gdf_hidro_geo.geometry.apply(_eliminar_huecos)
    geom_hidro_limpia = _eliminar_huecos(unary_union(gdf_hidro_geo.geometry))
    gdf_hidro_geo = gpd.GeoDataFrame({'id': [1]}, geometry=[geom_hidro_limpia], crs=gdf_hidro_geo.crs)

    print("\n[2/8] Creando mascara inundable...")
    if USAR_INDICE_CONTINUO_GEO:
        mascara_geo = (raster_data_geo >= UMBRAL_INDICE_GEO).astype(np.uint8)
        print(f"  Umbral indice >= {UMBRAL_INDICE_GEO}")
    else:
        mascara_geo = np.isin(raster_data_geo, CLASES_INUNDABLES_GEO).astype(np.uint8)
        print(f"  Clases: {CLASES_INUNDABLES_GEO}")

    if SUAVIZADO_MORF_GEO:
        from scipy.ndimage import binary_closing as _bc_geo, binary_opening as _bo_geo
        est_geo = np.ones((TAMANO_KERNEL_GEO, TAMANO_KERNEL_GEO))
        mascara_geo = _bc_geo(mascara_geo, structure=est_geo, iterations=1).astype(np.uint8)
        mascara_geo = _bo_geo(mascara_geo, structure=est_geo, iterations=1).astype(np.uint8)

    
    semilla_geo = rasterize(
        [(geom_hidro_limpia, 1)],
        out_shape=raster_data_geo.shape,
        transform=transform_geo,
        fill=0, dtype=np.uint8
    )
    px_semilla = np.sum(semilla_geo)


    if px_semilla == 0:
        print("\n  ADVERTENCIA: semilla vacia. Verificar solapamiento raster-hidrologico.")
    else:
        print("\n[4/8] Flood fill hasta barrera natural...")
        resultado_geo = semilla_geo.copy()
        est3_geo = np.ones((3, 3), dtype=np.uint8)
        px_ant_geo = 0
        for it_geo in range(MAX_ITERACIONES_GEO):
            dilatado_geo = binary_dilation(resultado_geo, structure=est3_geo).astype(np.uint8)
            nuevo_geo    = dilatado_geo & mascara_geo
            px_act_geo   = np.sum(nuevo_geo)
            if px_act_geo == px_ant_geo:
                print(f"  Convergio en iteracion {it_geo}")
                break
            resultado_geo = nuevo_geo
            px_ant_geo    = px_act_geo
            if it_geo % 20 == 0 and it_geo > 0:
                print(f"    Iteracion {it_geo}: {px_act_geo:,} px")

        resultado_geo = (resultado_geo | semilla_geo).astype(np.uint8)
        from scipy.ndimage import binary_closing as _bc2_geo
        kernel5_geo   = np.ones((5, 5), dtype=np.uint8)
        resultado_geo = _bc2_geo(resultado_geo, structure=kernel5_geo, iterations=2).astype(np.uint8)
        resultado_geo = binary_fill_holes(resultado_geo).astype(np.uint8)

        features_geo = [
            {'properties': {'clase': 'geomorfologico', 'tipo': TIPO_ANALISIS_GEO}, 'geometry': g}
            for g, v in rio_shapes(resultado_geo, mask=(resultado_geo == 1), transform=transform_geo)
            if v == 1
        ]
        if not features_geo:
            print("  ERROR: no se generaron poligonos")
        else:
            gdf_geo = gpd.GeoDataFrame.from_features(features_geo, crs=crs_raster_geo)
            print(f"  Poligonos generados: {len(gdf_geo)}")

            print("\n[6/8] Reproyectando y filtrando...")
            crs_trab_geo = crs_raster_geo
            if gdf_geo.crs.is_geographic:
                bnds_geo = gdf_geo.total_bounds
                crs_utm_geo = _obtener_utm_epsg((bnds_geo[0]+bnds_geo[2])/2, (bnds_geo[1]+bnds_geo[3])/2)
                print(f"  Reproyectando a {crs_utm_geo}...")
                gdf_geo       = gdf_geo.to_crs(crs_utm_geo)
                gdf_hidro_geo = gdf_hidro_geo.to_crs(crs_utm_geo)
                crs_trab_geo  = crs_utm_geo

            gdf_geo['area_ha'] = gdf_geo.geometry.area / 10000
            n_antes_geo = len(gdf_geo)
            gdf_geo = gdf_geo[gdf_geo['area_ha'] >= AREA_MINIMA_GEO_HA].copy()
            print(f"  Filtrado (>={AREA_MINIMA_GEO_HA} ha): {len(gdf_geo)} (eliminados: {n_antes_geo-len(gdf_geo)})")

            if len(gdf_geo) == 0:
                print(f"  ADVERTENCIA: todos filtrados, usando {AREA_MINIMA_FALLBACK_GEO_HA} ha...")
                gdf_geo = gpd.GeoDataFrame.from_features(features_geo, crs=crs_raster_geo).to_crs(crs_trab_geo)
                gdf_geo['area_ha'] = gdf_geo.geometry.area / 10000
                gdf_geo = gdf_geo[gdf_geo['area_ha'] >= AREA_MINIMA_FALLBACK_GEO_HA].copy()

            gdf_geo['perimetro'] = gdf_geo.geometry.length
            gdf_geo.to_file(ruta_geo_crudo, driver='ESRI Shapefile')

            print("\n[7/8] Unificando en un solo poligono...")
            geom_hidro_ref_geo = unary_union(gdf_hidro_geo.geometry)
            gdf_geo = _forzar_poligono_unico(gdf_geo, geom_hidro_ref_geo)

            if SUAVIZAR_GEO and len(gdf_geo) > 0:
                print("\n[8/8] Smooth Line...")
                # Unir todo antes de suavizar para evitar artefactos entre partes
                geom_pre = _eliminar_huecos(unary_union(gdf_geo.geometry))
                if geom_pre.is_empty:
                    print("  ADVERTENCIA: geometria vacia antes del suavizado, usando CRUDO.")
                else:
                    # [1/2] Simplify: elimina escalones de pixel del raster
                    print(f"  [1/2] Simplify ({SIMPLIFY_TOLERANCIA_GEO}m)...")
                    geom_simp = geom_pre.simplify(SIMPLIFY_TOLERANCIA_GEO, preserve_topology=True)
                    if geom_simp.is_empty:
                        geom_simp = geom_pre
                    # [2/2] Chaikin: curvas organicas suaves
                    if SMOOTH_CHAIKIN_GEO:
                        print(f"  [2/2] Chaikin ({CHAIKIN_ITERACIONES_GEO} iteraciones)...")
                        gdf_tmp = gpd.GeoDataFrame(
                            {'clase': ['geomorfologico'], 'tipo': [TIPO_ANALISIS_GEO]},
                            geometry=[geom_simp], crs=gdf_geo.crs
                        )
                        gdf_geo = _chaikin_smooth_gdf(gdf_tmp, CHAIKIN_ITERACIONES_GEO)
                    else:
                        gdf_geo = gpd.GeoDataFrame(
                            {'clase': ['geomorfologico'], 'tipo': [TIPO_ANALISIS_GEO]},
                            geometry=[geom_simp], crs=gdf_geo.crs
                        )

            # Limpieza final
            geom_final_geo = _eliminar_huecos(unary_union(gdf_geo.geometry))
            if isinstance(geom_final_geo, MultiPolygon):
                partes_fin = sorted(geom_final_geo.geoms, key=lambda p: p.area, reverse=True)
                geom_final_geo = _eliminar_huecos(partes_fin[0])
                print(f"  Suavizado genero {len(partes_fin)} partes, se tomo la mayor")

            gdf_geo = gpd.GeoDataFrame(
                {'clase': ['geomorfologico'], 'tipo': [TIPO_ANALISIS_GEO]},
                geometry=[geom_final_geo], crs=gdf_geo.crs
            )
            gdf_geo['area_m2']   = gdf_geo.geometry.area
            gdf_geo['area_ha']   = gdf_geo['area_m2'] / 10000
            gdf_geo['perimetro'] = gdf_geo.geometry.length
            gdf_geo.to_file(ruta_geo_final, driver='ESRI Shapefile')

            gdf_h_cmp     = gdf_hidro_geo.to_crs(gdf_geo.crs)
            area_hidro_ha = gdf_h_cmp.geometry.area.sum() / 10000
            area_geo_ha   = gdf_geo['area_ha'].sum()
            dif_geo       = area_geo_ha - area_hidro_ha

            print("\n" + "=" * 60)
            print("PASO 5 COMPLETADO")
            print("=" * 60)
            print(f"\nArchivo: {ruta_geo_final}")
            print(f"  Tipo geometria:  {gdf_geo.geometry.iloc[0].geom_type}")
            n_huecos_geo = len(list(gdf_geo.geometry.iloc[0].interiors)) if isinstance(gdf_geo.geometry.iloc[0], Polygon) else 'N/A'
            print(f"  Huecos internos: {n_huecos_geo}")
            print(f"  Area:            {area_geo_ha:.2f} ha")
            print(f"\nComparacion con hidrologico:")
            print(f"  Area hidrologica:    {area_hidro_ha:.2f} ha")
            print(f"  Area geomorfologica: {area_geo_ha:.2f} ha")
            if area_hidro_ha > 0:
                print(f"  Diferencia:          {dif_geo:.2f} ha (+{(dif_geo/area_hidro_ha)*100:.1f}%)")

print("\n" + "=" * 60)
print("PROCESO COMPLETADO")
print("=" * 60)
