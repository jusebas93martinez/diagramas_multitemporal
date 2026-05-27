# -*- coding: utf-8 -*-
"""
SENTINEL-1 SAR: COMPOSITE DE AGUA POR RANGO DE FECHAS
======================================================
Estrategia:
  1. Reune TODAS las imagenes SAR del rango (+-ventana alrededor del mes objetivo)
  2. Crea composite median (VV y VH) -> reduce ruido speckle
  3. Descarga por tiles y une en mosaico
  4. Clasifica agua con umbral dB -> TIF binario

Ventaja sobre imagen unica:
  - El median de multiples pasadas reduce el ruido de speckle de SAR
  - Si una fecha tiene nubes (irrelevante en SAR) o datos incompletos,
    otras pasadas del mismo periodo rellenan los gaps
  - Detecta agua con mayor consistencia que una sola imagen
"""

import ee
import geemap
import os
import sys
import numpy as np
import rasterio
from rasterio.merge import merge
from rasterio.enums import Resampling
from datetime import datetime, timedelta

# ============================================================================
# PARAMETROS DE USUARIO - CONFIGURA AQUI
# ============================================================================
direccion_shp     = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\POLIGONO\POLIGONO.shp"
directorio_salida = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\SAR"
# Fecha central del composite
ANIO_OBJETIVO = 2024
MES_OBJETIVO  = 9

# Ventana de busqueda en dias a cada lado del mes objetivo
# 60 dias = aprox 2 meses antes y 2 meses despues
DIAS_VENTANA = 30

# Orbita: intentara ASCENDING primero, luego DESCENDING si no hay imagenes
MODO_ORBITA_PREFERIDO = 'ASCENDING'

# Parametros tecnicos
CRS_EXPORTACION = 'EPSG:32618'
SCALE           = 10
BUFFER_METROS   = 3000

# Umbral para clasificacion de agua (dB)
# Tipico: -14 a -16 dB para regiones tropicales
UMBRAL_DB = -14

# Eliminar tiles temporales despues del merge
ELIMINAR_TILES = True

# ============================================================================
# INICIALIZAR EARTH ENGINE
# ============================================================================
try:
    ee.Initialize(project='precipitaciones-459216')
    print("Earth Engine inicializado\n")
except Exception:
    ee.Authenticate()
    ee.Initialize(project='precipitaciones-459216')

os.makedirs(directorio_salida, exist_ok=True)
carpeta_binario = os.path.join(directorio_salida, 'CLASIFICACION_AGUA')
os.makedirs(carpeta_binario, exist_ok=True)

# ============================================================================
# CARGAR SHAPEFILE Y CREAR TILES
# ============================================================================
print("Cargando shapefile...")
try:
    ee_shape = geemap.shp_to_ee(direccion_shp)
    region   = ee_shape.geometry().buffer(BUFFER_METROS).bounds()
    print(f"Region cargada con buffer de {BUFFER_METROS} m\n")
except Exception as e:
    print(f"ERROR al cargar shapefile: {e}")
    sys.exit(1)

# Tiles 2x2
bbox = ee.Geometry(region).bounds()
ring = ee.List(bbox.coordinates().get(0))
p0   = ee.List(ring.get(0))
p2   = ee.List(ring.get(2))

xmin = ee.Number(p0.get(0)); ymin = ee.Number(p0.get(1))
xmax = ee.Number(p2.get(0)); ymax = ee.Number(p2.get(1))
midx = xmin.add(xmax).divide(2)
midy = ymin.add(ymax).divide(2)

tiles = [
    ("SW", ee.Geometry.Rectangle([xmin, ymin, midx, midy], geodesic=False)),
    ("NW", ee.Geometry.Rectangle([xmin, midy, midx, ymax], geodesic=False)),
    ("SE", ee.Geometry.Rectangle([midx, ymin, xmax, midy], geodesic=False)),
    ("NE", ee.Geometry.Rectangle([midx, midy, xmax, ymax], geodesic=False)),
]

# ============================================================================
# BUSCAR IMAGENES EN EL RANGO
# ============================================================================
fecha_centro  = datetime(ANIO_OBJETIVO, MES_OBJETIVO, 15)
fecha_inicio  = fecha_centro - timedelta(days=DIAS_VENTANA)
fecha_fin     = fecha_centro + timedelta(days=DIAS_VENTANA)
inicio_str    = fecha_inicio.strftime('%Y-%m-%d')
fin_str       = fecha_fin.strftime('%Y-%m-%d')

