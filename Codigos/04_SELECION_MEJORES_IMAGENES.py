# -*- coding: utf-8 -*-
"""
SCRIPT V6.0: SELECCIONADOR MEJOR IMAGEN + REPORTE + TABLA PNG
Compatible con logs PRO (multimision por mes: S2 + LC08 + LC09, L7 fallback)
"""

import os
import shutil
import re
import csv
from datetime import datetime
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject
from scipy.ndimage import uniform_filter

# ==============================================================================
# 1. CONFIGURACION
# ==============================================================================
DIR_RAIZ         = r"E:\Documentos_compartidos\ANT\2026-01\20260413\IMAGENES_MOSAICO"
DIR_LOGS         = os.path.join(DIR_RAIZ, 'LOGS')
DIR_SALIDA_FINAL = os.path.join(DIR_RAIZ, 'MEJORES_POR_AÑOOO')
RUTA_MEJORES_TXT = os.path.join(DIR_RAIZ, 'mejores.txt')
UMBRAL_NUBES     = 25

MESES_MAP = {
    'ENE': '01', 'FEB': '02', 'MAR': '03', 'ABR': '04', 'MAY': '05', 'JUN': '06',
    'JUL': '07', 'AGO': '08', 'SEP': '09', 'OCT': '10', 'NOV': '11', 'DIC': '12'
}
MESES_NOMBRES = {
    '01': 'Enero',   '02': 'Febrero',  '03': 'Marzo',     '04': 'Abril',
    '05': 'Mayo',    '06': 'Junio',    '07': 'Julio',      '08': 'Agosto',
    '09': 'Septiembre', '10': 'Octubre', '11': 'Noviembre', '12': 'Diciembre'
}
MISIONES_NOMBRES = {
    'S2':      'Sentinel-2 L2A',
    'S2_L1C':  'Sentinel-2 L1C (SIN corr. atm.)',
    'LC09':    'Landsat 9 OLI',
    'LC08':    'Landsat 8 OLI',
    'LE07':    'Landsat 7 ETM+ (SLC-off corregido) [FALLBACK]',
    'LT05':    'Landsat 5 TM',
    'LT04':    'Landsat 4 TM',
    'LM04':    'Landsat 4 MSS',
    'LM03':    'Landsat 3 MSS',
    'LM02':    'Landsat 2 MSS',
    'LM01':    'Landsat 1 MSS',
}
# Misiones sin corrección atmosférica (aviso en reportes)
MISIONES_SIN_CORRECCION = {'S2_L1C'}
# Misiones usadas como fallback (aviso especial)
MISIONES_FALLBACK = {'LE07'}

# --- MNDWI: Umbrales de agua por sensor ---
UMBRAL_POR_MISION = {
    # Con correccion atmosferica
    'S2':       -0.15,
    'LC09':     -0.15,
    'LC08':     -0.15,
    'LE07':     -0.15,
    'LT05':     -0.15,
    'LT04':     -0.15,
    # Sin correccion atmosferica (TOA/L1C)
    'S2_L1C':   -0.15,
    'LC09_TOA': -0.15,
    'LC08_TOA': -0.15,
    'LE07_TOA': -0.15,
    'LT05_TOA': -0.15,
}
UMBRAL_FIJO_MNDWI = 0.09    # Umbral usado si el sensor no esta en UMBRAL_POR_MISION
TOLERANCIA_CERO   = 0.001   # Excluir valores entre -0.001 y +0.001 (errores/nubes)

# --- MNDWI: Filtrado y binario final ---
FRECUENCIA_MINIMA = 2    # Solo pixeles con frecuencia >= N (agua persistente)
APLICAR_SUAVIZADO = True
TAMANO_FILTRO     = 2    # Ventana NxN pixeles para el suavizado
UMBRAL_SUAVIZADO  = 0.5  # Umbral despues de suavizar


# ==============================================================================
# 2. PARSER DE LOGS (formato PRO: múltiples misiones por mes)
# ==============================================================================

def _finalizar_mes(mes_nom, misiones_del_mes, meses_data, meses_encontrados):
    """Consolida todas las misiones encontradas en un mes y guarda en meses_data."""
    mes_num = MESES_MAP.get(mes_nom, '00')
    if not misiones_del_mes:
        meses_data[mes_num] = {
            'mes_nom': mes_nom, 'sin_imagenes': True,
            'misiones': [], 'mision': None, 'imagenes': [],
            'imagen_base': None, 'archivo_exportado': None, 'meses_relleno': []
        }
    else:
        # La "mejor" mision del mes es la de menor % de nubes en imagen base
        mejor = min(
            misiones_del_mes,
            key=lambda x: x['imagen_base']['nubes'] if x.get('imagen_base') else 100.0
        )
        meses_data[mes_num] = {
            'mes_nom':          mes_nom,
            'sin_imagenes':     False,
            'misiones':         misiones_del_mes,        # TODAS las misiones del mes
            # Campos de la mejor misión (compatibilidad con reporte/copia)
            'mision':           mejor['mision'],
            'imagenes':         mejor['imagenes'],
            'imagen_base':      mejor['imagen_base'],
            'archivo_exportado': mejor['archivo_exportado'],
            'meses_relleno':    mejor['meses_relleno'],
        }
    if mes_nom not in meses_encontrados:
        meses_encontrados.append(mes_nom)


def analizar_log_v7(lineas):
    """
    Parsea logs del script PRO.
    Soporta múltiples misiones por mes (S2 + LC08 + LC09, L7 fallback).
    Retorna (mejor_global, meses_data, meses_encontrados).
    """
    mejor_global      = None
    min_nubes_global  = 100.0
    meses_data        = {}
    meses_encontrados = []

    mes_nom_actual   = None
    misiones_del_mes = []   # acumulador de misiones del mes en curso

    # Acumuladores de la misión en curso (dentro de un mes)
    cur_imgs          = []
    cur_archivo       = None
    cur_mision        = None
    cur_meses_relleno = []

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        # ── Nuevo mes objetivo ──────────────────────────────────────────────
        match_mes = re.search(r'MES OBJETIVO:\s+(\w+)\s+\((\d{4})-(\d{2})\)', linea)
        if match_mes:
            if mes_nom_actual is not None:
                _finalizar_mes(mes_nom_actual, misiones_del_mes, meses_data, meses_encontrados)
            mes_nom_actual   = match_mes.group(1)
            misiones_del_mes = []
            cur_imgs          = []
            cur_archivo       = None
            cur_mision        = None
            cur_meses_relleno = []
            if mes_nom_actual not in meses_encontrados:
                meses_encontrados.append(mes_nom_actual)
            i += 1
            continue

        # ── Inicio de bloque de imágenes base (nueva misión en el mes) ─────
        if 'IMAGENES BASE -' in linea:
            cur_imgs          = []
            cur_archivo       = None
            cur_mision        = None
            cur_meses_relleno = []
            i += 1
            continue

        # ── Entradas de imagen base: "  1. ID" + siguiente línea con nubes ─
        match_img_num = re.search(r'^\s*(\d+)\.\s+(\S+)\s*$', linea)
        if match_img_num and mes_nom_actual:
            img_id = match_img_num.group(2)
            if i + 1 < len(lineas):
                next_line = lineas[i + 1].strip()
                match_nubes = re.search(r'Fecha:\s+([^\|]+)\|\s*Nubes:\s*([\d.]+)%', next_line)
                if match_nubes:
                    cur_imgs.append({
                        'id':    img_id,
                        'nubes': float(match_nubes.group(2)),
                        'fecha': match_nubes.group(1).strip()
                    })
                    i += 2
                    continue
            i += 1
            continue

        # ── Meses de relleno dentro de un bloque ────────────────────────────
        match_mes_rel = re.search(r'^\s+(\w{3}):\s+(\d+)\s+imgs?', linea)
        if match_mes_rel:
            cur_meses_relleno.append({
                'mes':      match_mes_rel.group(1),
                'num_imgs': int(match_mes_rel.group(2))
            })
            i += 1
            continue

        # ── ARCHIVO EXPORTADO ────────────────────────────────────────────────
        match_arch = re.search(r'ARCHIVO EXPORTADO:\s+(.+)', linea)
        if match_arch:
            cur_archivo = match_arch.group(1).strip()
            match_mis   = re.search(r'_(\w+)_\d{8}$', cur_archivo)
            if match_mis:
                cur_mision = match_mis.group(1)
            i += 1
            continue

        # ── IMAGEN BASE → finaliza la misión en curso ────────────────────────
        match_img_base = re.search(r'IMAGEN BASE:\s+(\S+)\s+\(nubes:\s*([\d.]+)%\)', linea)
        if match_img_base:
            base_id    = match_img_base.group(1)
            base_nubes = float(match_img_base.group(2))

            entrada = {
                'mision':           cur_mision,
                'imagenes':         cur_imgs.copy(),
                'archivo_exportado': cur_archivo,
                'imagen_base':      {'id': base_id, 'nubes': base_nubes},
                'meses_relleno':    cur_meses_relleno.copy(),
                'es_fallback':      cur_mision in MISIONES_FALLBACK,
            }
            misiones_del_mes.append(entrada)

            # Actualizar mejor global
            if base_nubes < min_nubes_global:
                min_nubes_global = base_nubes
                mejor_global = {
                    'mes':      mes_nom_actual,
                    'mision':   cur_mision,
                    'score':    base_nubes,
                    'id_crudo': base_id,
                    'archivo':  cur_archivo,
                }

            # Resetear acumuladores de misión
            cur_imgs          = []
            cur_archivo       = None
            cur_mision        = None
            cur_meses_relleno = []
            i += 1
            continue

        i += 1

    # Finalizar el último mes
    if mes_nom_actual is not None:
        _finalizar_mes(mes_nom_actual, misiones_del_mes, meses_data, meses_encontrados)

    return mejor_global, meses_data, meses_encontrados


