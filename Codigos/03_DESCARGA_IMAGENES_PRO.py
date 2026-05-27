# -*- coding: utf-8 -*-
"""
SCRIPT PRO - MOSAICO ANUAL CON RELLENO DE NUBES
================================================
Incluye Landsat 1-9 + Sentinel-2 (1972 - presente).
Landsat 7 se usa SOLO como fallback cuando Landsat 5 no tiene datos (2001-2012),
aplicando correccion SLC-off para minimizar las franjas sin datos.

Cobertura por mision:
  Landsat 1 MSS:  1972 - 1978
  Landsat 2 MSS:  1975 - 1982
  Landsat 3 MSS:  1978 - 1983
  Landsat 4 MSS:  1982 - 1992
  Landsat 4 TM:   1982 - 1993
  Landsat 5 TM:   1984 - 2012  (preferido)
  
  Landsat 7 ETM+: 2001 - 2012  (fallback si L5 sin datos, con correccion SLC-off)
  Landsat 8 OLI:  2013 - presente
  Landsat 9 OLI:  2021 - presente
  Sentinel-2 L1C: 2015 - presente
  Sentinel-2 L2A: 2017 - presente

Estrategia:
1. Para cada mes objetivo, obtener la imagen con menos nubes como BASE
2. Identificar pixeles NoData o con valor 0
3. Rellenar con imagenes de OTROS meses del mismo año (priorizando menos nubes)
4. Resultado: Mosaico con minima cantidad de nubes/gaps
"""

import ee
import geemap
import os
import sys
import calendar
import math
from datetime import datetime

try:
    import rasterio
    from rasterio.merge import merge as rio_merge
except ImportError:
    sys.exit("Instalar librerias: pip install rasterio geemap")

# ==============================================================================
# 1. PARAMETROS DE ENTRADA
# ==============================================================================
direccion_shp      = r"E:\Documentos_compartidos\APTO\APTO.shp"
directorio_salida  = r"E:\Documentos_compartidos\APTO\IMG"

# Fechas a procesar: {año: [meses objetivo]}
# El script buscara primero en estos meses, luego rellenara con el resto del año
# El script buscara primero en estos meses, luego rellenara con el resto del año
FECHAS_A_PROCESAR = {
    2026: ['ENE','FEB','MAR','ABR','MAY','JUN','JUL','AGO','SEP','OCT','NOV','DIC'],
}

MESES_MAP = {
    'ENE': 1, 'FEB': 2, 'MAR': 3, 'ABR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AGO': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DIC': 12
}

MESES_NOMBRES = {v: k for k, v in MESES_MAP.items()}

umbral_nubes_escena  = 90   # Pre-filtro AMPLIO sobre escena completa (no descartar nada util)
umbral_nubes_aoi     = 5    # Filtro ESTRICTO: % nubes maximo sobre el area de estudio
umbral_nubes_aoi_relleno = 15  # Umbral AOI para buscar imagenes de relleno (si se necesita)
umbral_sin_relleno   = 5    # Si nubes_aoi <= este %, NO rellena con otros meses (queda natural)
buffer_km            = 3
CRS_EXPORTACION      = 'EPSG:32618'
LIMITE_DESCARGA_MB      = 48    # Límite real GEE getDownloadURL (50331648 bytes)
FACTOR_CORRECCION_PIX  = 2.5   # Corrección: estimación WGS84→UTM subestima ~2.4x los píxeles reales

# Meses para relleno (orden de preferencia: epoca seca primero)
MESES_RELLENO_ORDEN = [12, 1, 2, 3, 7, 8, 6, 11, 4, 5, 9, 10]

# ==============================================================================
# 2. INICIALIZACION EE
# ==============================================================================
try:
    ee.Initialize(project='precipitaciones-459216')
    print("Earth Engine inicializado")
except:
    ee.Authenticate()
    ee.Initialize(project='precipitaciones-459216')