print("=" * 60)
print(f"COMPOSITE SAR  |  {ANIO_OBJETIVO}-{MES_OBJETIVO:02d}")
print(f"Rango: {inicio_str}  a  {fin_str}  ({DIAS_VENTANA*2} dias)")
print("=" * 60)

def buscar_coleccion(modo_orbita):
    """Filtra la coleccion S1 para el rango y orbita dados."""
    return (
        ee.ImageCollection('COPERNICUS/S1_GRD')
        .filterBounds(region)
        .filterDate(inicio_str, fin_str)
        .filter(ee.Filter.eq('instrumentMode', 'IW'))
        .filter(ee.Filter.eq('orbitProperties_pass', modo_orbita))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))
        .select(['VV', 'VH'])
    )

# Intentar orbita preferida, si no hay imagenes probar la otra
modo_orbita  = MODO_ORBITA_PREFERIDO
coleccion    = buscar_coleccion(modo_orbita)
num_imgs     = coleccion.size().getInfo()
print(f"\nOrbita {modo_orbita}: {num_imgs} imagenes encontradas")

if num_imgs == 0:
    modo_alterno = 'DESCENDING' if modo_orbita == 'ASCENDING' else 'ASCENDING'
    print(f"  -> Probando orbita alterna: {modo_alterno}...")
    coleccion = buscar_coleccion(modo_alterno)
    num_imgs  = coleccion.size().getInfo()
    print(f"  -> Orbita {modo_alterno}: {num_imgs} imagenes encontradas")
    if num_imgs > 0:
        modo_orbita = modo_alterno
    else:
        # Ultimo intento: ampliar ventana al doble
        print(f"\n  -> Sin imagenes. Ampliando ventana a {DIAS_VENTANA*2} dias...")
        inicio_ext = (fecha_centro - timedelta(days=DIAS_VENTANA*2)).strftime('%Y-%m-%d')
        fin_ext    = (fecha_centro + timedelta(days=DIAS_VENTANA*2)).strftime('%Y-%m-%d')
        coleccion  = (
            ee.ImageCollection('COPERNICUS/S1_GRD')
            .filterBounds(region)
            .filterDate(inicio_ext, fin_ext)
            .filter(ee.Filter.eq('instrumentMode', 'IW'))
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV'))
            .select(['VV', 'VH'])
        )
        num_imgs = coleccion.size().getInfo()
        print(f"  -> Ventana ampliada ({inicio_ext} a {fin_ext}): {num_imgs} imagenes")
        if num_imgs == 0:
            print("\nERROR: No hay imagenes SAR disponibles para esta region/periodo.")
            print("Verifica que Sentinel-1 cubra esta area geografica.")
            sys.exit(1)

# Mostrar fechas disponibles
print(f"\nImagenes en el rango ({num_imgs} total):")
try:
    timestamps = coleccion.aggregate_array('system:time_start').getInfo()
    fechas_unicas = sorted(set(
        datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
        for ts in timestamps
    ))
    for f in fechas_unicas:
        print(f"  - {f}")
except Exception:
    print("  (no se pudo listar fechas individuales)")

# ============================================================================
# CREAR COMPOSITE MEDIAN
# ============================================================================
print(f"\nCreando composite median de {num_imgs} imagenes...")
composite = coleccion.median().clip(region)
print("  -> Composite listo")

# ============================================================================
# DESCARGA POR TILES
# ============================================================================
print(f"\n{'=' * 60}")
print("DESCARGANDO TILES")
print("=" * 60)

etiqueta    = f"S1_{modo_orbita}_{ANIO_OBJETIVO}_{MES_OBJETIVO:02d}_COMPOSITE"
rutas_tiles = []

for tile_nombre, tile_geom in tiles:
    nombre_tile = f"{etiqueta}_TILE-{tile_nombre}.tif"
    ruta_tile   = os.path.join(directorio_salida, nombre_tile)

    try:
        print(f"  Tile {tile_nombre}...", end=" ", flush=True)
        geemap.ee_export_image(
            composite,
            filename=ruta_tile,
            scale=SCALE,
            region=tile_geom,
            crs=CRS_EXPORTACION,
        )
        if os.path.exists(ruta_tile):
            rutas_tiles.append(ruta_tile)
            print("OK")
        else:
            print("VACIO (sin datos en este tile)")
    except Exception as e:
        print(f"ERROR: {e}")