def analizar_log_v6(lineas):
    """Parser de logs formato antiguo V6/V6.5 (una misión por mes)."""
    mejor_mes_info   = None
    min_nubes_global = 100.0
    meses_data       = {}
    meses_encontrados = []
    mes_actual       = None
    mes_nom_actual   = None
    mision_actual    = None
    mision_temp      = None
    imgs_del_mes     = []

    for linea in lineas:
        ls = linea.strip()

        match_mes = re.search(r'MES:\s+(\w+)\s+\((\d{4}-\d{2}-\d{2})\s+a\s+(\d{4}-\d{2}-\d{2})\)', ls)
        if match_mes:
            if mes_actual and imgs_del_mes and mision_actual:
                mes_num = MESES_MAP.get(mes_nom_actual, '00')
                meses_data[mes_num] = {
                    'mes_nom': mes_nom_actual, 'mision': mision_actual,
                    'imagenes': imgs_del_mes.copy(), 'sin_imagenes': False,
                    'misiones': [{'mision': mision_actual, 'imagenes': imgs_del_mes.copy(),
                                  'imagen_base': None, 'archivo_exportado': None,
                                  'meses_relleno': [], 'es_fallback': False}]
                }
                if mes_nom_actual not in meses_encontrados:
                    meses_encontrados.append(mes_nom_actual)
                mejor_img = min(imgs_del_mes, key=lambda x: x['nubes'])
                if mejor_img['nubes'] < min_nubes_global:
                    min_nubes_global = mejor_img['nubes']
                    mejor_mes_info = {'mes': mes_nom_actual, 'mision': mision_actual,
                                      'score': min_nubes_global, 'id_crudo': mejor_img['id']}
            mes_nom_actual = match_mes.group(1)
            mes_actual     = mes_nom_actual
            mision_actual  = None
            mision_temp    = None
            imgs_del_mes   = []
            if mes_nom_actual not in meses_encontrados:
                meses_encontrados.append(mes_nom_actual)
            continue

        match_mision = re.search(r'\[\d+/\d+\]\s+([^:]+):', ls)
        if match_mision:
            nombre = match_mision.group(1).strip()
            if 'Sentinel-2 L1C' in nombre:   mision_temp = 'S2_L1C'
            elif 'Sentinel-2' in nombre:      mision_temp = 'S2'
            elif 'Landsat 9' in nombre:       mision_temp = 'LC09'
            elif 'Landsat 8' in nombre:       mision_temp = 'LC08'
            elif 'Landsat 7' in nombre:       mision_temp = 'LE07'
            elif 'Landsat 5' in nombre:       mision_temp = 'LT05'

        if '-> SELECCIONADA' in ls and mision_temp:
            mision_actual = mision_temp

        match_img = re.search(r'^\s*\d+\.\s+(\S+)\s+\(([\d.]+)%\)', ls)
        if match_img and mes_actual:
            imgs_del_mes.append({'id': match_img.group(1), 'nubes': float(match_img.group(2))})

    if mes_actual and imgs_del_mes and mision_actual:
        mes_num = MESES_MAP.get(mes_nom_actual, '00')
        meses_data[mes_num] = {
            'mes_nom': mes_nom_actual, 'mision': mision_actual,
            'imagenes': imgs_del_mes.copy(), 'sin_imagenes': False,
            'misiones': [{'mision': mision_actual, 'imagenes': imgs_del_mes.copy(),
                          'imagen_base': None, 'archivo_exportado': None,
                          'meses_relleno': [], 'es_fallback': False}]
        }
        if mes_nom_actual not in meses_encontrados:
            meses_encontrados.append(mes_nom_actual)
        mejor_img = min(imgs_del_mes, key=lambda x: x['nubes'])
        if mejor_img['nubes'] < min_nubes_global:
            mejor_mes_info = {'mes': mes_nom_actual, 'mision': mision_actual,
                              'score': mejor_img['nubes'], 'id_crudo': mejor_img['id']}

    return mejor_mes_info, meses_data, meses_encontrados


def detectar_version_log(lineas):
    for linea in lineas:
        if 'MOSAICO ANUAL' in linea or 'IMAGENES BASE -' in linea:
            return 'V7'
    return 'V6'


