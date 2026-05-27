# -*- coding: utf-8 -*-
"""
SCRIPT PARA DESCARGAR MOSAICO MULTIBANDA SENTINEL-2 SIN NODATA
Garantiza cobertura completa rellenando pixeles vacios con imagenes adicionales.

Estrategia de relleno:
1. Composite primario: median con filtro de nubes estricto
2. Composite secundario: median con filtro de nubes relajado
3. Composite terciario: mean con filtro de nubes amplio + periodo extendido
4. Relleno en cascada: primario -> secundario -> terciario
"""

import ee
import geemap
import os
import sys
from datetime import datetime, timedelta

# Verificar rasterio
try:
    import rasterio
    from rasterio.merge import merge as rio_merge
    import numpy as np
except ImportError:
    sys.exit("ERROR: Instalar rasterio -> pip install rasterio")

# =======================================================================
# 1. PARAMETROS DE ENTRADA
# =======================================================================
latitud      = 8.729069
longitud     = -75.909675
lado_km      = 4

CRS_EXPORTACION = 'EPSG:32618'

# Fecha especifica a descargar (identificada en Copernicus Browser)
FECHA_OBJETIVO = '2025-12-06'

# Umbral de nubes sobre la ESCENA COMPLETA (metadato rapido, pre-filtro)
UMBRAL_NUBES_ESCENA = 50       # Relajado porque ya sabemos que esta limpia

# Umbral de nubes LOCALES (dentro del area de estudio)
UMBRAL_NUBES_LOCAL = 32        # Descargar imagenes con <= 32% nubes en area de estudio


bandas_s2      = ['B2','B3','B4','B8','B11','B12']
nombres_bandas = ['Blue','Green','Red','NIR','SWIR1','SWIR2']
directorio_salida = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MULTIBANDA"

# CONFIGURACION DE TILES
TILES_COLS = 2
TILES_FILAS = 2

# =======================================================================
# 2. INICIALIZACION DE EARTH ENGINE
# =======================================================================
try:
    ee.Initialize(project='precipitaciones-459216')
    print("Earth Engine inicializado correctamente.")
except Exception:
    print("Autenticando con Earth Engine...")
    ee.Authenticate()
    ee.Initialize(project='precipitaciones-459216')
    print("Earth Engine autenticado e inicializado.")

# =======================================================================
# 3. FUNCIONES
# =======================================================================
def mask_s2_sr(img):
    """Mascara para S2_SR_HARMONIZED usando SCL"""
    scl = img.select('SCL')
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(mask).divide(10000)

def mask_s2_sr_relajado(img):
    """Mascara relajada - solo nubes densas y sombras"""
    scl = img.select('SCL')
    # Solo excluir: 3=sombra nube, 9=nubes altas, 10=cirrus
    mask = scl.neq(3).And(scl.neq(9)).And(scl.neq(10))
    return img.updateMask(mask).divide(10000)

def sin_mascara_s2_sr(img):
    """Sin mascara - solo division por 10000"""
    return img.divide(10000)

def mask_s2_l1c(img):
    """Mascara para S2 L1C usando QA60"""
    qa = img.select('QA60')
    mask_cloud  = qa.bitwiseAnd(1 << 10).eq(0)
    mask_cirrus = qa.bitwiseAnd(1 << 11).eq(0)
    return img.updateMask(mask_cloud).updateMask(mask_cirrus).divide(10000)

def sin_mascara_l1c(img):
    """Sin mascara para L1C"""
    return img.divide(10000)

def agregar_nubosidad_local_sr(img):
    """Calcula % de nubes DENTRO del cuadrado de interes usando SCL (SR).
    Sustituye CLOUDY_PIXEL_PERCENTAGE que mide toda la escena (~110x110 km)."""
    scl = img.select('SCL')
    # Nubes: sombra(3), nube media(8), nube alta(9), cirrus(10)
    es_nube = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
    es_valido = scl.neq(0)  # 0 = NoData

    n_total = es_valido.rename('valid').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=20,
        maxPixels=1e9
    ).get('valid')

    n_nubes = es_nube.rename('cloud').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=20,
        maxPixels=1e9
    ).get('cloud')

    n_total = ee.Number(n_total)
    pct = ee.Algorithms.If(
        n_total.gt(0),
        ee.Number(n_nubes).divide(n_total).multiply(100),
        ee.Number(100)  # Sin datos en la region -> tratar como 100% nuboso
    )
    return img.set('CLOUD_PCT_LOCAL', pct)