# ============================================================================
# MERGE DE TILES
# ============================================================================
print(f"\n{'=' * 60}")
print("UNIENDO TILES")
print("=" * 60)

rutas_validas = [r for r in rutas_tiles if os.path.exists(r)]

if not rutas_validas:
    print("ERROR: No se descargó ningún tile.")
    sys.exit(1)

ruta_merge = None

if len(rutas_validas) >= 2:
    try:
        src_files  = [rasterio.open(fp) for fp in rutas_validas]
        mosaic_arr, out_trans = merge(src_files, resampling=Resampling.nearest)
        out_meta   = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff", "compress": "lzw",
            "height": mosaic_arr.shape[1], "width": mosaic_arr.shape[2],
            "transform": out_trans, "crs": src_files[0].crs,
        })
        nombre_merge = f"{etiqueta}_MERGE.tif"
        ruta_merge   = os.path.join(directorio_salida, nombre_merge)
        with rasterio.open(ruta_merge, "w", **out_meta) as dst:
            dst.write(mosaic_arr)
        for src in src_files:
            src.close()
        print(f"  Mosaico creado: {nombre_merge}")

        if ELIMINAR_TILES:
            for ruta in rutas_validas:
                try:
                    os.remove(ruta)
                except Exception:
                    pass
            print("  Tiles temporales eliminados")
    except Exception as e:
        print(f"  Error en merge: {e}")
        ruta_merge = rutas_validas[0]
else:
    ruta_merge = rutas_validas[0]
    print(f"  Solo 1 tile disponible, usando directamente")

if not ruta_merge or not os.path.exists(ruta_merge):
    print("ERROR: No se pudo generar el mosaico.")
    sys.exit(1)

# ============================================================================
# CLASIFICACION BINARIA DE AGUA
# ============================================================================
print(f"\n{'=' * 60}")
print(f"CLASIFICACION DE AGUA  (VV < {UMBRAL_DB} dB = agua)")
print("=" * 60)

nombre_binario = f"S1_AGUA_BINARIO_{ANIO_OBJETIVO}_{MES_OBJETIVO:02d}.tif"
ruta_binario   = os.path.join(carpeta_binario, nombre_binario)

porcentaje_agua = None
try:
    with rasterio.open(ruta_merge) as src:
        vv_banda = src.read(1).astype('float32')
        perfil   = src.profile.copy()

        # Mascara de nodata (valores muy bajos o nan)
        mascara_valida  = np.isfinite(vv_banda) & (vv_banda > -50)
        clasificacion   = np.where(mascara_valida & (vv_banda < UMBRAL_DB), 1, 0).astype('uint8')

        total_validos   = int(np.sum(mascara_valida))
        pixeles_agua    = int(np.sum(clasificacion == 1))
        porcentaje_agua = (pixeles_agua / total_validos * 100) if total_validos > 0 else 0

        print(f"  Pixeles validos:  {total_validos:,}")
        print(f"  Pixeles agua:     {pixeles_agua:,}  ({porcentaje_agua:.2f}%)")
        print(f"  Pixeles no-agua:  {total_validos - pixeles_agua:,}")

        perfil.update(dtype=rasterio.uint8, count=1, nodata=255, compress='lzw')
        with rasterio.open(ruta_binario, 'w', **perfil) as dst:
            dst.write(clasificacion, 1)
        print(f"\n  Binario guardado: {nombre_binario}")

except Exception as e:
    print(f"  Error en clasificacion: {e}")

# ============================================================================
# RESUMEN FINAL
# ============================================================================
print(f"\n{'=' * 60}")
print("PROCESO COMPLETADO")
print("=" * 60)
print(f"Periodo:          {inicio_str}  a  {fin_str}")
print(f"Orbita usada:     {modo_orbita}")
print(f"Imagenes en composite: {num_imgs}")
print(f"Umbral agua:      {UMBRAL_DB} dB  (VV)")
if porcentaje_agua is not None:
    print(f"Agua detectada:   {porcentaje_agua:.2f}%")
print(f"\nArchivos:")
print(f"  SAR composite:  {directorio_salida}")
print(f"  Binario agua:   {carpeta_binario}")