def analizar_log_completo(ruta_log):
    with open(ruta_log, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
    version = detectar_version_log(lineas)
    if version == 'V7':
        return analizar_log_v7(lineas)
    else:
        return analizar_log_v6(lineas)


# ==============================================================================
# 3. COPIA DE ARCHIVOS
# ==============================================================================

def copiar_archivos(anio, info_ganador):
    mes_nom  = info_ganador['mes']
    mes_num  = MESES_MAP.get(mes_nom, '00')
    mision   = info_ganador.get('mision', '')
    base_name = info_ganador.get('archivo') or f"{anio}_{mes_num}_{mes_nom}_{mision}"

    # Productos posibles (TM/OLI y MSS)
    productos_buscar = ['RGB', 'MNDWI', 'IR', 'NDWI']
    archivos_copiados = []

    for prod in productos_buscar:
        carpeta_origen  = os.path.join(DIR_RAIZ, prod)
        carpeta_destino = os.path.join(DIR_SALIDA_FINAL, prod)
        if not os.path.exists(carpeta_origen):
            continue
        os.makedirs(carpeta_destino, exist_ok=True)
        nombre_archivo = f"{base_name}_{prod}.tif"
        ruta_origen    = os.path.join(carpeta_origen, nombre_archivo)
        if os.path.exists(ruta_origen):
            ruta_destino = os.path.join(carpeta_destino, nombre_archivo)
            shutil.copy2(ruta_origen, ruta_destino)
            archivos_copiados.append(nombre_archivo)

    return archivos_copiados, base_name


# ==============================================================================
# 3.5. SELECCION POR ANALISIS DE PIXELES (baja resolucion)
# ==============================================================================

def analizar_pixeles_reducido(ruta_tif, factor=20):
    """
    Lee el TIF al 1/factor de resolucion y calcula % de pixeles validos.
    Retorna float (0-100) o None si no se puede leer.
    """
    if not os.path.exists(ruta_tif):
        return None
    try:
        with rasterio.open(ruta_tif) as src:
            h = max(1, src.height // factor)
            w = max(1, src.width // factor)
            data = src.read(1, out_shape=(h, w), resampling=Resampling.nearest)
            nodata = src.nodata
            if nodata is not None:
                mascara_valida = data != nodata
            else:
                mascara_valida = data > 0
            return round(float(np.sum(mascara_valida)) / data.size * 100.0, 2)
    except Exception as e:
        print(f"    [PIXEL] Error en {os.path.basename(ruta_tif)}: {e}")
        return None


def seleccionar_mejor_por_pixeles(anio, meses_data, dir_raiz, umbral_nubes=UMBRAL_NUBES):
    """
    Selecciona la mejor imagen del año combinando metadata y analisis de pixeles.
    1. Recopila todos los candidatos con su archivo exportado.
    2. Filtra los que tienen metadata < umbral_nubes.
       Si ninguno pasa el umbral -> usa todos (fallback).
    3. Analiza pixeles a baja resolucion (RGB) para cada candidato.
    4. Retorna el candidato con mayor % de pixeles validos.
    """
    candidatos = []
    for _, info_mes in meses_data.items():
        if info_mes.get('sin_imagenes'):
            continue
        mes_nom = info_mes['mes_nom']
        for entrada in info_mes.get('misiones', []):
            img_base = entrada.get('imagen_base')
            archivo  = entrada.get('archivo_exportado')
            if not img_base or not archivo:
                continue
            candidatos.append({
                'mes':         mes_nom,
                'mision':      entrada.get('mision'),
                'score':       img_base['nubes'],
                'id_crudo':    img_base['id'],
                'archivo':     archivo,
                'es_fallback': entrada.get('es_fallback', False),
            })

    if not candidatos:
        return None

    # Filtrar por umbral metadata
    bajo_umbral = [c for c in candidatos if c['score'] < umbral_nubes]
    if bajo_umbral:
        pool = bajo_umbral
        fallback_umbral = False
    else:
        pool = candidatos
        fallback_umbral = True
        print(f"    [AÑO {anio}] Sin imagenes < {umbral_nubes}% nubes → evaluando todas ({len(pool)})")

    # Analisis de pixeles sobre RGB de origen
    print(f"    Analizando {len(pool)} candidato(s) por pixeles...")
    for c in pool:
        ruta_rgb = os.path.join(dir_raiz, 'RGB', f"{c['archivo']}_RGB.tif")
        c['pct_valido'] = analizar_pixeles_reducido(ruta_rgb)
        if c['pct_valido'] is not None:
            print(f"      {c['mes']}/{c['mision']}  meta:{c['score']:.1f}%  validos:{c['pct_valido']:.1f}%")
        else:
            print(f"      {c['mes']}/{c['mision']}  meta:{c['score']:.1f}%  [TIF no encontrado]")

    # Seleccionar por menor % nubes metadata (pixeles solo informativo)
    ganador = min(pool, key=lambda x: x['score'])

    ganador['fallback_umbral'] = fallback_umbral
    return ganador


# ==============================================================================
# 3.6  DETECCION DE NUBES / NODATA Y RELLENO DE IMAGEN SELECCIONADA
# ==============================================================================

# -- Configuracion relleno --
UMBRAL_BRILLO_NUBE  = 0.70    # Reflectancia media normalizada > umbral → posible nube/nieve
UMBRAL_STD_NUBE     = 0.12    # Desv. est. inter-banda < umbral → pixel uniforme (nube)
UMBRAL_PCT_RELLENO  = 0.50    # % minimo de pixeles invalidos para activar relleno
FACTOR_ESCALA_REFL  = 10000.0 # Factor de escala reflectancia GEE (reflectancia x 10000)
PRODUCTOS_RELLENAR  = ['RGB', 'MNDWI', 'IR', 'NDWI']
GEE_PROYECTO        = 'precipitaciones-459216'

# Bandas GEE por sensor y producto: (lista_bandas, tipo_indice, factor_escala_fisico)
_GEE_BANDAS = {
    'S2':   {'RGB':   (['B4', 'B3', 'B2'],         None,    1e-4),
             'MNDWI': (['B3', 'B11'],               'MNDWI', 1e-4),
             'IR':    (['B8'],                       None,    1e-4),
             'NDWI':  (['B3', 'B8'],                'NDWI',  1e-4)},
    'LC09': {'RGB':   (['SR_B4', 'SR_B3', 'SR_B2'], None,    2.75e-5),
             'MNDWI': (['SR_B3', 'SR_B6'],          'MNDWI', 2.75e-5),
             'IR':    (['SR_B5'],                    None,    2.75e-5),
             'NDWI':  (['SR_B3', 'SR_B5'],          'NDWI',  2.75e-5)},
    'LE07': {'RGB':   (['SR_B3', 'SR_B2', 'SR_B1'], None,    2.75e-5),
             'MNDWI': (['SR_B2', 'SR_B5'],          'MNDWI', 2.75e-5),
             'IR':    (['SR_B4'],                    None,    2.75e-5),
             'NDWI':  (['SR_B2', 'SR_B4'],          'NDWI',  2.75e-5)},
    'LT05': {'RGB':   (['SR_B3', 'SR_B2', 'SR_B1'], None,    2.75e-5),
             'MNDWI': (['SR_B2', 'SR_B5'],          'MNDWI', 2.75e-5),
             'IR':    (['SR_B4'],                    None,    2.75e-5),
             'NDWI':  (['SR_B2', 'SR_B4'],          'NDWI',  2.75e-5)},
    'LT04': {'RGB':   (['SR_B3', 'SR_B2', 'SR_B1'], None,    2.75e-5),
             'MNDWI': (['SR_B2', 'SR_B5'],          'MNDWI', 2.75e-5),
             'IR':    (['SR_B4'],                    None,    2.75e-5),
             'NDWI':  (['SR_B2', 'SR_B4'],          'NDWI',  2.75e-5)},
}
_GEE_BANDAS['LC08']   = _GEE_BANDAS['LC09']
_GEE_BANDAS['S2_L1C'] = _GEE_BANDAS['S2']

_GEE_COLECCIONES = {
    'S2':     'COPERNICUS/S2_SR_HARMONIZED',
    'S2_L1C': 'COPERNICUS/S2_HARMONIZED',
    'LC09':   'LANDSAT/LC09/C02/T1_L2',
    'LC08':   'LANDSAT/LC08/C02/T1_L2',
    'LE07':   'LANDSAT/LE07/C02/T1_L2',
    'LT05':   'LANDSAT/LT05/C02/T1_L2',
    'LT04':   'LANDSAT/LT04/C02/T1_L2',
}


def detectar_mascara_invalida(ruta_rgb):
    """
    Analiza la imagen RGB seleccionada y detecta pixeles invalidos por inspeccion espectral:
      - NoData : todos los canales == 0 (o == nodata del TIF)
      - Nubes  : reflectancia media > UMBRAL_BRILLO_NUBE  Y  desv. inter-banda < UMBRAL_STD_NUBE
    Nota: superficies muy brillantes (arena blanca, nieve) tambien pueden ser detectadas.
          Ajustar UMBRAL_BRILLO_NUBE si el area de estudio lo requiere.
    Retorna (mascara_2d bool, profile dict, pct_invalido float) o (None, None, 0) si falla.
    """
    if not os.path.exists(ruta_rgb):
        print(f"    [RELLENO] RGB no encontrado: {ruta_rgb}")
        return None, None, 0.0
    try:
        with rasterio.open(ruta_rgb) as src:
            data    = src.read().astype(np.float32)   # (bandas, H, W)
            nodata  = src.nodata
            profile = src.profile.copy()

        # Mascara NoData
        mask_nd = np.all(data == 0, axis=0)
        if nodata is not None and nodata != 0:
            mask_nd |= np.all(data == float(nodata), axis=0)

        # Normalizar reflectancia a 0-1 para analisis espectral
        validos = data[~np.isnan(data)]
        max_val = float(validos.max()) if validos.size > 0 else 0.0
        d_norm  = np.clip(data / FACTOR_ESCALA_REFL if max_val > 2.0 else data.copy(), 0.0, 1.0)

        # Mascara Nubes: alto brillo + baja varianza inter-banda
        brillo    = np.mean(d_norm, axis=0)
        std_ib    = np.std(d_norm, axis=0)
        mask_nube = (~mask_nd) & (brillo > UMBRAL_BRILLO_NUBE) & (std_ib < UMBRAL_STD_NUBE)

        mascara = mask_nd | mask_nube
        pct     = float(np.sum(mascara)) / mascara.size * 100.0

        print(f"    NoData  : {int(np.sum(mask_nd)):>10,} px")
        print(f"    Nubes   : {int(np.sum(mask_nube)):>10,} px  (brillo>{UMBRAL_BRILLO_NUBE}, std<{UMBRAL_STD_NUBE})")
        print(f"    Total   : {int(np.sum(mascara)):>10,} px  ({pct:.2f}%)")
        return mascara, profile, pct

    except Exception as e:
        print(f"    [RELLENO] Error en deteccion: {e}")
        return None, None, 0.0


def _leer_reproyectar(ruta, profile_ref):
    """
    Lee ruta y, si es necesario, reproyecta al grid de profile_ref.
    Retorna array float32 (nbands, H, W) o None si falla.
    """
    try:
        with rasterio.open(ruta) as src:
            mismo_grid = (
                src.crs == profile_ref['crs'] and
                abs(src.transform.a - profile_ref['transform'].a) < 1e-6 and
                src.height == profile_ref['height'] and
                src.width  == profile_ref['width']
            )
            if mismo_grid:
                return src.read().astype(np.float32)
            nbands = src.count
        H, W = profile_ref['height'], profile_ref['width']
        out  = np.zeros((nbands, H, W), dtype=np.float32)
        with rasterio.open(ruta) as src:
            for b in range(1, nbands + 1):
                reproject(
                    source=rasterio.band(src, b), destination=out[b - 1],
                    src_transform=src.transform,  src_crs=src.crs,
                    dst_transform=profile_ref['transform'], dst_crs=profile_ref['crs'],
                    resampling=Resampling.bilinear
                )
        return out
    except Exception as e:
        print(f"      [LEER] {os.path.basename(ruta)}: {e}")
        return None


def _mascara_invalida_data(data, producto):
    """
    Mascara bool 2D de pixeles invalidos para array float32 (nbands, H, W).
    RGB: nodata + nubes por analisis espectral.
    Otros productos: NaN y ceros (nodata) unicamente.
    """
    mask = np.any(np.isnan(data), axis=0) | np.all(data == 0, axis=0)
    if producto == 'RGB':
        validos = data[~np.isnan(data)]
        max_val = float(validos.max()) if validos.size > 0 else 0.0
        d_n = np.clip(data / FACTOR_ESCALA_REFL if max_val > 2.0 else data.copy(), 0, 1)
        brillo = np.mean(d_n, axis=0)
        std_ib = np.std(d_n, axis=0)
        mask |= (~mask) & (brillo > UMBRAL_BRILLO_NUBE) & (std_ib < UMBRAL_STD_NUBE)
    return mask


def _candidatos_año(meses_data, archivo_ganador):
    """Lista de candidatos del año (excluye el ganador), ordenados por % nubes asc."""
    cands = []
    for info in meses_data.values():
        if info.get('sin_imagenes'):
            continue
        for entrada in info.get('misiones', []):
            arch = entrada.get('archivo_exportado')
            ib   = entrada.get('imagen_base')
            if not arch or not ib or arch == archivo_ganador:
                continue
            cands.append({'archivo': arch, 'nubes': ib['nubes'],
                          'mision': entrada.get('mision', '')})
    return sorted(cands, key=lambda x: x['nubes'])


def rellenar_desde_local(ruta_dest, mascara, candidatos, dir_raiz, producto):
    """
    Rellena pixeles invalidos usando candidatos locales del mismo año.
    Lee el destino una vez, itera candidatos en memoria, escribe una sola vez al final.
    Retorna (mascara_residual, n_px_rellenados).
    """
    with rasterio.open(ruta_dest) as src:
        data    = src.read().astype(np.float32)
        profile = src.profile.copy()
        dtype0  = src.dtypes[0]

    pendiente = mascara.copy()
    n_total   = 0

    for cand in candidatos:
        if not np.any(pendiente):
            break
        ruta_c = os.path.join(dir_raiz, producto, f"{cand['archivo']}_{producto}.tif")
        if not os.path.exists(ruta_c):
            continue
        arr_c = _leer_reproyectar(ruta_c, profile)
        if arr_c is None:
            continue

        mask_inv_c = _mascara_invalida_data(arr_c, producto)
        mask_fill  = pendiente & ~mask_inv_c
        n = int(np.sum(mask_fill))
        if n > 0:
            data[:, mask_fill] = arr_c[:, mask_fill]
            pendiente[mask_fill] = False
            n_total += n
            print(f"      [{producto}] <- {cand['archivo']} [{cand['mision']}]  "
                  f"{n:,} px  nubes:{cand['nubes']:.1f}%")

    if n_total > 0:
        if np.issubdtype(np.dtype(dtype0), np.integer):
            out = np.clip(data, 0, np.iinfo(np.dtype(dtype0)).max).astype(dtype0)
        else:
            out = data.astype(dtype0)
        with rasterio.open(ruta_dest, 'w', **profile) as dst:
            dst.write(out)

    return pendiente, n_total


def rellenar_con_gee(ruta_dest, mascara, anio, mision, producto):
    """
    Fallback GEE: descarga composite mediana cloud-free del mismo año y rellena
    los pixeles residuales. Requiere earthengine-api instalado y autenticado.
      - Instalacion : pip install earthengine-api
      - Autenticacion: earthengine authenticate
    """
    try:
        import ee
    except ImportError:
        print("      [GEE] earthengine-api no instalado -> pip install earthengine-api")
        return 0

    try:
        ee.Initialize(project=GEE_PROYECTO)
    except Exception:
        try:
            ee.Authenticate()
            ee.Initialize(project=GEE_PROYECTO)
        except Exception as exc:
            print(f"      [GEE] No se pudo inicializar Earth Engine: {exc}")
            return 0

    # Configuracion de bandas para este sensor/producto
    key_sensor = mision if mision in _GEE_BANDAS else 'S2'
    cfg = _GEE_BANDAS.get(key_sensor, {}).get(producto)
    if not cfg:
        print(f"      [GEE] Sin configuracion para sensor={key_sensor}, producto={producto}")
        return 0
    bandas_gee, tipo_indice, sf_gee = cfg
    col_id = _GEE_COLECCIONES.get(key_sensor, _GEE_COLECCIONES['S2'])

    try:
        from rasterio.warp import transform_bounds
        import urllib.request

        with rasterio.open(ruta_dest) as src_ref:
            profile_ref = src_ref.profile.copy()
            crs_src     = src_ref.crs
            bounds_src  = src_ref.bounds
            res_m       = abs(src_ref.transform.a)
            orig_dtype  = src_ref.dtypes[0]
            data_dest   = src_ref.read().astype(np.float32)

        w, s, e, n_b = transform_bounds(crs_src, 'EPSG:4326', *bounds_src)
        region = ee.Geometry.Rectangle([w, s, e, n_b])
        d_ini, d_fin = f"{anio}-01-01", f"{anio}-12-31"

        print(f"      [GEE] Construyendo composite {anio} | {key_sensor}/{producto}...")

        # Enmascaramiento de nubes segun plataforma
        if key_sensor.startswith('S2'):
            def mask_fn(img):
                scl = img.select('SCL')
                return img.updateMask(
                    scl.neq(3).And(scl.neq(8)).And(scl.neq(9)).And(scl.neq(10)))
            f_cloud = ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 70)
        else:
            def mask_fn(img):
                qa = img.select('QA_PIXEL')
                return img.updateMask(
                    qa.bitwiseAnd(1 << 3).eq(0).And(qa.bitwiseAnd(1 << 4).eq(0)))
            f_cloud = ee.Filter.lt('CLOUD_COVER', 70)

        col = (ee.ImageCollection(col_id)
               .filterBounds(region).filterDate(d_ini, d_fin)
               .filter(f_cloud).map(mask_fn))

        n_gee = col.size().getInfo()
        if n_gee == 0:
            print(f"      [GEE] Sin imagenes en {col_id} para {anio}")
            return 0
        print(f"      [GEE] {n_gee} imagenes disponibles -> mediana...")

        comp = col.median().select(bandas_gee).multiply(sf_gee)
        if tipo_indice in ('MNDWI', 'NDWI'):
            b1_ee = comp.select(bandas_gee[0])
            b2_ee = comp.select(bandas_gee[1])
            comp  = b1_ee.subtract(b2_ee).divide(b1_ee.add(b2_ee)).rename(tipo_indice)

        epsg  = crs_src.to_epsg()
        crs_p = f'EPSG:{epsg}' if epsg else 'EPSG:4326'
        url   = comp.getDownloadURL({
            'scale': res_m, 'crs': crs_p, 'region': region,
            'format': 'GEO_TIFF', 'maxPixels': 1e9,
        })

        print("      [GEE] Descargando...")
        tmp = ruta_dest.replace('.tif', '_gee_tmp.tif')
        urllib.request.urlretrieve(url, tmp)

        data_gee = _leer_reproyectar(tmp, profile_ref)
        try:
            os.remove(tmp)
        except Exception:
            pass
        if data_gee is None:
            return 0

        # Escalar GEE (reflectancia fisica 0-1 o indice -1..1) al rango del destino
        if np.issubdtype(np.dtype(orig_dtype), np.integer):
            data_gee = data_gee * FACTOR_ESCALA_REFL

        mask_gee_val = np.all(data_gee != 0, axis=0) & ~np.any(np.isnan(data_gee), axis=0)
        mask_fill    = mascara & mask_gee_val
        n = int(np.sum(mask_fill))

        if n > 0:
            data_dest[:, mask_fill] = data_gee[:, mask_fill]
            if np.issubdtype(np.dtype(orig_dtype), np.integer):
                out = np.clip(data_dest, 0, np.iinfo(np.dtype(orig_dtype)).max).astype(orig_dtype)
            else:
                out = data_dest.astype(orig_dtype)
            with rasterio.open(ruta_dest, 'w', **profile_ref) as dst:
                dst.write(out)
            print(f"      [GEE] {n:,} px rellenados con composite mediana {anio}")
        else:
            print("      [GEE] Sin pixeles GEE validos para el relleno")

        return n

    except Exception as exc:
        print(f"      [GEE] Error: {exc}")
        return 0


def aplicar_relleno_imagen_seleccionada(anio, ganador, meses_data):
    """
    Detecta nubes/nodata en la imagen seleccionada analizando directamente los pixeles
    (no usa metadata) y los rellena en dos pasos:
      1. Con otras imagenes locales del mismo año (ordenadas por menor % nubes).
      2. Fallback: composite mediana GEE del mismo año para pixeles residuales.
    Opera sobre todos los productos disponibles (RGB, MNDWI, IR, NDWI).
    La mascara de nubes se genera desde el RGB y se adapta al grid de cada producto.
    """
    if not ganador or not ganador.get('archivo'):
        return

    archivo = ganador['archivo']
    mision  = ganador.get('mision', '')

    print(f"\n  [{anio}] Deteccion y relleno de nubes/nodata (analisis de pixeles)...")

    # -- 1. Detectar mascara en RGB --
    ruta_rgb = os.path.join(DIR_SALIDA_FINAL, 'RGB', f"{archivo}_RGB.tif")
    mascara_rgb, profile_rgb, pct = detectar_mascara_invalida(ruta_rgb)

    if mascara_rgb is None:
        print(f"    [{anio}] No se pudo leer RGB en destino — omitiendo relleno")
        return

    if pct < UMBRAL_PCT_RELLENO:
        print(f"    [{anio}] Imagen aceptable ({pct:.2f}% invalidos < umbral {UMBRAL_PCT_RELLENO}%)")
        return

    candidatos = _candidatos_año(meses_data, archivo)
    print(f"    Candidatos locales disponibles: {len(candidatos)}")

    # -- 2 & 3. Por cada producto --
    for producto in PRODUCTOS_RELLENAR:
        ruta_prod = os.path.join(DIR_SALIDA_FINAL, producto, f"{archivo}_{producto}.tif")
        if not os.path.exists(ruta_prod):
            continue

        # Adaptar mascara RGB al grid del producto (pueden diferir en resolucion)
        with rasterio.open(ruta_prod) as sp:
            H_p, W_p  = sp.height, sp.width
            prof_prod = sp.profile.copy()

        if H_p == mascara_rgb.shape[0] and W_p == mascara_rgb.shape[1]:
            mascara_prod = mascara_rgb.copy()
        else:
            src_m = mascara_rgb.astype(np.uint8)[np.newaxis]
            dst_m = np.zeros((1, H_p, W_p), dtype=np.uint8)
            reproject(
                source=src_m, destination=dst_m,
                src_transform=profile_rgb['transform'], src_crs=profile_rgb['crs'],
                dst_transform=prof_prod['transform'],   dst_crs=prof_prod['crs'],
                resampling=Resampling.nearest
            )
            mascara_prod = dst_m[0].astype(bool)

        n_inv = int(np.sum(mascara_prod))
        if n_inv == 0:
            continue
        print(f"\n    [{producto}] {n_inv:,} px invalidos ({n_inv / mascara_prod.size * 100:.2f}%)")

        # Relleno local
        mascara_res, n_local = rellenar_desde_local(
            ruta_prod, mascara_prod, candidatos, DIR_RAIZ, producto
        )
        n_res = int(np.sum(mascara_res))
        print(f"      Relleno local: {n_local:,} px  |  Residual: {n_res:,} px "
              f"({n_res / mascara_prod.size * 100:.2f}%)")

        # Fallback GEE si quedan pixeles invalidos
        if n_res > 0:
            rellenar_con_gee(ruta_prod, mascara_res, anio, mision, producto)
        else:
            print(f"      [{producto}] Relleno completo con imagenes locales")


# ==============================================================================
# 4. REPORTE TXT
# ==============================================================================

def generar_reporte_completo(todos_los_datos, ruta_salida):
    with open(ruta_salida, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("REPORTE COMPLETO DE IMAGENES SATELITALES - PRO\n")
        f.write("Todas las misiones por mes | L7 solo como fallback\n")
        f.write("=" * 70 + "\n")
        f.write(f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Umbral nubes: <{UMBRAL_NUBES}%\n")
        f.write(f"Directorio: {DIR_RAIZ}\n\n")

        anios_ord = sorted(todos_los_datos.keys())

        # ------------------------------------------------------------------
        f.write("=" * 70 + "\n")
        f.write("SECCION 1: TODAS LAS IMAGENES ENCONTRADAS POR AÑO/MES/MISION\n")
        f.write("=" * 70 + "\n")

        for anio in anios_ord:
            datos_anio    = todos_los_datos[anio]
            meses_data    = datos_anio.get('meses', {})
            meses_buscados = datos_anio.get('meses_buscados', [])
            f.write(f"\n{'#'*60}\nAÑO {anio}\n{'#'*60}\n")
            if meses_buscados:
                f.write(f"Meses buscados: {', '.join(sorted(meses_buscados, key=lambda x: MESES_MAP.get(x,'99')))}\n")

            total_imgs = 0
            for mes_num in sorted(meses_data.keys()):
                info_mes = meses_data[mes_num]
                f.write(f"\n  --- {info_mes['mes_nom']} ---\n")
                misiones = info_mes.get('misiones', [])
                if not misiones or info_mes.get('sin_imagenes', True):
                    f.write("    Sin imagenes disponibles\n")
                    continue

                for entrada in misiones:
                    mis     = entrada.get('mision', '?')
                    nombre  = MISIONES_NOMBRES.get(mis, mis)
                    fb_mark = " [FALLBACK SLC-off]" if entrada.get('es_fallback') else ""
                    toa_mark = " [SIN CORR. ATM.]" if mis in MISIONES_SIN_CORRECCION else ""
                    f.write(f"    Mision: {nombre}{fb_mark}{toa_mark}\n")
                    imgs_ord = sorted(entrada.get('imagenes', []), key=lambda x: x['nubes'])
                    total_imgs += len(imgs_ord)
                    img_base  = entrada.get('imagen_base')
                    for idx, img in enumerate(imgs_ord, 1):
                        marca    = " <-- BASE" if img_base and img['id'] == img_base['id'] else ""
                        fecha_s  = f" | {img.get('fecha','?')}" if img.get('fecha') else ""
                        f.write(f"      {idx}. {img['id']}\n")
                        f.write(f"         Nubes: {img['nubes']:.1f}%{fecha_s}{marca}\n")
                    meses_rel = entrada.get('meses_relleno', [])
                    if meses_rel:
                        f.write(f"      Relleno: {', '.join(mr['mes']+'('+str(mr['num_imgs'])+'img)' for mr in meses_rel)}\n")
                    f.write("\n")

            f.write(f"  TOTAL IMAGENES: {total_imgs}\n")

        # ------------------------------------------------------------------
        f.write("\n" + "=" * 70 + "\n")
        f.write("SECCION 2: MEJOR IMAGEN SELECCIONADA POR AÑO\n")
        f.write("(La de menor % nubes entre todos los meses y misiones del año)\n")
        f.write("=" * 70 + "\n")

        for anio in anios_ord:
            mejor      = todos_los_datos[anio]['mejor']
            nombre_base = todos_los_datos[anio].get('nombre_base', '')
            f.write(f"\nAÑO {anio}\n" + "-" * 40 + "\n")
            if mejor and mejor.get('mision'):
                mis     = mejor['mision']
                fb_mark = " [FALLBACK SLC-off]" if mis in MISIONES_FALLBACK else ""
                toa_mark = " [SIN CORR. ATM.]" if mis in MISIONES_SIN_CORRECCION else ""
                mes_nom  = MESES_NOMBRES.get(MESES_MAP.get(mejor['mes'], '00'), mejor['mes'])
                f.write(f"  Archivo: {nombre_base}_[RGB/MNDWI/IR].tif\n")
                f.write(f"  Mes: {mes_nom} ({mejor['mes']})\n")
                f.write(f"  Mision: {MISIONES_NOMBRES.get(mis, mis)}{fb_mark}{toa_mark}\n")
                f.write(f"  Nubes imagen base: {mejor['score']:.2f}%\n")
                if mejor.get('id_crudo'):
                    f.write(f"  ID imagen base: {mejor['id_crudo']}\n")
            else:
                f.write("  Sin imagenes validas\n")

        # ------------------------------------------------------------------
        f.write("\n" + "=" * 70 + "\n")
        f.write("RESUMEN FINAL\n")
        f.write("=" * 70 + "\n")
        f.write(f"{'Año':<6}{'Mes':<6}{'Mision':<10}{'Nubes':<9}{'Fallback':<10}{'Archivo'}\n")
        f.write("-" * 70 + "\n")
        for anio in anios_ord:
            mejor      = todos_los_datos[anio]['mejor']
            nombre_base = todos_los_datos[anio].get('nombre_base', '-')
            if mejor and mejor.get('mision'):
                mis  = mejor['mision']
                fb   = "[L7-FB]" if mis in MISIONES_FALLBACK else ""
                toa  = "*" if mis in MISIONES_SIN_CORRECCION else ""
                f.write(f"{anio:<6}{mejor['mes']:<6}{mis:<10}{mejor['score']:.1f}%{toa:<9}{fb:<10}{nombre_base}\n")
            else:
                f.write(f"{anio:<6}{'---':<6}{'---':<10}{'---':<9}{'':<10}Sin imagen\n")
        f.write("\n* = Sin correccion atmosferica\n")
        f.write("[L7-FB] = Landsat 7 usado como fallback (SLC-off corregido)\n")
        f.write(f"\nArchivos copiados a: {DIR_SALIDA_FINAL}\n")

    print(f"Reporte TXT: {ruta_salida}")


# ==============================================================================
# 5. TABLA PNG (una fila por mision, no por mes)
# ==============================================================================

def generar_tabla_unica_png(todos_los_datos, ruta_png):
    """
    Tabla con UNA FILA POR MISION.
    - La mejor imagen del año se resalta en azul.
    - Las filas de Landsat 7 fallback se resaltan en naranja tenue.
    """
    ids_seleccionadas = {}
    for anio in todos_los_datos:
        mejor = todos_los_datos[anio].get('mejor')
        if mejor and mejor.get('id_crudo'):
            ids_seleccionadas[anio] = mejor['id_crudo']

    filas = []
    contador = 1
    for anio in sorted(todos_los_datos.keys()):
        meses_data = todos_los_datos[anio].get('meses', {})
        for mes_num in sorted(meses_data.keys()):
            info_mes = meses_data[mes_num]
            if info_mes.get('sin_imagenes', True):
                continue
            mes_nom  = info_mes['mes_nom']
            misiones = info_mes.get('misiones', [])

            for entrada in misiones:
                mis       = entrada.get('mision', '?')
                mis_nombre = MISIONES_NOMBRES.get(mis, mis)
                img_base  = entrada.get('imagen_base')
                if not img_base:
                    continue
                es_sel = (anio in ids_seleccionadas and
                          img_base['id'] == ids_seleccionadas[anio])
                es_fb  = entrada.get('es_fallback', False)
                filas.append({
                    'num':         contador,
                    'anio':        anio,
                    'mes':         mes_nom,
                    'mision':      mis_nombre,
                    'id_imagen':   img_base['id'],
                    'nubes':       f"{img_base['nubes']:.1f}%",
                    'fecha':       img_base.get('fecha', '-'),
                    'seleccionada': es_sel,
                    'es_fallback': es_fb,
                    'n_imgs':      str(len(entrada.get('imagenes', []))),
                })
                contador += 1

    if not filas:
        print("  No hay datos para la tabla de imagenes")
        return

    columnas   = ['#', 'Año', 'Mes', 'Mision', 'ID Imagen Base', 'Nubes']
    col_widths = [0.02, 0.03, 0.03, 0.14, 0.12, 0.05]

    cell_text = [
        [str(f['num']), f['anio'], f['mes'], f['mision'],
         f['id_imagen'], f['nubes']]
        for f in filas
    ]

    ancho_fig = sum(col_widths) * 26
    fig, ax = plt.subplots(figsize=(ancho_fig, 0.35 * (len(filas) + 1) + 1.5))
    ax.axis('off')

    tabla = ax.table(
        cellText=cell_text, colLabels=columnas, colWidths=col_widths,
        bbox=[0, 0, 1, 1], cellLoc='center'
    )
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(6)

    # Encabezado
    for j in range(len(columnas)):
        c = tabla[0, j]
        c.set_facecolor('#1a6b3c')
        c.set_text_props(color='white', fontweight='bold', fontsize=7)
        c.set_edgecolor('#145a30')

    COLOR_SEL      = '#aed6f1'   # azul tenue  → mejor del año
    COLOR_SEL_TXT  = '#1a3c6b'

    for i, fila in enumerate(filas, start=1):
        if fila['seleccionada']:
            bg, fg, fw = COLOR_SEL, COLOR_SEL_TXT, 'bold'
            edge = '#5dade2'
        else:
            bg, fg, fw = 'white', 'black', 'normal'
            edge = '#d5dbdb'

        for j in range(len(columnas)):
            c = tabla[i, j]
            c.set_facecolor(bg)
            c.set_edgecolor(edge)
            c.set_text_props(color=fg, fontweight=fw, fontsize=6)

        # ID alineado a la izquierda
        tabla[i, 4].set_text_props(ha='left', fontsize=5.5, color=fg, fontweight=fw)

    # ── Leyenda principal: convenciones de color ──────────────────────────────
    leyenda = [
        mpatches.Patch(facecolor=COLOR_SEL, edgecolor='#5dade2',
                       label='Imagen seleccionada por año (menor % nubes)'),
        mpatches.Patch(facecolor='white', edgecolor='#d5dbdb',
                       label='Imagen no seleccionada (candidata del año)'),
    ]
    legend_colores = ax.legend(
        handles=leyenda,
        loc='upper left',
        bbox_to_anchor=(0.0, -0.01),
        fontsize=7, frameon=True, fancybox=True,
        title='Convención selección año',
        title_fontsize=7.5,
        ncol=1,
    )
    legend_colores.get_frame().set_edgecolor('#5dade2')
    legend_colores.get_frame().set_linewidth(1.2)
    ax.add_artist(legend_colores)

    # ── Leyenda metodología: IDEAM vs TRMM ───────────────────────────────────
    COLOR_IDEAM = '#f9ebea'
    COLOR_TRMM  = '#eaf4fb'

    met_patches = [
        mpatches.Patch(facecolor=COLOR_IDEAM, edgecolor='#e74c3c', linewidth=1.2,
                       label='IDEAM — Estaciones hidrometeorológicas terrestres\n'
                             '(precipitación observada in-situ, dato de referencia)'),
        mpatches.Patch(facecolor=COLOR_TRMM, edgecolor='#2e86c1', linewidth=1.2,
                       label='TRMM — Precipitación estimada por satélite\n'
                             '(producto 3B43 v7, resolución 0.25° × 0.25°)'),
        mpatches.Patch(facecolor='#fdfefe', edgecolor='#7d6608', linewidth=1.0,
                       label='Criterio de selección: mes con menor % nubes\n'
                             'y mayor coherencia IDEAM–TRMM en el período analizado'),
    ]
    legend_met = ax.legend(
        handles=met_patches,
        loc='upper right',
        bbox_to_anchor=(1.0, -0.01),
        fontsize=6.8, frameon=True, fancybox=True,
        title='Metodología de comparación IDEAM – TRMM',
        title_fontsize=7.5,
        ncol=1,
        handlelength=1.5,
        handleheight=1.4,
    )
    legend_met.get_frame().set_edgecolor('#2e86c1')
    legend_met.get_frame().set_linewidth(1.2)
    ax.add_artist(legend_met)

    plt.savefig(ruta_png, dpi=150, bbox_inches='tight',
                pad_inches=0.25, facecolor='white', edgecolor='none')
    plt.close()
    print(f"Tabla PNG: {ruta_png}")


# ==============================================================================
# 5.5. TABLA PNG SOLO SELECCIONADAS (una fila por año)
# ==============================================================================

def generar_tabla_seleccionadas_png(todos_los_datos, ruta_png):
    """Tabla simple: UNA FILA POR AÑO con la imagen seleccionada."""
    filas = []
    for anio in sorted(todos_los_datos.keys()):
        mejor = todos_los_datos[anio].get('mejor')
        if not mejor or not mejor.get('mision'):
            filas.append({'anio': anio, 'mes': '-', 'mision': '-',
                          'id_imagen': '-'})
            continue
        mis = mejor.get('mision', '?')
        filas.append({
            'anio':      anio,
            'mes':       mejor.get('mes', '-'),
            'mision':    MISIONES_NOMBRES.get(mis, mis),
            'id_imagen': mejor.get('id_crudo', '-'),
        })

    if not filas:
        print("  No hay datos para tabla de seleccionadas")
        return

    columnas   = ['Año', 'Mes', 'Mision', 'ID Imagen Base']
    col_widths = [0.03, 0.03, 0.14, 0.13]

    cell_text = [
        [f['anio'], f['mes'], f['mision'], f['id_imagen']]
        for f in filas
    ]

    ancho_fig = sum(col_widths) * 28
    fig, ax = plt.subplots(figsize=(ancho_fig, 0.42 * (len(filas) + 1) + 1.5))
    ax.axis('off')

    tabla = ax.table(
        cellText=cell_text, colLabels=columnas, colWidths=col_widths,
        bbox=[0, 0, 1, 1], cellLoc='center'
    )
    tabla.auto_set_font_size(False)
    tabla.set_fontsize(7)

    for j in range(len(columnas)):
        c = tabla[0, j]
        c.set_facecolor('#1a6b3c')
        c.set_text_props(color='white', fontweight='bold', fontsize=7)
        c.set_edgecolor('#145a30')

    for i, fila in enumerate(filas, start=1):
        bg = '#eafaf1' if i % 2 != 0 else '#ffffff'
        for j in range(len(columnas)):
            c = tabla[i, j]
            c.set_facecolor(bg)
            c.set_edgecolor('#a9dfbf')
            c.set_text_props(fontsize=7)
        tabla[i, 3].set_text_props(ha='left', fontsize=6)

    plt.savefig(ruta_png, dpi=150, bbox_inches='tight',
                pad_inches=0.15, facecolor='white', edgecolor='none')
    plt.close()
    print(f"Tabla seleccionadas PNG: {ruta_png}")


# ==============================================================================
# 6. FRECUENCIA DE PIXELES HUMEDOS (MNDWI)
# Corre automaticamente sobre MEJORES_POR_ANIO/MNDWI/ al terminar la seleccion
# ==============================================================================

PATRON_MNDWI = re.compile(
    r'^(\d{4})'
    r'_\d{2}_[A-Za-z]{3}_'
    r'([A-Z0-9]+(?:_[A-Z0-9]+)?)'
    r'_MNDWI\.tif$',
    re.IGNORECASE
)


def _mndwi_normalizar(arr):
    arr = arr.astype(np.float32)
    arr[arr < -100] = np.nan
    if np.nanmax(arr) > 1.1:
        arr /= 10000.0
    return arr


def _mndwi_inferir_mision(sensor_str):
    s = sensor_str.upper()
    if s in UMBRAL_POR_MISION:
        return s
    for m in UMBRAL_POR_MISION:
        if m in s or s in m:
            return m
    return 'DESCONOCIDA'


def _mndwi_listar_archivos(carpeta):
    archivos = []
    for f in os.listdir(carpeta):
        if not f.lower().endswith('.tif'):
            continue
        match = PATRON_MNDWI.match(f)
        if match:
            archivos.append((f, match.group(2).upper(), match.group(1)))
        else:
            print(f"    [MNDWI] No reconocido: {f}")
    return sorted(archivos, key=lambda x: x[2])


def calcular_frecuencia_mndwi(dir_salida_final):
    """
    Calcula la frecuencia de pixeles humedos sobre los MNDWI de MEJORES_POR_ANIO.
    Genera: frecuencia total, conteo validos, frecuencia normalizada (%) y CSV.
    """
    mndwi_dir  = os.path.join(dir_salida_final, 'MNDWI')
    salida_dir = os.path.join(dir_salida_final, 'SALIDAS_humedo_MNDWI')

    if not os.path.isdir(mndwi_dir):
        print(f"  [MNDWI] Carpeta no encontrada: {mndwi_dir} — omitiendo frecuencia.")
        return
    archivos = _mndwi_listar_archivos(mndwi_dir)
    if not archivos:
        print("  [MNDWI] No hay archivos MNDWI validos.")
        return

    os.makedirs(salida_dir, exist_ok=True)
    print(f"\n  Archivos MNDWI encontrados: {len(archivos)}")

    # Plantilla de referencia (primer archivo)
    with rasterio.open(os.path.join(mndwi_dir, archivos[0][0])) as ref:
        crs_ref = ref.crs
        bounds  = ref.bounds
        transform, width, height = calculate_default_transform(
            ref.crs, ref.crs, ref.width, ref.height, *bounds, resolution=(10.0, 10.0)
        )
        meta_base = ref.meta.copy()
        meta_base.update({'crs': crs_ref, 'transform': transform,
                          'width': width, 'height': height})

    freq_hum      = np.zeros((height, width), dtype=np.uint16)
    count_validos = np.zeros((height, width), dtype=np.uint16)

    csv_path = os.path.join(salida_dir, 'resumen_umbral_MNDWI.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fcsv:
        csv.writer(fcsv).writerow(
            ['archivo', 'sensor', 'anio', 'umbral',
             'pixeles_humedos', 'pixeles_validos', 'pixeles_excluidos']
        )

    for archivo, sensor, anio in archivos:
        mision = _mndwi_inferir_mision(sensor)
        thr    = UMBRAL_POR_MISION.get(mision, UMBRAL_FIJO_MNDWI)
        try:
            with rasterio.open(os.path.join(mndwi_dir, archivo)) as src:
                banda = np.empty((height, width), dtype=np.float32)
                reproject(
                    source=rasterio.band(src, 1), destination=banda,
                    src_transform=src.transform, src_crs=src.crs,
                    dst_transform=transform, dst_crs=crs_ref,
                    resampling=Resampling.nearest
                )
            banda = _mndwi_normalizar(banda)

            mascara_valido = (
                ~np.isnan(banda) &
                (np.abs(banda) > TOLERANCIA_CERO) &
                (banda >= -1.0) & (banda <= 1.0)
            )
            mask_humedo = (banda > thr) & mascara_valido

            n_hum  = int(np.sum(mask_humedo))
            n_val  = int(np.sum(mascara_valido))
            n_excl = int(np.sum(~mascara_valido))

            freq_hum      += mask_humedo.astype(np.uint16)
            count_validos += mascara_valido.astype(np.uint16)

            print(f"    {anio} | {sensor:<10} | umbral:{thr:>6} | "
                  f"humedos:{n_hum:>8,} | validos:{n_val:>8,} | excluidos:{n_excl:>6,}")

            # Raster binario individual (0=seco, 1=humedo, NaN=sin dato)
            salida_arr = np.full(banda.shape, np.nan, dtype=np.float32)
            salida_arr[mascara_valido] = 0
            salida_arr[mask_humedo]    = 1
            meta_out = meta_base.copy()
            meta_out.update(dtype=rasterio.float32, count=1, nodata=np.nan)
            with rasterio.open(os.path.join(salida_dir, f"Agua_{anio}_{sensor}.tif"),
                               'w', **meta_out) as dst:
                dst.write(salida_arr, 1)

            with open(csv_path, 'a', newline='', encoding='utf-8') as fcsv:
                csv.writer(fcsv).writerow(
                    [archivo, sensor, anio, thr, n_hum, n_val, n_excl]
                )
        except Exception as e:
            print(f"    [MNDWI] ERROR {archivo}: {e}")

    # --- Guardar resultados acumulados ---
    meta_u16 = meta_base.copy()
    meta_u16.update(dtype=rasterio.uint16, count=1, nodata=0)

    with rasterio.open(os.path.join(salida_dir, "Frecuencia_Total_MNDWI.tif"),
                       'w', **meta_u16) as dst:
        dst.write(freq_hum, 1)

    with rasterio.open(os.path.join(salida_dir, "Conteo_Observaciones_Validas.tif"),
                       'w', **meta_u16) as dst:
        dst.write(count_validos, 1)

    # Frecuencia normalizada: % de veces humedo sobre observaciones validas
    freq_norm = np.where(count_validos > 0,
                         (freq_hum / count_validos) * 100.0,
                         np.nan).astype(np.float32)
    meta_f32 = meta_base.copy()
    meta_f32.update(dtype=rasterio.float32, count=1, nodata=np.nan)
    with rasterio.open(os.path.join(salida_dir, "Frecuencia_Normalizada_MNDWI.tif"),
                       'w', **meta_f32) as dst:
        dst.write(freq_norm, 1)

    # Clasificacion de permanencia hidrica
    permanencia = np.zeros((height, width), dtype=np.uint8)
    con_datos = count_validos > 0
    permanencia[con_datos & (freq_norm >= 80)] = 1           # Siempre humedo
    permanencia[con_datos & (freq_norm >= 50) & (freq_norm < 80)] = 2  # Frecuente
    permanencia[con_datos & (freq_norm >= 20) & (freq_norm < 50)] = 3  # Estacional
    permanencia[con_datos & (freq_norm >=  5) & (freq_norm < 20)] = 4  # Raro
    permanencia[con_datos & (freq_norm <   5)] = 5           # Seco
    meta_u8 = meta_base.copy()
    meta_u8.update(dtype=rasterio.uint8, count=1, nodata=0)
    with rasterio.open(os.path.join(salida_dir, "Clasificacion_Permanencia_Hidrica.tif"),
                       'w', **meta_u8) as dst:
        dst.write(permanencia, 1)

    print(f"\n  Resultados MNDWI en: {salida_dir}")
    print(f"  Imagenes procesadas : {len(archivos)}")
    print(f"  Frecuencia maxima   : {int(np.max(freq_hum))}")
    total_con_datos = int(np.sum(con_datos))
    if total_con_datos > 0:
        clases = {1: 'Siempre humedo (>=80%)', 2: 'Frecuente (50-80%)',
                  3: 'Estacional (20-50%)',   4: 'Raro (5-20%)', 5: 'Seco (<5%)'}
        for cod, nombre in clases.items():
            n = int(np.sum(permanencia == cod))
            print(f"    [{cod}] {nombre:<25}: {n:>10,} px ({n/total_con_datos*100:.1f}%)")


def generar_binario_mndwi(dir_salida_final):
    """
    A partir de Frecuencia_Total_MNDWI.tif (generado por calcular_frecuencia_mndwi),
    filtra por frecuencia minima, aplica suavizado espacial opcional y guarda el
    raster binario final en SALIDAS_humedo_MNDWI/FINALES/.
    """
    salida_dir    = os.path.join(dir_salida_final, 'SALIDAS_humedo_MNDWI')
    ruta_freq     = os.path.join(salida_dir, 'Frecuencia_Total_MNDWI.tif')
    final_dir     = os.path.join(salida_dir, 'FINALES')

    if not os.path.exists(ruta_freq):
        print(f"  [BINARIO] No encontrado: {ruta_freq} — omitiendo binario.")
        return

    os.makedirs(final_dir, exist_ok=True)
    print(f"\n  Frecuencia minima : >= {FRECUENCIA_MINIMA}")
    print(f"  Suavizado         : {'Si (ventana ' + str(TAMANO_FILTRO) + 'x' + str(TAMANO_FILTRO) + ')' if APLICAR_SUAVIZADO else 'No'}")

    with rasterio.open(ruta_freq) as src:
        perfil     = src.profile
        frecuencia = src.read(1).astype(np.float32)

    print(f"  Rango frecuencia  : {int(np.min(frecuencia))} - {int(np.max(frecuencia))}")

    # Distribucion
    for i in range(1, min(int(np.max(frecuencia)) + 1, 11)):
        cnt = int(np.sum(frecuencia == i))
        if cnt > 0:
            print(f"    Freq {i}: {cnt:,} px")

    # Filtrar por frecuencia minima
    binario = (frecuencia >= FRECUENCIA_MINIMA).astype(np.uint8)
    px_antes   = int(np.sum(frecuencia >= 1))
    px_despues = int(np.sum(binario))
    print(f"  Con cualquier freq : {px_antes:,} px")
    print(f"  Con freq>={FRECUENCIA_MINIMA}        : {px_despues:,} px  ({px_antes - px_despues:,} eliminados)")

    # Suavizado espacial
    if APLICAR_SUAVIZADO:
        suavizado  = uniform_filter(binario.astype(float), size=TAMANO_FILTRO, mode='nearest')
        resultado  = (suavizado >= UMBRAL_SUAVIZADO).astype(np.uint8)
        sufijo     = f"_freq{FRECUENCIA_MINIMA}_suavizado"
        print(f"  Px tras suavizado  : {int(np.sum(resultado)):,} ({int(np.sum(resultado)) - px_despues:+,})")
    else:
        resultado = binario
        sufijo    = f"_freq{FRECUENCIA_MINIMA}"

    # Guardar binario final
    perfil.update(dtype='uint8', nodata=0, count=1)
    nombre_bin = f"final_MNDWI_binario{sufijo}.tif"
    with rasterio.open(os.path.join(final_dir, nombre_bin), 'w', **perfil) as dst:
        dst.write(resultado, 1)

    # Guardar frecuencia filtrada
    freq_filtrada = np.where(frecuencia >= FRECUENCIA_MINIMA, frecuencia, 0)
    perfil_u16    = perfil.copy()
    perfil_u16.update(dtype='uint16', nodata=0)
    nombre_freq_f = f"Frecuencia_filtrada_min{FRECUENCIA_MINIMA}.tif"
    with rasterio.open(os.path.join(salida_dir, nombre_freq_f), 'w', **perfil_u16) as dst:
        dst.write(freq_filtrada.astype(np.uint16), 1)

    px_agua = int(np.sum(resultado))
    print(f"  Agua final         : {px_agua:,} px ({px_agua / resultado.size * 100:.2f}%)")
    print(f"  Binario guardado   : {os.path.join(final_dir, nombre_bin)}")


# ==============================================================================
# 7. LECTURA DE SELECCION MANUAL (mejores.txt)
# ==============================================================================

ARCHIVO_MEJORES = RUTA_MEJORES_TXT

# Patron para parsear lineas de mejores.txt:
#   1988_10_OCT_LT04_19881023
PATRON_MEJORES = re.compile(
    r'^(\d{4})_(\d{2})_([A-Z]{3})_([A-Z0-9]+)_(\d{8})$'
)


def leer_seleccion_manual(ruta_txt):
    """
    Lee mejores.txt y retorna lista de dicts con la info parseada.
    Cada linea tiene formato: YYYY_MM_MES_MISION_YYYYMMDD
    """
    if not os.path.exists(ruta_txt):
        print(f"ERROR: No se encuentra {ruta_txt}")
        return []

    seleccion = []
    with open(ruta_txt, 'r', encoding='utf-8') as f:
        for linea in f:
            linea = linea.strip()
            if not linea or linea.startswith('#'):
                continue
            match = PATRON_MEJORES.match(linea)
            if match:
                seleccion.append({
                    'anio':      match.group(1),
                    'mes_num':   match.group(2),
                    'mes_nom':   match.group(3),
                    'mision':    match.group(4),
                    'fecha_id':  match.group(5),
                    'base_name': linea,   # nombre base sin producto
                })
            else:
                print(f"  [AVISO] Linea no reconocida en mejores.txt: {linea}")
    return seleccion


def copiar_seleccion_manual(seleccion):
    """
    Copia los archivos IR, MNDWI y RGB de cada imagen seleccionada
    desde las carpetas de producto a MEJORES_POR_AÑO.
    """
    productos = ['RGB', 'MNDWI', 'IR', 'NDWI']
    for entrada in seleccion:
        base = entrada['base_name']
        copiados = []
        for prod in productos:
            carpeta_origen  = os.path.join(DIR_RAIZ, prod)
            carpeta_destino = os.path.join(DIR_SALIDA_FINAL, prod)
            if not os.path.exists(carpeta_origen):
                continue
            os.makedirs(carpeta_destino, exist_ok=True)
            nombre_archivo = f"{base}_{prod}.tif"
            ruta_origen    = os.path.join(carpeta_origen, nombre_archivo)
            if os.path.exists(ruta_origen):
                ruta_destino = os.path.join(carpeta_destino, nombre_archivo)
                shutil.copy2(ruta_origen, ruta_destino)
                copiados.append(prod)
            else:
                print(f"    [!] No encontrado: {nombre_archivo}")
        print(f"  {base}  ->  copiados: {', '.join(copiados) if copiados else 'NINGUNO'}")
    return


def construir_datos_desde_seleccion(seleccion):
    """
    Construye la estructura todos_los_datos a partir de la seleccion manual
    para generar reportes y tablas PNG.
    """
    todos_los_datos = {}
    for entrada in seleccion:
        anio     = entrada['anio']
        mes_num  = entrada['mes_num']
        mes_nom  = entrada['mes_nom']
        mision   = entrada['mision']
        base     = entrada['base_name']

        mejor = {
            'mes':      mes_nom,
            'mision':   mision,
            'score':    0.0,       # sin dato de nubes (seleccion manual)
            'id_crudo': base,
            'archivo':  base,
        }

        meses_data = {
            mes_num: {
                'mes_nom':      mes_nom,
                'sin_imagenes': False,
                'misiones': [{
                    'mision':           mision,
                    'imagenes':         [{'id': base, 'nubes': 0.0}],
                    'imagen_base':      {'id': base, 'nubes': 0.0},
                    'archivo_exportado': base,
                    'meses_relleno':    [],
                    'es_fallback':      mision in MISIONES_FALLBACK,
                }],
                'mision':           mision,
                'imagenes':         [{'id': base, 'nubes': 0.0}],
                'imagen_base':      {'id': base, 'nubes': 0.0},
                'archivo_exportado': base,
                'meses_relleno':    [],
            }
        }

        todos_los_datos[anio] = {
            'mejor':             mejor,
            'meses':             meses_data,
            'meses_buscados':    [mes_nom],
            'archivos_copiados': [],
            'nombre_base':       base,
        }
    return todos_los_datos


# ==============================================================================
# 8. EJECUCION
# ==============================================================================
if __name__ == "__main__":
    os.makedirs(DIR_SALIDA_FINAL, exist_ok=True)

    # ── MODO: manual (mejores.txt existe) o automático (desde logs) ──────────
    if os.path.exists(ARCHIVO_MEJORES):
        # ── MODO MANUAL ───────────────────────────────────────────────────────
        print("=" * 60)
        print("SELECCION MANUAL DE MEJORES IMAGENES")
        print(f"Leyendo seleccion desde: {ARCHIVO_MEJORES}")
        print("=" * 60)

        seleccion = leer_seleccion_manual(ARCHIVO_MEJORES)
        if not seleccion:
            print("No hay imagenes validas en mejores.txt.")
            exit()

        print(f"\nImagenes seleccionadas: {len(seleccion)}")
        for s in seleccion:
            mis_nombre = MISIONES_NOMBRES.get(s['mision'], s['mision'])
            print(f"  {s['anio']} | {s['mes_nom']} | {mis_nombre} | {s['base_name']}")

        print(f"\nCopiando archivos a {DIR_SALIDA_FINAL}...")
        copiar_seleccion_manual(seleccion)

        todos_los_datos = construir_datos_desde_seleccion(seleccion)

    else:
        # ── MODO AUTOMATICO ───────────────────────────────────────────────────
        print("=" * 60)
        print("SELECCION AUTOMATICA DE MEJORES IMAGENES")
        print(f"mejores.txt no encontrado → procesando logs en: {DIR_LOGS}")
        print("Metodologia: menor % nubes (metadata) + analisis de pixeles RGB")
        print("=" * 60)

        if not os.path.isdir(DIR_LOGS):
            print(f"ERROR: Carpeta de logs no encontrada: {DIR_LOGS}")
            exit()

        archivos_log = sorted([
            f for f in os.listdir(DIR_LOGS)
            if f.lower().endswith(('.log', '.txt'))
        ])
        if not archivos_log:
            print(f"ERROR: No se encontraron archivos .log/.txt en {DIR_LOGS}")
            exit()

        print(f"\nLogs encontrados: {len(archivos_log)}")
        todos_los_datos = {}

        for nombre_log in archivos_log:
            ruta_log = os.path.join(DIR_LOGS, nombre_log)
            print(f"\n{'─'*55}")
            print(f"Log: {nombre_log}")
            print(f"{'─'*55}")

            try:
                mejor_global, meses_data, meses_encontrados = analizar_log_completo(ruta_log)
            except Exception as e:
                print(f"  ERROR al parsear log: {e}")
                continue

            if not meses_data:
                print("  Sin datos utiles en este log.")
                continue

            # Detectar año desde los archivos exportados o nombre del log
            anios_en_log = set()
            for info in meses_data.values():
                for entrada in info.get('misiones', []):
                    arch = entrada.get('archivo_exportado') or ''
                    m = re.match(r'^(\d{4})', arch)
                    if m:
                        anios_en_log.add(m.group(1))
            if not anios_en_log:
                m = re.search(r'(\d{4})', nombre_log)
                if m:
                    anios_en_log.add(m.group(1))
            if not anios_en_log:
                print("  No se pudo determinar el año — saltando log.")
                continue

            anio = sorted(anios_en_log)[0]
            print(f"  Año detectado: {anio}")
            print(f"  Meses con datos: {', '.join(sorted(meses_encontrados, key=lambda x: MESES_MAP.get(x,'99')))}")

            # Seleccion automatica por pixeles
            ganador = seleccionar_mejor_por_pixeles(anio, meses_data, DIR_RAIZ)

            if not ganador:
                print(f"  [{anio}] Sin candidatos validos.")
                todos_los_datos[anio] = {
                    'mejor': None, 'meses': meses_data,
                    'meses_buscados': meses_encontrados,
                    'archivos_copiados': [], 'nombre_base': '',
                }
                continue

            print(f"\n  [{anio}] SELECCIONADO → {ganador['mes']} | "
                  f"{ganador.get('mision','')} | nubes: {ganador['score']:.1f}%")

            # Copiar archivos al destino
            archivos_copiados, nombre_base = copiar_archivos(anio, ganador)
            ganador['archivo'] = ganador.get('archivo') or nombre_base
            if archivos_copiados:
                print(f"  Copiados: {', '.join(archivos_copiados)}")
            else:
                print(f"  [!] No se copiaron archivos — verificar rutas TIF.")

            # Relleno de nubes/nodata sobre la imagen seleccionada
            aplicar_relleno_imagen_seleccionada(anio, ganador, meses_data)

            todos_los_datos[anio] = {
                'mejor':             ganador,
                'meses':             meses_data,
                'meses_buscados':    meses_encontrados,
                'archivos_copiados': archivos_copiados,
                'nombre_base':       nombre_base,
            }

    if not todos_los_datos:
        print("\nSin datos para generar reportes.")
        exit()

    # ── Salidas comunes a ambos modos ─────────────────────────────────────────
    # Tabla PNG seleccionadas (una fila por año)
    print("\nGenerando tabla PNG seleccionadas...")
    ruta_tabla_sel = os.path.join(DIR_SALIDA_FINAL, "TABLA_SELECCIONADAS_POR_AÑO.png")
    generar_tabla_seleccionadas_png(todos_los_datos, ruta_tabla_sel)

    # Reporte TXT
    ruta_reporte = os.path.join(DIR_SALIDA_FINAL, "REPORTE_COMPLETO_IMAGENES.txt")
    generar_reporte_completo(todos_los_datos, ruta_reporte)

    # Tabla PNG completa
    print("Generando tabla PNG completa...")
    ruta_tabla = os.path.join(DIR_SALIDA_FINAL, "TABLA_IMAGENES_COMPLETA.png")
    generar_tabla_unica_png(todos_los_datos, ruta_tabla)

    # Frecuencia MNDWI
    print("\n" + "=" * 60)
    print("FRECUENCIA DE PIXELES HUMEDOS (MNDWI)")
    print("=" * 60)
    calcular_frecuencia_mndwi(DIR_SALIDA_FINAL)

    # Binario MNDWI final
    print("\n" + "=" * 60)
    print("GENERADOR DE BINARIO MNDWI FINAL")
    print("=" * 60)
    generar_binario_mndwi(DIR_SALIDA_FINAL)

    print("\n" + "=" * 60)
    print("PROCESO COMPLETADO")
    print("=" * 60)