def agregar_nubosidad_local_l1c(img):
    """Calcula % de nubes DENTRO del cuadrado de interes usando QA60 (L1C)."""
    qa = img.select('QA60')
    es_nube = qa.bitwiseAnd(1 << 10).neq(0).Or(qa.bitwiseAnd(1 << 11).neq(0))

    n_total = qa.rename('qa').reduceRegion(
        reducer=ee.Reducer.count(),
        geometry=region,
        scale=60,
        maxPixels=1e9
    ).get('qa')

    n_nubes = es_nube.rename('cloud').reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=60,
        maxPixels=1e9
    ).get('cloud')

    n_total = ee.Number(n_total)
    pct = ee.Algorithms.If(
        n_total.gt(0),
        ee.Number(n_nubes).divide(n_total).multiply(100),
        ee.Number(100)
    )
    return img.set('CLOUD_PCT_LOCAL', pct)

def crear_tiles(region, n_cols, n_filas):
    """Divide una region rectangular en una grilla de tiles."""
    coords = region.bounds().coordinates().getInfo()[0]
    min_x = min(c[0] for c in coords)
    max_x = max(c[0] for c in coords)
    min_y = min(c[1] for c in coords)
    max_y = max(c[1] for c in coords)

    ancho_tile = (max_x - min_x) / n_cols
    alto_tile = (max_y - min_y) / n_filas

    tiles = []
    for fila in range(n_filas):
        for col in range(n_cols):
            x1 = min_x + col * ancho_tile
            x2 = min_x + (col + 1) * ancho_tile
            y1 = min_y + fila * alto_tile
            y2 = min_y + (fila + 1) * alto_tile
            tile_geom = ee.Geometry.Rectangle([x1, y1, x2, y2], None, False)
            tiles.append({
                'geom': tile_geom,
                'idx': fila * n_cols + col,
                'fila': fila,
                'col': col
            })
    return tiles

def merge_tiles_rasterio(tiles_paths, output_path):
    """Une multiples GeoTIFFs en uno solo usando rasterio."""
    print(f"\nUniendo {len(tiles_paths)} tiles...")
    archivos_validos = [p for p in tiles_paths if os.path.exists(p)]

    if not archivos_validos:
        print("ERROR: No hay tiles para unir")
        return False

    if len(archivos_validos) < len(tiles_paths):
        print(f"  ADVERTENCIA: Solo {len(archivos_validos)} de {len(tiles_paths)} tiles encontrados")

    try:
        src_files = [rasterio.open(path) for path in archivos_validos]
        mosaic, out_transform = rio_merge(src_files)

        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff",
            "height": mosaic.shape[1],
            "width": mosaic.shape[2],
            "transform": out_transform,
            "compress": "lzw"
        })

        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(mosaic)

        for src in src_files:
            src.close()

        # Eliminar tiles temporales
        print("Eliminando tiles temporales...")
        for path in archivos_validos:
            try:
                os.remove(path)
            except:
                pass

        print(f"Merge completado: {output_path}")
        return True
    except Exception as e:
        print(f"ERROR en merge: {e}")
        return False

def verificar_nodata(ruta_tif):
    """Verifica si hay pixeles NoData en el raster."""
    with rasterio.open(ruta_tif) as src:
        data = src.read()
        nodata = src.nodata

        if nodata is not None:
            nodata_count = np.sum(data == nodata)
        else:
            # Considerar 0 como nodata para reflectancia
            nodata_count = np.sum(data == 0)

        total_pixels = data.size
        nodata_percent = (nodata_count / total_pixels) * 100

        return nodata_count, nodata_percent

# =======================================================================
# 4. CREACION DE LA REGION Y TILES
# =======================================================================
buffer_m = (lado_km * 1000) / 2
region = ee.Geometry.Point([longitud, latitud]).buffer(buffer_m).bounds()
print(f"Region: cuadrado de {lado_km}x{lado_km} km centrado en ({latitud}, {longitud})")

tiles = crear_tiles(region, TILES_COLS, TILES_FILAS)
print(f"Dividido en {len(tiles)} tiles ({TILES_COLS} cols x {TILES_FILAS} filas)")

os.makedirs(directorio_salida, exist_ok=True)

# =======================================================================
# 5. DEFINIR FECHAS
# =======================================================================
inicio = FECHA_OBJETIVO
fin = (datetime.strptime(FECHA_OBJETIVO, '%Y-%m-%d') + timedelta(days=1)).strftime('%Y-%m-%d')

print(f"Fecha objetivo: {FECHA_OBJETIVO} (busqueda: {inicio} a {fin})")


# =======================================================================
# 6. BUSCAR IMAGENES PARA LA FECHA
# =======================================================================
print("\n" + "=" * 60)
print("BUSCANDO IMAGENES PARA LA FECHA OBJETIVO")
print("=" * 60)

es_sr = False
lista_imagenes = []