# ==============================================================================
# 3. CONFIGURACION DE MISIONES
# Landsat 7 (LE07) excluido por problemas del SLC-off (franjas sin datos)
# ==============================================================================
MISIONES = {
    # ---- SENTINEL-2 ----
    'S2': {
        'id': 'COPERNICUS/S2_SR_HARMONIZED',
        'scale': 10,
        'bands': ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': True,
        'nombre': 'Sentinel-2 L2A',
        'tipo_mask': 'SCL',
        'cloud_param': 'CLOUDY_PIXEL_PERCENTAGE',
        'es_mss': False,
        'anio_inicio': 2017,
        'anio_fin': 2099,
    },
    'S2_L1C': {
        'id': 'COPERNICUS/S2',
        'scale': 10,
        'bands': ['B2', 'B3', 'B4', 'B8', 'B11', 'B12'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': True,
        'nombre': 'Sentinel-2 L1C (TOA)',
        'tipo_mask': 'QA60',
        'cloud_param': 'CLOUDY_PIXEL_PERCENTAGE',
        'es_mss': False,
        'anio_inicio': 2015,
        'anio_fin': 2099,
    },
    # ---- LANDSAT 9 ----
    'LC09': {
        'id': 'LANDSAT/LC09/C02/T1_L2',
        'scale': 30,
        'bands': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 9 L2',
        'tipo_mask': 'LANDSAT_SR',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': False,
        'anio_inicio': 2021,
        'anio_fin': 2099,
    },
    # ---- LANDSAT 8 ----
    'LC08': {
        'id': 'LANDSAT/LC08/C02/T1_L2',
        'scale': 30,
        'bands': ['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 8 L2',
        'tipo_mask': 'LANDSAT_SR',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': False,
        'anio_inicio': 2013,
        'anio_fin': 2099,
    },
    # ---- LANDSAT 7 ETM+ (fallback_only: solo cuando L5 no tiene datos, 2001-2012) ----
    'LE07': {
        'id': 'LANDSAT/LE07/C02/T1_L2',
        'scale': 30,
        'bands': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 7 ETM+ L2 (SLC-off corregido)',
        'tipo_mask': 'LANDSAT_SR',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': False,
        'anio_inicio': 2001,   # Solo periodo SLC-off donde L5 puede fallar
        'anio_fin': 2012,
        'fallback_only': True, # Usar SOLO si ninguna otra mision tiene datos
    },
    # ---- LANDSAT 5 TM ----
    'LT05': {
        'id': 'LANDSAT/LT05/C02/T1_L2',
        'scale': 30,
        'bands': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 5 TM L2',
        'tipo_mask': 'LANDSAT_SR',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': False,
        'anio_inicio': 1984,
        'anio_fin': 2012,
    },
    # ---- LANDSAT 4 TM ----
    'LT04': {
        'id': 'LANDSAT/LT04/C02/T1_L2',
        'scale': 30,
        'bands': ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B7'],
        'names': ['Blue', 'Green', 'Red', 'NIR', 'SWIR1', 'SWIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 4 TM L2',
        'tipo_mask': 'LANDSAT_SR',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': False,
        'anio_inicio': 1982,
        'anio_fin': 1993,
    },
    # ---- LANDSAT 4 MSS ----
    'LM04': {
        'id': 'LANDSAT/LM04/C02/T1',
        'scale': 60,
        'bands': ['B1', 'B2', 'B3', 'B4'],
        'names': ['Green', 'Red', 'NIR', 'NIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 4 MSS',
        'tipo_mask': 'MSS',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': True,
        'anio_inicio': 1982,
        'anio_fin': 1992,
    },
    # ---- LANDSAT 3 MSS ----
    'LM03': {
        'id': 'LANDSAT/LM03/C02/T1',
        'scale': 60,
        'bands': ['B4', 'B5', 'B6', 'B7'],
        'names': ['Green', 'Red', 'NIR', 'NIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 3 MSS',
        'tipo_mask': 'MSS',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': True,
        'anio_inicio': 1978,
        'anio_fin': 1983,
    },
    # ---- LANDSAT 2 MSS ----
    'LM02': {
        'id': 'LANDSAT/LM02/C02/T1',
        'scale': 60,
        'bands': ['B4', 'B5', 'B6', 'B7'],
        'names': ['Green', 'Red', 'NIR', 'NIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 2 MSS',
        'tipo_mask': 'MSS',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': True,
        'anio_inicio': 1975,
        'anio_fin': 1982,
    },
    # ---- LANDSAT 1 MSS ----
    'LM01': {
        'id': 'LANDSAT/LM01/C02/T1',
        'scale': 60,
        'bands': ['B4', 'B5', 'B6', 'B7'],
        'names': ['Green', 'Red', 'NIR', 'NIR2'],
        'usa_tiles': False,
        'nombre': 'Landsat 1 MSS',
        'tipo_mask': 'MSS',
        'cloud_param': 'CLOUD_COVER',
        'es_mss': True,
        'anio_inicio': 1972,
        'anio_fin': 1978,
    },
}

# ==============================================================================
# 4. FUNCIONES DE MASCARA
# ==============================================================================
def mask_s2_scl(img):
    scl = img.select('SCL')
    mask = scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)).And(scl.neq(11))
    return img.updateMask(mask)

def mask_s2_qa60(img):
    qa = img.select('QA60')
    mask = qa.bitwiseAnd(1 << 10).eq(0).And(qa.bitwiseAnd(1 << 11).eq(0))
    return img.updateMask(mask)

def mask_landsat_sr(img):
    qa = img.select('QA_PIXEL')
    mask = (qa.bitwiseAnd(1 << 1).eq(0)
              .And(qa.bitwiseAnd(1 << 3).eq(0))
              .And(qa.bitwiseAnd(1 << 4).eq(0)))
    optical = img.select('SR_B.').multiply(0.0000275).add(-0.2)
    return img.addBands(optical, None, True).updateMask(mask)

def mask_mss(img):
    """Mascara de nubes para Landsat MSS (QA_PIXEL en Collection 2)"""
    qa = img.select('QA_PIXEL')
    mask = (qa.bitwiseAnd(1 << 3).eq(0)
              .And(qa.bitwiseAnd(1 << 4).eq(0)))
    return img.updateMask(mask)

def obtener_funcion_mask(tipo):
    if tipo == 'SCL':
        return mask_s2_scl
    elif tipo == 'QA60':
        return mask_s2_qa60
    elif tipo == 'MSS':
        return mask_mss
    else:
        return mask_landsat_sr


def filtrar_por_nubes_aoi(coleccion, region, tipo_mask, scale, umbral):
    """
    Filtra imagenes calculando el % de nubes exactamente sobre el AOI,
    no sobre la escena completa del sensor.
    """
    def agregar_nube_aoi(img):
        if tipo_mask == 'LANDSAT_SR':
            qa = img.select('QA_PIXEL')
            cloud_mask = (qa.bitwiseAnd(1 << 3).neq(0)
                          .Or(qa.bitwiseAnd(1 << 4).neq(0)))
        elif tipo_mask == 'SCL':
            scl = img.select('SCL')
            cloud_mask = (scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9))
                          .Or(scl.eq(10)).Or(scl.eq(11)))
        elif tipo_mask == 'QA60':
            qa = img.select('QA60')
            cloud_mask = (qa.bitwiseAnd(1 << 10).neq(0)
                          .Or(qa.bitwiseAnd(1 << 11).neq(0)))
        else:  # MSS
            qa = img.select('QA_PIXEL')
            cloud_mask = (qa.bitwiseAnd(1 << 3).neq(0)
                          .Or(qa.bitwiseAnd(1 << 4).neq(0)))
        stats = cloud_mask.rename('cloud').reduceRegion(
            reducer=ee.Reducer.mean(),
            geometry=region,
            scale=scale,
            maxPixels=1e9
        )
        nube_aoi = ee.Number(stats.get('cloud')).multiply(100)
        return img.set('nubes_aoi', nube_aoi)
    return (coleccion
            .map(agregar_nube_aoi)
            .filter(ee.Filter.lte('nubes_aoi', umbral)))

def calc_mndwi(img):
    return img.normalizedDifference(['Green', 'SWIR1']).rename('MNDWI')

def calc_ndwi_mss(img):
    """NDWI para MSS (usa Green y NIR, sin SWIR disponible)"""
    return img.normalizedDifference(['Green', 'NIR']).rename('NDWI')

def corregir_slc_off(img):
    """
    Correccion SLC-off para Landsat 7 (post mayo-2003).
    Rellena las franjas sin datos con interpolacion focal progresiva.
    Estrategia: focal_median con radios crecientes (1->2->4->8 px),
    usando unmask en cascada para solo rellenar los gaps, no los pixeles validos.
    focal_median es mas robusto que focal_mean ante valores extremos en bordes.
    """
    fecha_img = ee.Date(img.get('system:time_start'))
    fecha_slc = ee.Date('2003-05-31')

    def aplicar_relleno(img):
        # Paso 1: radio 1 px
        f1 = img.focal_median(radius=1, kernelType='square', iterations=1)
        r1 = img.unmask(f1)
        # Paso 2: radio 2 px (cubre franjas tipicas de ~2-3 px)
        f2 = r1.focal_median(radius=2, kernelType='square', iterations=1)
        r2 = r1.unmask(f2)
        # Paso 3: radio 4 px (cubre franjas anchas en zonas de latitud alta)
        f3 = r2.focal_median(radius=4, kernelType='square', iterations=1)
        r3 = r2.unmask(f3)
        # Paso 4: radio 8 px (relleno final para gaps residuales)
        f4 = r3.focal_median(radius=8, kernelType='square', iterations=1)
        return r3.unmask(f4)

    return ee.Image(
        ee.Algorithms.If(
            fecha_img.millis().gte(fecha_slc.millis()),
            aplicar_relleno(img),
            img
        )
    )

# ==============================================================================
# 5. SELECCION DE MISION POR AÑO
# ==============================================================================
def obtener_mision_para_anio(anio):
    """
    Retorna lista de misiones disponibles para un año dado,
    ordenadas por preferencia (mejor resolucion/calidad primero).
    Landsat 7 aparece al final como fallback_only: se usa solo si
    ninguna otra mision produjo datos en ese mes.

    Cobertura:
      Landsat 1 MSS:  1972 - 1978
      Landsat 2 MSS:  1975 - 1982
      Landsat 3 MSS:  1978 - 1983
      Landsat 4 MSS:  1982 - 1992
      Landsat 4 TM:   1982 - 1993
      Landsat 5 TM:   1984 - 2012  (preferido)
      Landsat 7 ETM+: 2001 - 2012  (fallback si L5 sin datos)
      Landsat 8 OLI:  2013 - presente
      Landsat 9 OLI:  2021 - presente
      Sentinel-2 L1C: 2015 - presente
      Sentinel-2 L2A: 2017 - presente
    """
    # LE07 va al final: se evalua solo si las misiones preferidas no tienen datos
    orden_preferencia = [
        'S2', 'LC09', 'LC08', 'LT05', 'LT04',
        'LM04', 'LM03', 'LM02', 'LM01', 'LE07',
    ]

    disponibles = []
    for key in orden_preferencia:
        m = MISIONES[key]
        if m['anio_inicio'] <= anio <= m['anio_fin']:
            disponibles.append(key)

    if not disponibles:
        print(f"  [!] ADVERTENCIA: No hay misiones disponibles para {anio}")

    return disponibles

# ==============================================================================
# 6. FUNCION PRINCIPAL: CREAR MOSAICO CON RELLENO
# ==============================================================================
def obtener_info_imagenes(coleccion, cloud_param):
    """
    Obtiene lista de imagenes con IDs, % nubes escena y % nubes sobre AOI,
    ordenadas por nubes_aoi de menor a mayor.
    """
    try:
        ids       = coleccion.aggregate_array('system:index').getInfo()
        nubes     = coleccion.aggregate_array(cloud_param).getInfo()
        fechas    = coleccion.aggregate_array('system:time_start').getInfo()
        nubes_aoi = coleccion.aggregate_array('nubes_aoi').getInfo()

        info = []
        for img_id, nube, nube_a, ts in zip(ids, nubes, nubes_aoi, fechas):
            fecha = datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d')
            info.append({
                'id': img_id,
                'nubes': nube if nube is not None else -1,
                'nubes_aoi': nube_a if nube_a is not None else -1,
                'fecha': fecha
            })
        info.sort(key=lambda x: x['nubes_aoi'])  # Ordenar por nubes sobre el AOI
        return info
    except:
        return []

def crear_mosaico_con_relleno(anio, mes_objetivo, region, mision_key):
    """
    Crea un mosaico para un mes objetivo, rellenando NoData con otros meses.

    Para misiones MSS: solo bandas Green, Red, NIR, NIR2 (sin MNDWI)
    Para misiones TM/OLI: 6 bandas opticas + MNDWI

    Retorna: (imagen, log_detallado, info_base)
    """
    datos = MISIONES[mision_key]
    fn_mask = obtener_funcion_mask(datos['tipo_mask'])
    cloud_param = datos['cloud_param']
    es_mss = datos.get('es_mss', False)

    log_relleno = []
    info_base = None

    # --- PASO 1: Imagen base del mes objetivo ---
    # Pre-filtro AMPLIO por escena (no descartar imagenes utiles), luego fino sobre AOI
    start_base = f"{anio}-{mes_objetivo:02d}-01"
    end_base = f"{anio}-{mes_objetivo:02d}-{calendar.monthrange(anio, mes_objetivo)[1]}"

    # Filtro escena amplio + filtro AOI estricto
    coll_base = (ee.ImageCollection(datos['id'])
                 .filterBounds(region)
                 .filterDate(start_base, end_base)
                 .filter(ee.Filter.lte(cloud_param, umbral_nubes_escena)))
    coll_base = filtrar_por_nubes_aoi(
        coll_base, region, datos['tipo_mask'], datos['scale'], umbral_nubes_aoi
    )

    num_base = coll_base.size().getInfo()
    umbral_usado = umbral_nubes_aoi

    if num_base == 0:
        # Segundo intento: relajar umbral AOI
        coll_base = (ee.ImageCollection(datos['id'])
                     .filterBounds(region)
                     .filterDate(start_base, end_base)
                     .filter(ee.Filter.lte(cloud_param, umbral_nubes_escena)))
        coll_base = filtrar_por_nubes_aoi(
            coll_base, region, datos['tipo_mask'], datos['scale'], umbral_nubes_aoi_relleno
        )
        num_base = coll_base.size().getInfo()
        umbral_usado = umbral_nubes_aoi_relleno

    if num_base == 0:
        # Ultimo intento: sin filtro de nubes AOI
        coll_base = (ee.ImageCollection(datos['id'])
                     .filterBounds(region)
                     .filterDate(start_base, end_base))
        coll_base = filtrar_por_nubes_aoi(
            coll_base, region, datos['tipo_mask'], datos['scale'], 100
        )
        num_base = coll_base.size().getInfo()
        umbral_usado = 100

    if num_base == 0:
        return None, ["Sin imagenes base"], None

    info_imgs_base = obtener_info_imagenes(coll_base, cloud_param)

    log_relleno.append("=" * 50)
    log_relleno.append(f"IMAGENES BASE - {MESES_NOMBRES[mes_objetivo]} {anio}")
    log_relleno.append(f"Mision: {datos['nombre']} | Umbral AOI: {umbral_usado}%")
    log_relleno.append(f"Resolucion: {datos['scale']}m | MSS: {es_mss}")
    log_relleno.append("=" * 50)

    for i, img_info in enumerate(info_imgs_base):
        nubes_str     = f"{img_info['nubes']:.1f}%"     if img_info['nubes'] >= 0     else "N/D"
        nubes_aoi_str = f"{img_info['nubes_aoi']:.1f}%" if img_info['nubes_aoi'] >= 0 else "N/D"
        log_relleno.append(f"  {i+1}. {img_info['id']}")
        log_relleno.append(f"     Fecha: {img_info['fecha']} | Nubes escena: {nubes_str} | Nubes AOI: {nubes_aoi_str}")

    if info_imgs_base:
        info_base = info_imgs_base[0]

    # Procesar coleccion base
    coll_proc = coll_base.map(fn_mask).select(datos['bands'], datos['names'])
    if mision_key == 'LE07':
        coll_proc = coll_proc.map(corregir_slc_off)
    img_base = coll_proc.median()

    # Agregar indice de agua
    if es_mss:
        img_final = img_base.addBands(calc_ndwi_mss(img_base))
    else:
        img_final = img_base.addBands(calc_mndwi(img_base))

    log_relleno.append(f"\nTOTAL BASE: {num_base} imagenes")

    # --- PASO 2: Decidir si rellenar o no ---
    # Si la mejor imagen tiene pocas nubes sobre el AOI, NO rellenar (queda natural)
    nubes_mejor = info_base['nubes_aoi'] if info_base and info_base['nubes_aoi'] >= 0 else 100
    necesita_relleno = nubes_mejor > umbral_sin_relleno

    meses_usados = [mes_objetivo]

    if not necesita_relleno:
        log_relleno.append("")
        log_relleno.append("=" * 50)
        log_relleno.append(f"SIN RELLENO: nubes AOI = {nubes_mejor:.1f}% <= {umbral_sin_relleno}%")
        log_relleno.append("Imagen natural sin parches de otros meses")
        log_relleno.append("=" * 50)
    else:
        log_relleno.append("")
        log_relleno.append("=" * 50)
        log_relleno.append(f"RELLENO NECESARIO: nubes AOI = {nubes_mejor:.1f}% > {umbral_sin_relleno}%")
        log_relleno.append("=" * 50)

        for mes_relleno in MESES_RELLENO_ORDEN:
            if mes_relleno == mes_objetivo or mes_relleno in meses_usados:
                continue

            start_rel = f"{anio}-{mes_relleno:02d}-01"
            end_rel = f"{anio}-{mes_relleno:02d}-{calendar.monthrange(anio, mes_relleno)[1]}"

            try:
                coll_relleno = (ee.ImageCollection(datos['id'])
                               .filterBounds(region)
                               .filterDate(start_rel, end_rel)
                               .filter(ee.Filter.lte(cloud_param, umbral_nubes_escena)))
                coll_relleno = filtrar_por_nubes_aoi(
                    coll_relleno, region, datos['tipo_mask'], datos['scale'], umbral_nubes_aoi_relleno
                )

                num_relleno = coll_relleno.size().getInfo()

                if num_relleno > 0:
                    info_imgs_relleno = obtener_info_imagenes(coll_relleno, cloud_param)

                    log_relleno.append(f"\n  {MESES_NOMBRES[mes_relleno]}: {num_relleno} imgs")
                    for img_info in info_imgs_relleno[:3]:
                        nubes_aoi_str = f"{img_info['nubes_aoi']:.1f}%" if img_info['nubes_aoi'] >= 0 else "N/D"
                        log_relleno.append(f"    - {img_info['id']} (escena: {img_info['nubes']:.1f}% | AOI: {nubes_aoi_str})")
                    if len(info_imgs_relleno) > 3:
                        log_relleno.append(f"    ... y {len(info_imgs_relleno)-3} mas")

                    coll_proc_rel = coll_relleno.map(fn_mask).select(datos['bands'], datos['names'])
                    if mision_key == 'LE07':
                        coll_proc_rel = coll_proc_rel.map(corregir_slc_off)
                    img_relleno = coll_proc_rel.median()

                    if es_mss:
                        img_relleno_full = img_relleno.addBands(calc_ndwi_mss(img_relleno))
                    else:
                        img_relleno_full = img_relleno.addBands(calc_mndwi(img_relleno))

                    img_final = img_final.unmask(img_relleno_full)
                    meses_usados.append(mes_relleno)

            except:
                pass

        # Relleno final con focal_mean solo si se necesito relleno
        img_focal = img_final.focal_mean(radius=2, kernelType='square', iterations=1)
        img_final = img_final.unmask(img_focal)

    log_relleno.append("")
    log_relleno.append("=" * 50)
    log_relleno.append(f"RESUMEN: {len(meses_usados)} meses usados")
    log_relleno.append(f"Meses: {', '.join([MESES_NOMBRES[m] for m in meses_usados])}")
    log_relleno.append("=" * 50)

    return img_final, log_relleno, info_base

# ==============================================================================
# 7. FUNCIONES DE EXPORTACION
# ==============================================================================
def merge_tiles_rasterio(tiles_paths, output_path):
    try:
        src_files = [rasterio.open(p) for p in tiles_paths if os.path.exists(p)]
        if not src_files:
            return
        mosaic, out_trans = rio_merge(src_files)
        out_meta = src_files[0].meta.copy()
        out_meta.update({
            "driver": "GTiff", "height": mosaic.shape[1],
            "width": mosaic.shape[2], "transform": out_trans, "compress": "lzw"
        })
        with rasterio.open(output_path, "w", **out_meta) as dest:
            dest.write(mosaic)
        for src in src_files:
            src.close()
        for path in tiles_paths:
            try:
                os.remove(path)
            except:
                pass
    except Exception as e:
        print(f"Error Merge: {e}")

def calcular_tiles_dinamicos(bbox, scale, n_bands):
    """
    Calcula los tiles necesarios para que cada descarga no supere LIMITE_DESCARGA_MB.

    bbox  : (minx, miny, maxx, maxy) en grados WGS84 — obtenido una sola vez al inicio
    scale : resolución en metros/píxel del sensor
    n_bands: número de bandas del producto a exportar

    Retorna lista de ee.Geometry.Rectangle.
    Si el área cabe en un solo tile devuelve [region_completa].

    Lógica de tamaño:
      - Convierte grados → metros usando la latitud media del AOI
      - Estima pixeles totales = (ancho_m / scale) × (alto_m / scale)
      - Tamaño Float32 = pixeles × bandas × 4 bytes
      - tiles = ceil(tamaño_MB / LIMITE_DESCARGA_MB)
      - grilla = ceil(sqrt(tiles))  → grilla cuadrada N×N
    """
    minx, miny, maxx, maxy = bbox

    avg_lat_rad = math.radians((miny + maxy) / 2.0)
    width_m  = (maxx - minx) * 111320.0 * math.cos(avg_lat_rad)
    height_m = (maxy - miny) * 110540.0

    n_pix_x   = max(1.0, width_m  / scale)
    n_pix_y   = max(1.0, height_m / scale)
    size_mb   = (n_pix_x * n_pix_y * n_bands * 4.0) / (1024.0 ** 2)
    # Aplica corrección: la conversión WGS84→metros subestima los píxeles reales en UTM
    size_mb_corr = size_mb * FACTOR_CORRECCION_PIX

    n_tiles   = max(1, math.ceil(size_mb_corr / LIMITE_DESCARGA_MB))
    grid_size = math.ceil(math.sqrt(n_tiles))

    # Detección de sensor por escala
    if scale <= 10:
        sensor_str = 'Sentinel (10m)'
    elif scale <= 30:
        sensor_str = 'Landsat TM/OLI (30m)'
    else:
        sensor_str = 'Landsat MSS (60m)'

    print(f"        [TILES] {sensor_str} | {n_bands}b | "
          f"{size_mb:.1f}MB est. → {size_mb_corr:.1f}MB corr. | "
          f"grilla {grid_size}×{grid_size} ({grid_size**2} tiles)")

    if grid_size <= 1:
        return [ee.Geometry.Rectangle([minx, miny, maxx, maxy], None, False)]

    x_step = (maxx - minx) / grid_size
    y_step = (maxy - miny) / grid_size
    tiles = []
    for row in range(grid_size):
        for col in range(grid_size):
            tiles.append(ee.Geometry.Rectangle(
                [minx + col * x_step,
                 miny + row * y_step,
                 minx + (col + 1) * x_step,
                 miny + (row + 1) * y_step],
                None, False
            ))
    return tiles


def exportar_productos(img, nombre, datos, bbox):
    """
    Exporta productos dividiendo automáticamente en tiles según tamaño estimado.

    - Detecta Sentinel (10m) vs Landsat TM/OLI (30m) vs Landsat MSS (60m) por escala.
    - Calcula la grilla N×N mínima para que cada tile <= LIMITE_DESCARGA_MB.
    - 1 tile  → descarga directa  (sin merge)
    - N tiles → descarga por tile + merge con rasterio
    """
    es_mss = datos.get('es_mss', False)

    if es_mss:
        productos = {
            'NDWI': (img.select('NDWI'),                    1),
            'RGB':  (img.select(['NIR', 'Red', 'Green']),   3),
            'IR':   (img.select(['NIR2', 'NIR', 'Red']),    3),
        }
    else:
        productos = {
            'MNDWI': (img.select('MNDWI'),                   1),
            'RGB':   (img.select(['Red', 'Green', 'Blue']),  3),
            'IR':    (img.select(['NIR', 'Red', 'Green']),   3),
        }

    for prod, (band_img, n_bands) in productos.items():
        carp = os.path.join(directorio_salida, prod)
        os.makedirs(carp, exist_ok=True)

        nombre_final = f"{nombre}_{prod}.tif"
        ruta_final   = os.path.join(carp, nombre_final)

        tiles = calcular_tiles_dinamicos(bbox, datos['scale'], n_bands)
        n     = len(tiles)

        try:
            if n == 1:
                geemap.ee_export_image(band_img, filename=ruta_final,
                                       scale=datos['scale'], region=tiles[0],
                                       crs=CRS_EXPORTACION)
            else:
                tiles_paths = []
                for i, tile in enumerate(tiles):
                    ruta_tile = os.path.join(carp, f"temp_{nombre}_{prod}_{i}.tif")
                    geemap.ee_export_image(band_img, filename=ruta_tile,
                                           scale=datos['scale'], region=tile,
                                           crs=CRS_EXPORTACION)
                    tiles_paths.append(ruta_tile)
                merge_tiles_rasterio(tiles_paths, ruta_final)

            grid = int(math.sqrt(n))
            print(f"        -> {prod}: OK ({grid}×{grid} tiles)")
        except Exception as e:
            print(f"        -> {prod}: ERROR ({e})")

# ==============================================================================
# 8. PROCESO PRINCIPAL
# ==============================================================================
print("=" * 70)
print("MOSAICO ANUAL CON RELLENO DE NUBES - PRO")
print("Landsat 7 EXCLUIDO (SLC-off: franjas sin datos)")
print("=" * 70)
print(f"Cobertura: Landsat 1-6, 8-9 + Sentinel-2 (1972 - presente)")
print(f"Pre-filtro escena: {umbral_nubes_escena}% | Umbral AOI: {umbral_nubes_aoi}% | Sin relleno si AOI <= {umbral_sin_relleno}%")

# Cargar region
ee_shape = geemap.shp_to_ee(direccion_shp)
region = ee_shape.geometry().buffer(buffer_km * 1000).bounds()

# Calcular bounding box una sola vez (grados WGS84) para el tiling dinámico
_bbox_coords = region.bounds().coordinates().get(0).getInfo()
_xs = [c[0] for c in _bbox_coords]
_ys = [c[1] for c in _bbox_coords]
BBOX = (min(_xs), min(_ys), max(_xs), max(_ys))   # (minx, miny, maxx, maxy)
print(f"\n  Bounding Box: [{BBOX[0]:.5f}, {BBOX[1]:.5f}, {BBOX[2]:.5f}, {BBOX[3]:.5f}]")
print(f"  Límite GEE: {LIMITE_DESCARGA_MB} MB/tile | Factor corrección píxeles: ×{FACTOR_CORRECCION_PIX}")

# Carpeta de logs
os.makedirs(os.path.join(directorio_salida, 'LOGS'), exist_ok=True)

# Tabla de misiones disponibles
print("\n  MISIONES DISPONIBLES (Landsat 7 excluido):")
print("  " + "-" * 55)
for key, m in MISIONES.items():
    print(f"  {key:6s} | {m['nombre']:25s} | {m['anio_inicio']}-{m['anio_fin']} | {m['scale']}m")
print("  " + "-" * 55)

# Procesar cada año
for anio, meses in FECHAS_A_PROCESAR.items():
    print(f"\n{'='*70}")
    print(f"AÑO {anio}")
    print(f"{'='*70}")

    misiones_disponibles = obtener_mision_para_anio(anio)

    if not misiones_disponibles:
        print(f"  [X] No hay misiones para el año {anio}")
        continue

    print(f"  Misiones disponibles: {' -> '.join(misiones_disponibles)}")
    for mk in misiones_disponibles:
        m = MISIONES[mk]
        print(f"    {mk}: {m['nombre']} ({m['anio_inicio']}-{m['anio_fin']}, {m['scale']}m)")

    log_buffer = []
    log_buffer.append("=" * 70)
    log_buffer.append(f"REPORTE DE MOSAICO ANUAL - AÑO {anio}")
    log_buffer.append(f"Landsat 7 EXCLUIDO (SLC-off)")
    log_buffer.append("=" * 70)
    log_buffer.append(f"\nMisiones disponibles: {' -> '.join(misiones_disponibles)}")
    log_buffer.append(f"Pre-filtro escena: {umbral_nubes_escena}% | Umbral AOI: {umbral_nubes_aoi}%")
    log_buffer.append(f"Sin relleno si AOI <= {umbral_sin_relleno}% | Relleno AOI: {umbral_nubes_aoi_relleno}%")

    for mes_nom in meses:
        mes_num = MESES_MAP.get(mes_nom)
        if not mes_num:
            continue

        print(f"\n  MES OBJETIVO: {mes_nom} ({anio}-{mes_num:02d})")
        print(f"  {'-'*50}")

        log_buffer.append(f"\n{'#'*60}")
        log_buffer.append(f"MES OBJETIVO: {mes_nom} ({anio}-{mes_num:02d})")
        log_buffer.append(f"{'#'*60}")

        misiones_exportadas = []

        for mision_key in misiones_disponibles:
            datos = MISIONES[mision_key]
            es_fallback = datos.get('fallback_only', False)

            # Landsat 7 (fallback_only): solo intentar si ninguna otra mision exporto
            if es_fallback and misiones_exportadas:
                print(f"    [SKIP] {datos['nombre']}: no necesario, ya hay datos de {', '.join(misiones_exportadas)}")
                log_buffer.append(f"\n{datos['nombre']}: omitido (datos disponibles en {', '.join(misiones_exportadas)})")
                continue

            es_mss = datos.get('es_mss', False)
            tipo_str = "MSS (4 bandas, 60m)" if es_mss else f"TM/OLI (6 bandas, {datos['scale']}m)"
            fallback_str = " [FALLBACK SLC-off]" if es_fallback else ""
            print(f"    Probando {datos['nombre']} [{tipo_str}]{fallback_str}...")

            try:
                img_final, log_relleno, info_base = crear_mosaico_con_relleno(
                    anio, mes_num, region, mision_key
                )

                if img_final is not None and info_base is not None:
                    print(f"      EXITO con {datos['nombre']}")

                    nubes_str = f"{info_base['nubes']:.1f}%" if info_base['nubes'] >= 0 else "N/D"
                    print(f"      IMAGEN BASE: {info_base['id']}")
                    print(f"      Fecha: {info_base['fecha']} | Nubes: {nubes_str}")

                    if es_mss:
                        print(f"      [MSS] Productos: NDWI, RGB (falso color), IR")
                    else:
                        print(f"      Productos: MNDWI, RGB, IR")

                    for linea in log_relleno:
                        log_buffer.append(linea)

                    fecha_base_str = info_base['fecha'].replace('-', '')
                    nombre_archivo = f"{anio}_{mes_num:02d}_{mes_nom}_{mision_key}_{fecha_base_str}"

                    print(f"      Exportando: {nombre_archivo}_*.tif")

                    img_clipped = img_final.clip(region)
                    exportar_productos(img_clipped, nombre_archivo, datos, BBOX)

                    log_buffer.append("")
                    log_buffer.append(f"ARCHIVO EXPORTADO: {nombre_archivo}")
                    log_buffer.append(f"IMAGEN BASE: {info_base['id']} (nubes: {nubes_str})")
                    log_buffer.append(f"TIPO: {'MSS' if es_mss else 'TM/OLI'}")
                    misiones_exportadas.append(mision_key)

                else:
                    print(f"      Sin datos")
                    log_buffer.append(f"\n{datos['nombre']}: Sin datos disponibles")

            except Exception as e:
                print(f"      ERROR: {e}")
                log_buffer.append(f"\n{datos['nombre']}: ERROR - {e}")

        if misiones_exportadas:
            uso_l7 = 'LE07' in misiones_exportadas
            aviso_l7 = " (Landsat 7 SLC-off usado como fallback)" if uso_l7 else ""
            print(f"    [OK] {len(misiones_exportadas)} mision(es) exportadas: {', '.join(misiones_exportadas)}{aviso_l7}")
            log_buffer.append(f"\nMISIONES EXPORTADAS: {', '.join(misiones_exportadas)}{aviso_l7}")
        else:
            print(f"    [X] Sin imagenes disponibles en ninguna mision (incluido L7 fallback)")
            log_buffer.append(f"\n[SIN DATOS] No hay imagenes disponibles para este mes")

    # Guardar log
    ruta_log = os.path.join(directorio_salida, 'LOGS', f"REPORTE_{anio}_MOSAICO.txt")
    with open(ruta_log, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_buffer))
    print(f"\n  Log guardado: REPORTE_{anio}_MOSAICO.txt")

print("\n" + "=" * 70)
print("PROCESO FINALIZADO")
print("=" * 70)