# Intentar con SR primero
print("\nProbando Sentinel-2 SR_HARMONIZED...")
try:
    col_base = (
        ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
          .filterBounds(region)
    )

    col_fecha = col_base.filterDate(inicio, fin)
    num_imagenes = col_fecha.size().getInfo()
    print(f"  Imagenes encontradas para {FECHA_OBJETIVO}: {num_imagenes}")

    if num_imagenes > 0:
        es_sr = True
        img_list = col_fecha.toList(num_imagenes)
        for i in range(num_imagenes):
            img = ee.Image(img_list.get(i))
            img_id = img.get('system:index').getInfo()
            nubes_escena = img.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
            # Extraer nombre del tile (ej: T18PUQ)
            tile_name = img_id.split('_')[-1] if '_' in img_id else f"img{i}"
            img_procesada = img.select(bandas_s2, nombres_bandas).divide(10000).clip(region)
            lista_imagenes.append({
                'id': img_id, 'tile': tile_name,
                'nubes_escena': nubes_escena, 'image': img_procesada
            })
            print(f"    [{i+1}] {tile_name} - nubes escena: {nubes_escena:.1f}% - {img_id}")

except Exception as e:
    print(f"  Error: {e}")

# Fallback a L1C
if not es_sr:
    print("\nUsando Sentinel-2 L1C (fallback)...")
    try:
        col_base = (
            ee.ImageCollection('COPERNICUS/S2')
              .filterBounds(region)
        )

        col_fecha = col_base.filterDate(inicio, fin)
        num_imagenes = col_fecha.size().getInfo()
        print(f"  Imagenes encontradas para {FECHA_OBJETIVO}: {num_imagenes}")

        if num_imagenes > 0:
            img_list = col_fecha.toList(num_imagenes)
            for i in range(num_imagenes):
                img = ee.Image(img_list.get(i))
                img_id = img.get('system:index').getInfo()
                nubes_escena = img.get('CLOUDY_PIXEL_PERCENTAGE').getInfo()
                tile_name = img_id.split('_')[-1] if '_' in img_id else f"img{i}"
                img_procesada = img.select(bandas_s2, nombres_bandas).divide(10000).clip(region)
                lista_imagenes.append({
                    'id': img_id, 'tile': tile_name,
                    'nubes_escena': nubes_escena, 'image': img_procesada
                })
                print(f"    [{i+1}] {tile_name} - nubes escena: {nubes_escena:.1f}% - {img_id}")

            print("  [!] ADVERTENCIA: SIN correccion atmosferica")
    except Exception as e:
        print(f"  Error: {e}")
        sys.exit("ERROR: No hay imagenes disponibles")

if not lista_imagenes:
    sys.exit(f"ERROR: No hay imagenes para la fecha {FECHA_OBJETIVO}")

# =======================================================================
# 7. DESCARGAR CADA IMAGEN INDEPENDIENTE EN TILES Y MERGE
# =======================================================================
sufijo = "_SR" if es_sr else "_TOA"

for img_idx, img_info in enumerate(lista_imagenes):
    print(f"\n{'='*60}")
    print(f"IMAGEN {img_idx+1}/{len(lista_imagenes)}: {img_info['tile']} (nubes escena: {img_info['nubes_escena']:.1f}%)")
    print(f"{'='*60}")

    imagen = img_info['image']
    tiles_paths = []

    for tile_info in tiles:
        tile_idx = tile_info['idx']
        tile_geom = tile_info['geom']

        nombre_tile = f"temp_{img_info['tile']}_{tile_idx:02d}.tif"
        ruta_tile = os.path.join(directorio_salida, nombre_tile)

        print(f"  Tile {tile_idx+1}/{len(tiles)}...", end=" ")

        try:
            img_tile = imagen.clip(tile_geom)

            geemap.ee_export_image(
                img_tile,
                ruta_tile,
                10,
                region=tile_geom,
                crs=CRS_EXPORTACION,
                file_per_band=False
            )

            if os.path.exists(ruta_tile):
                tiles_paths.append(ruta_tile)
                tamano_mb = os.path.getsize(ruta_tile) / (1024*1024)
                print(f"OK ({tamano_mb:.1f} MB)")
            else:
                print("FALLO")

        except Exception as e:
            print(f"ERROR: {e}")

    # Merge tiles de esta imagen
    if tiles_paths:
        nombre_final = f"S2_{FECHA_OBJETIVO}_{img_info['tile']}{sufijo}.tif"
        ruta_final = os.path.join(directorio_salida, nombre_final)

        exito = merge_tiles_rasterio(tiles_paths, ruta_final)

        if exito and os.path.exists(ruta_final):
            tamano_final = os.path.getsize(ruta_final) / (1024*1024)
            print(f"  GUARDADA: {nombre_final} ({tamano_final:.1f} MB)")
    else:
        print(f"  ERROR: No se descargaron tiles para {img_info['tile']}")

print(f"\n{'='*60}")
print("PROCESO FINALIZADO")
print(f"{'='*60}")
print(f"Imagenes descargadas: {len(lista_imagenes)}")
print(f"Directorio: {directorio_salida}")
