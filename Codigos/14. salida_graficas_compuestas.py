# -*- coding: utf-8 -*-
"""
PLANTILLA: MAPA CON IMAGEN SENTINEL-2 COMO FONDO
=================================================
- Zoom sobre capa de referencia + buffer configurable
- Todo en EPSG:9377 (MAGNA SIRGAS Origen Unico Nacional de Colombia)
- Detecta automaticamente el CRS de cada capa y lo reproyecta a 9377
- Grilla Norte/Este coherente con escala grafica, en gris oscuro
- Plantilla extensible: agregar capas en CAPAS_VECTOR
"""

import geopandas as gpd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import matplotlib.patheffects as pe
import matplotlib.colors as mcolors
from matplotlib_scalebar.scalebar import ScaleBar
from pyproj import Transformer, CRS
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject as rasterio_reproject, Resampling, calculate_default_transform
import numpy as np
import os

# ==============================================================================
# 1. RUTAS — PONER AQUI TODAS LAS RUTAS
# ==============================================================================

# --- Imagen satelital de fondo (Sentinel-2 u otro raster RGB) ---
RUTA_IMAGEN_SATELITAL   = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MULTIBANDA\S2_2025-12-06_T18PUQ_SR.tif"

# --- Componentes de analisis ---
RUTA_HIDROLOGICO        = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\HIDROLOGICO\HIDROLOGICO.shp"
RUTA_GEOMORFOLOGICO     = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\DEM\resultados_Geomorfologico\poligono_geomorfologico_INDICE.shp"
RUTA_ECOSISTEMICO       = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\COBERTURAS\Cienagas\coberturas.shp"
RUTA_CAUSE_PERMANENTE   = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\POLIGONO_FINAL_PRELIMINAR\BUP_PRELIMINAR_LA_CHIQUITA.shp"
RUTA_DEM                = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\DEM\copernicus_dem_glo30_30m_buffer_microrelief_exag10x_local.tif"

# --- Capas base cartograficas ---
RUTA_GDB                = r'C:\Users\sebas\OneDrive\Documentos\ANT\25k_2017.gdb'
RUTA_MUNICIPIOS         = r'C:\Users\sebas\OneDrive\Documentos\ANT\MGN2023_MPIO_POLITICO\MGN_ADM_MPIO_GRAFICO.shp'
# --- LABEL CENTRAL (dejar '' para no mostrar) ---
NOMBRE_LABEL       = 'CIÉNAGA LA CHIQUITA'
NOMBRE_LABEL_SIZE  = 15
# --- SALIDA ---
DIR_SALIDA    = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA"
NOMBRE_SALIDA = 'MAPA_SENTINEL.png'
RUTA_SALIDA   = os.path.join(DIR_SALIDA, NOMBRE_SALIDA)
DPI_SALIDA    = 150
ANCHO_PX      = 2800        # píxeles de ancho del PNG final
ALTO_PX       = 2400        # píxeles de alto  del PNG final
FIGSIZE       = (ANCHO_PX / DPI_SALIDA, ALTO_PX / DPI_SALIDA)  # pulgadas calculadas
# Escala tipografica: ajusta todos los textos al tamaño fisico del mapa.
# Referencia base = figura de 10" de ancho → FONT_SCALE = 1.0
# Para figuras mas grandes los textos crecen proporcionalmente.
FONT_SCALE    = FIGSIZE[0] / 10.0

# ==============================================================================
# 2. CAPAS ACTIVAS  (1 = encendida  |  0 = apagada)
#    Los números de la derecha identifican cada capa para BUFFER_CAPA (ver abajo)
# ==============================================================================
#                                                          # N°buffer
ACTIVO_IMAGEN_SATELITAL = 1                             #  —  (raster, no aplica)
ACTIVO_DEM              = 0                              #  —  (raster, no aplica)
ACTIVO_HIDROLOGICO      = 0                            #   1
ACTIVO_GEOMORFOLOGICO   = 0                            #   2
ACTIVO_ECOSISTEMICO     = 0                             #   3
ACTIVO_CAUSE_PERMANENTE = 1                              #   4
ACTIVO_DRENAJE_SENCILLO = 1                               #  —  (línea, no aplica)
ACTIVO_DRENAJE_DOBLE    = 1                               #  —  (línea, no aplica)
ACTIVO_MUNICIPIOS       = 1                               #  —  (línea, no aplica)

# ==============================================================================
# 3. CONFIGURACION GENERAL
# ==============================================================================

# --- CRS DE SALIDA (no cambiar) ---
EPSG_SALIDA = 9377   # MAGNA SIRGAS / Colombia Origen Unico Nacional

# --- CAPA DE REFERENCIA PARA EL BUFFER/ZOOM ---
# Pon aquí el número de la capa (ver columna N°buffer en sección 2)
#   1 = Hidrologico  |  2 = Geomorfologico  |  3 = Ecosistemico  |  4 = Cause Permanente
BUFFER_CAPA = 4

_SHP_POR_NUMERO = {1: RUTA_HIDROLOGICO, 2: RUTA_GEOMORFOLOGICO, 3: RUTA_ECOSISTEMICO, 4: RUTA_CAUSE_PERMANENTE}
SHP_REFERENCIA  = _SHP_POR_NUMERO.get(BUFFER_CAPA, RUTA_HIDROLOGICO)

# Buffer alrededor del bbox de SHP_REFERENCIA (en metros)
# 0 = encuadre exacto | 1000 = 1 km extra por lado
BUFFER_M = 900 # metros

# --- DEM (elevación + hillshading) ---
# DEM_VMIN / DEM_VMAX: None = rango real del recorte | fijos: ej. 0, 500
DEM_VMIN   = None       # None = automático
DEM_VMAX   = None       # None = automático
DEM_ALPHA  = 0.75       # transparencia del DEM sobre el fondo
DEM_LABEL  = 'Elevación (m.s.n.m.)'

# Hillshading — sombra de relieve
DEM_HILLSHADE    = True   # False = solo color plano sin sombra
DEM_AZIMUTH      = 315    # dirección de la luz en grados (315 = NW, estándar cartográfico)
DEM_ALTITUD_LUZ  = 40     # elevación de la fuente de luz en grados (0=horizonte, 90=cenital)
DEM_EXAGERACION  = 2.0    # exageración vertical (>1 resalta más el relieve)
DEM_BLEND_MODE   = 'overlay'  # 'overlay' | 'soft' | 'hsv'
# Si el DEM reporta EPSG None (WKT sin AUTHORITY), forzar este EPSG.
# 9377 = MAGNA SIRGAS Origen Unico (dem_filled procesado en el flujo colombiano)
# 4326 = WGS84 geografico  |  32618 = WGS84 UTM 18N  |  None = no forzar
EPSG_DEM_FORZAR  = 4326

# --- IMAGEN DE FONDO ---
RUTA_RASTER_FONDO = RUTA_IMAGEN_SATELITAL
BANDAS_RGB        = (6, 4, 1) if ACTIVO_CAUSE_PERMANENTE else (3, 2, 1)  # cauce: B12/B8/B2 | resto: RGB natural (B4/B3/B2)
PERCENTIL_LOW     = 2 if ACTIVO_CAUSE_PERMANENTE else 1    # cauce: percent clip estilo ArcGIS
PERCENTIL_HIGH    = 98          # recorte percentil superior para stretch
ALPHA_RASTER      = 1.0 if ACTIVO_CAUSE_PERMANENTE else 0.5   # cauce: opaco total | resto: semi-transparente
# Ajustes de brillo para imágenes oscuras (ej. tomadas de noche o con poca luz)
#   GAMMA_RASTER: < 1 aclara (ej. 0.5), > 1 oscurece (ej. 1.5), 1.0 = sin cambio
#   BRILLO_RASTER: suma aditiva al rango [0,1] (ej. 0.15 aclara), 0.0 = sin cambio
GAMMA_RASTER      = 1.0 if ACTIVO_CAUSE_PERMANENTE else 0.7   # cauce: sin gamma (ArcGIS) | resto: aclara
BRILLO_RASTER     = 0.0 if ACTIVO_CAUSE_PERMANENTE else 0.2   # cauce: sin offset | resto: brillo extra
# Desaturación: 0.0 = color original | 1.0 = escala de grises completa
DESAT_RASTER      = 0.0         # sin desaturacion — percent clip ya da buenos colores
# Si el raster reporta EPSG None (WKT sin AUTHORITY), forzar este EPSG
# para garantizar la transformación datum correcta al reproyectar a 9377.
# 32618 = WGS84 / UTM zone 18N  |  None = no forzar (usar WKT tal cual)
EPSG_IMAGEN_FORZAR = 32618

# --- GRILLA DE COORDENADAS ---
GRILLA_COLOR     = '#3C3939'    # gris oscuro
GRILLA_ALPHA     = 0.8
GRILLA_LINEWIDTH = 1.5
GRILLA_FONTSIZE  = int(round(9 * FONT_SCALE))
# Intervalo fijo en metros (None = calculado automaticamente segun el extent)
GRILLA_INTERVALO = None         # ej: 1000, 2000, 5000 — None = auto

# --- RECUADRO CRS (posicion vertical en fraccion del axes, 0=abajo 1=arriba) ---
POS_Y_CRS_BOX = 0.1



# ==============================================================================
# 4. CAPAS VECTORIALES
#    Usan las rutas y los interruptores definidos arriba.
#    El orden en la lista es el orden de dibujo (primero = abajo).
# ==============================================================================

CAPAS_VECTOR = [

    # ── CAPA 1: Componente Hidrologico ────────────────────────────────────────
    {
        'nombre':     'hidrologico',
        'ruta':       RUTA_HIDROLOGICO,
        'layer':      None,         # None = SHP/GPKG; str = layer dentro de GDB
        'tipo':       'poligono',   # 'poligono' | 'linea' | 'punto'
        'facecolor':  'none',
        'edgecolor':  '#2196F3',    # azul brillante
        'linewidth':  2.0,
        'linestyle':  '-',
        'alpha':      1.0,
        'markersize': 6,
        'label':      'Componente Hidrologico',
        'zorder':     5,
        'halo':       True,
        'halo_color': 'white',
        'halo_width': 3.5,
        'visible':    bool(ACTIVO_HIDROLOGICO),
    },

    # ── CAPA 2: Componente Geomorfologico ─────────────────────────────────────
    {
        'nombre':     'geomorfologico',
        'ruta':       RUTA_GEOMORFOLOGICO,
        'layer':      None,
        'tipo':       'poligono',
        'facecolor':  'none',
        'edgecolor':  '#D84315',    # naranja oscuro
        'linewidth':  1.5,
        'linestyle':  '-',
        'alpha':      1.0,
        'markersize': 6,
        'label':      'Componente Geomorfologico',
        'zorder':     6,
        'halo':       True,
        'halo_color': 'white',
        'halo_width': 3.5,
        'visible':    bool(ACTIVO_GEOMORFOLOGICO),
    },

    # ── CAPA 3: Componente Ecosistemico ───────────────────────────────────────
    {
        'nombre':     'ecosistemico',
        'ruta':       RUTA_ECOSISTEMICO,
        'layer':      None,
        'tipo':       'poligono',
        'facecolor':  'none',
        'edgecolor':  '#388E3C',    # verde oscuro
        'linewidth':  1.5,
        'linestyle':  '-',
        'alpha':      1.0,
        'markersize': 6,
        'label':      'Componente Ecosistemico',
        'zorder':     7,
        'halo':       True,
        'halo_color': 'white',
        'halo_width': 3.5,
        'visible':    bool(ACTIVO_ECOSISTEMICO),
    },

    # ── CAPA 4: Cauce Permanente ───────────────────────────────────────────────
    {
        'nombre':     'cause_permanente',
        'ruta':       RUTA_CAUSE_PERMANENTE,
        'layer':      None,
        'tipo':       'poligono',
        'facecolor':  '#1565C0',    # azul con transparencia (ver alpha)
        'edgecolor':  '#0D47A1',    # azul oscuro borde
        'linewidth':  1.5,
        'linestyle':  '-',
        'alpha':      0.35,         # relleno azul semi-transparente
        'markersize': 6,
        'label':      'Cauce Permanente',
        'zorder':     8,
        'halo':       True,
        'halo_color': 'white',
        'halo_width': 2.5,
        'visible':    bool(ACTIVO_CAUSE_PERMANENTE),
    },

    # ── CAPA 6: Drenaje Sencillo (GDB) ─────────────────────────────────────────
    {
        'nombre':     'drenaje_sencillo',
        'ruta':       RUTA_GDB,
        'layer':      'Drenaje_Sencillo',   # feature class dentro de la GDB
        'tipo':       'linea',
        'facecolor':  None,
        'edgecolor':  '#1a5276',
        'linewidth':  0.7,
        'linestyle':  '-',
        'alpha':      0.85,
        'markersize': 6,
        'label':      'Drenaje Sencillo',
        'zorder':     4,
        'halo':       False,
        'halo_color': 'white',
        'halo_width': 2.0,
        'visible':    bool(ACTIVO_DRENAJE_SENCILLO),
    },

    # ── CAPA 7: Drenaje Doble (GDB) ────────────────────────────────────────────
    {
        'nombre':     'drenaje_doble',
        'ruta':       RUTA_GDB,
        'layer':      'Drenaje_Doble',      # feature class dentro de la GDB
        'tipo':       'poligono',
        'facecolor':  '#1a5276',
        'edgecolor':  '#154360',
        'linewidth':  0.3,
        'linestyle':  '-',
        'alpha':      0.75,
        'markersize': 6,
        'label':      'Drenaje Doble',
        'zorder':     4,
        'halo':       False,
        'halo_color': 'white',
        'halo_width': 2.0,
        'visible':    bool(ACTIVO_DRENAJE_DOBLE),
    },

    # ── CAPA 8: Municipios solo borde ───────────────────────────────────────────
    {
        'nombre':     'municipios',
        'ruta':       RUTA_MUNICIPIOS,
        'layer':      None,
        'tipo':       'poligono',
        'facecolor':  'none',
        'edgecolor':  'black',
        'linewidth':  1.5,
        'linestyle':  '-',
        'alpha':      1.0,
        'markersize': 6,
        'label':      'Municipios',
        'zorder':     3,
        'halo':       True,
        'halo_color': 'white',
        'halo_width': 3.0,
        'visible':    bool(ACTIVO_MUNICIPIOS),
    },
]

# ==============================================================================
# 5. FUNCIONES AUXILIARES
# ==============================================================================

CRS_SALIDA = CRS.from_epsg(EPSG_SALIDA)

# Paleta de relieve cartográfico: verde saturado → amarillo → naranja → marrón → gris pico
from matplotlib.colors import LinearSegmentedColormap as _LSC
CMAP_ELEVACION = _LSC.from_list('relieve_cartografico', [
    '#4A9E6B',   # verde oscuro    (llanuras bajas)
    '#7BBF72',   # verde medio     (tierras bajas)
    '#B8D97A',   # verde-amarillo  (ondulado suave)
    '#E8D060',   # amarillo        (colinas bajas)
    '#DDA840',   # dorado-ocre     (colinas medias)
    '#C07830',   # naranja-marrón  (colinas altas)
    '#9A5520',   # marrón          (lomas pronunciadas)
    '#7A4010',   # marrón oscuro   (montañas)
    '#C0B0A0',   # gris-beige      (altas cumbres)
    '#F0EFEE',   # blanco-gris     (picos / cimas)
])


def reproyectar_gdf(gdf, crs_destino=CRS_SALIDA):
    """Reproyecta un GeoDataFrame al CRS de destino si es necesario."""
    if gdf.crs is None:
        print("    ADVERTENCIA: capa sin CRS, se asume que ya esta en el destino.")
        return gdf
    if gdf.crs != crs_destino:
        print(f"    Reproyectando {gdf.crs.to_epsg()} → {crs_destino.to_epsg()}...")
        return gdf.to_crs(crs_destino)
    return gdf


def leer_raster_como_rgb(ruta, bandas_rgb, crs_destino, bbox_dest,
                          perc_low=2, perc_high=98, gamma=1.0, brillo=0.0, desat=0.0):
    """
    Lee raster, reproyecta a crs_destino y normaliza.
    El grid de salida se define EXACTAMENTE sobre bbox_dest → alineación
    perfecta con capas vectoriales, sin offset por pixel-snapping.

    Returns
    -------
    rgb_norm : np.ndarray (H, W, 3) float32 en [0,1]
    extent   : [xmin, xmax, ymin, ymax] en crs_destino  (= bbox_dest)
    ok       : bool
    """
    from rasterio.transform import from_bounds as _rfb
    try:
        xmin, ymin, xmax, ymax = bbox_dest

        with rasterio.open(ruta) as src:
            crs_src = src.crs
            # Si el WKT no tiene AUTHORITY el EPSG queda None → forzar
            if crs_src is not None and crs_src.to_epsg() is None and EPSG_IMAGEN_FORZAR is not None:
                print(f"    CRS raster: EPSG detectado como None → forzando EPSG:{EPSG_IMAGEN_FORZAR}")
                crs_src = CRS.from_epsg(EPSG_IMAGEN_FORZAR)
            else:
                print(f"    CRS raster: {crs_src}")
            print(f"    Bandas: {src.count}  |  Resolucion: {src.res}")

            # Grid de salida EXACTAMENTE = bbox del mapa en crs_destino
            # → el extent del imshow ES el bbox; cero desfase posible
            res   = src.res[0]   # resolución fuente (metros para S2 UTM)
            dst_w = max(1, int(round((xmax - xmin) / res)))
            dst_h = max(1, int(round((ymax - ymin) / res)))
            dst_tf = _rfb(xmin, ymin, xmax, ymax, dst_w, dst_h)

            # Reproyectar directamente al grid del mapa
            # rasterio.band() hace lectura eficiente sin cargar el TIF completo
            bandas_repr = []
            for b in bandas_rgb:
                arr = np.zeros((dst_h, dst_w), dtype=np.float32)
                rasterio_reproject(
                    source=rasterio.band(src, b),
                    destination=arr,
                    src_crs=crs_src,
                    dst_transform=dst_tf,
                    dst_crs=crs_destino,
                    resampling=Resampling.bilinear
                )
                bandas_repr.append(arr)

        # Normalizar por percentiles (ignorar nodata = 0)
        rgb_norm = []
        for banda in bandas_repr:
            validos = banda[banda > 0]
            if validos.size == 0:
                rgb_norm.append(np.zeros_like(banda))
                continue
            lo = np.percentile(validos, perc_low)
            hi = np.percentile(validos, perc_high)
            if hi <= lo:
                hi = lo + 1e-6
            norm = np.clip((banda - lo) / (hi - lo), 0, 1)
            if gamma != 1.0:
                norm = np.power(norm, gamma)
            if brillo != 0.0:
                norm = np.clip(norm + brillo, 0, 1)
            rgb_norm.append(norm.astype(np.float32))

        rgb = np.stack(rgb_norm, axis=-1)

        # Desaturación: mezcla con luminancia perceptual
        if desat > 0.0:
            lum = (0.299 * rgb[:, :, 0] + 0.587 * rgb[:, :, 1] + 0.114 * rgb[:, :, 2])
            lum3 = np.stack([lum, lum, lum], axis=-1)
            rgb = np.clip((1.0 - desat) * rgb + desat * lum3, 0, 1).astype(np.float32)

        # Extent exactamente = bbox_dest → alineación garantizada
        extent = [xmin, xmax, ymin, ymax]
        print(f"    Raster procesado: {dst_w}x{dst_h} px en EPSG:{EPSG_SALIDA}")
        return rgb, extent, True

    except Exception as e:
        print(f"    ERROR al leer raster: {e}")
        return None, None, False


def leer_raster_dem(ruta, crs_destino, bbox_dest):
    """
    Lee un DEM de banda única, recorta al bbox y reproyecta a crs_destino.
    Devuelve: data (2D float32), extent [L,R,B,T], vmin, vmax, ok
    """
    try:
        with rasterio.open(ruta) as src:
            crs_src_orig = src.crs   # CRS original del archivo (para transformar bbox)
            crs_src      = src.crs
            nodata       = src.nodata
            # Si el WKT no tiene AUTHORITY, to_epsg() devuelve None → forzar
            if crs_src is not None and crs_src.to_epsg() is None and EPSG_DEM_FORZAR is not None:
                print(f"    CRS DEM: EPSG detectado como None → forzando EPSG:{EPSG_DEM_FORZAR}")
                print(f"             WKT original: {crs_src.to_wkt()[:80]}...")
                crs_src = CRS.from_epsg(EPSG_DEM_FORZAR)
            else:
                print(f"    CRS DEM: {crs_src}  |  Res: {src.res}  |  Nodata: {nodata}")

            # Transformar bbox al CRS nativo del DEM
            # Usar el CRS ORIGINAL del archivo (no el forzado) para que coincida con src.transform
            crs_para_bbox = crs_src_orig if crs_src_orig is not None else crs_src
            try:
                mismos_crs = crs_para_bbox.equals(crs_destino)
            except Exception:
                mismos_crs = str(crs_para_bbox) == str(crs_destino)

            if not mismos_crs:
                tf = Transformer.from_crs(crs_destino, crs_para_bbox, always_xy=True)
                x0, y0 = tf.transform(bbox_dest[0], bbox_dest[1])
                x1, y1 = tf.transform(bbox_dest[2], bbox_dest[3])
                bbox_src = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                print(f"    bbox DEM (CRS orig): {bbox_src}")
            else:
                bbox_src = bbox_dest

            window = from_bounds(*bbox_src, src.transform)
            data   = src.read(1, window=window).astype(np.float32)
            win_tf = src.window_transform(window)
            h, w   = data.shape

        # Usar bounds reales del window (pixel-snapped) para evitar offset
        win_left   = win_tf.c
        win_top    = win_tf.f
        win_right  = win_left + w * win_tf.a
        win_bottom = win_top  + h * win_tf.e   # e negativo

        # Reproyectar a CRS de salida
        dst_tf, dst_w, dst_h = calculate_default_transform(
            crs_src, crs_destino, w, h,
            left=win_left, bottom=win_bottom,
            right=win_right, top=win_top)
        dst = np.zeros((dst_h, dst_w), dtype=np.float32)
        rasterio_reproject(
            source=data, destination=dst,
            src_transform=win_tf, src_crs=crs_src,
            dst_transform=dst_tf, dst_crs=crs_destino,
            resampling=Resampling.bilinear)

        # Enmascarar nodata y valores inválidos comunes
        if nodata is not None:
            dst = np.where(np.isclose(dst, nodata, atol=1), np.nan, dst)
        dst = np.where(dst < -9000, np.nan, dst)

        vmin = float(np.nanmin(dst)) if not np.all(np.isnan(dst)) else 0.0
        vmax = float(np.nanmax(dst)) if not np.all(np.isnan(dst)) else 1.0

        extent = [
            dst_tf.c,
            dst_tf.c + dst_w * dst_tf.a,
            dst_tf.f + dst_h * dst_tf.e,
            dst_tf.f,
        ]
        print(f"    DEM procesado: {dst_w}x{dst_h} px  |  "
              f"Elevación {vmin:.0f} – {vmax:.0f} m")
        return dst, extent, vmin, vmax, True

    except Exception as e:
        print(f"    ERROR al leer DEM: {e}")
        return None, None, 0.0, 1.0, False


def dibujar_capa_vector(ax, gdf, capa):
    """Dibuja una capa vector segun su tipo y estilo."""
    tipo = capa['tipo']
    fc   = capa['facecolor']
    ec   = capa['edgecolor']
    lw   = capa['linewidth']
    ls   = capa['linestyle']
    al   = capa['alpha']
    zo   = capa['zorder']

    if tipo == 'poligono':
        if capa['halo']:
            gdf.plot(ax=ax, facecolor='none', edgecolor=capa['halo_color'],
                     linewidth=capa['halo_width'], zorder=zo - 0.5, alpha=1.0)
        gdf.plot(ax=ax, facecolor=fc, edgecolor=ec,
                 linewidth=lw, linestyle=ls, alpha=al, zorder=zo)

    elif tipo == 'linea':
        if capa['halo']:
            gdf.plot(ax=ax, color=capa['halo_color'],
                     linewidth=capa['halo_width'], zorder=zo - 0.5, alpha=1.0)
        gdf.plot(ax=ax, color=ec, linewidth=lw,
                 linestyle=ls, alpha=al, zorder=zo)

    elif tipo == 'punto':
        if capa['halo']:
            gdf.plot(ax=ax, color=capa['halo_color'],
                     markersize=capa['markersize'] + capa['halo_width'],
                     zorder=zo - 0.5, alpha=1.0)
        gdf.plot(ax=ax, color=fc, edgecolor=ec,
                 markersize=capa['markersize'], linewidth=lw,
                 alpha=al, zorder=zo)


def dibujar_flecha_norte(ax, x=0.96, y=0.96, tamano=0.055):
    """Flecha de norte en coordenadas relativas del axes."""
    margen = tamano * 0.15
    ax.add_patch(mpatches.FancyBboxPatch(
        (x - tamano/2 - margen, y - tamano*1.85 - margen),
        tamano + 2*margen, tamano*1.85 + 2*margen + tamano*0.1,
        transform=ax.transAxes, facecolor='white', alpha=0.80,
        edgecolor='black', linewidth=0.7,
        boxstyle='round,pad=0.003', zorder=20, clip_on=False))

    ax_n = ax.inset_axes(
        [x - tamano/2, y - tamano*1.85, tamano, tamano*1.85],
        transform=ax.transAxes, zorder=21)
    ax_n.set_xlim(-1, 1)
    ax_n.set_ylim(-0.2, 2.2)
    ax_n.axis('off')

    ax_n.annotate('', xy=(0, 2.0), xytext=(0, 0),
                  arrowprops=dict(arrowstyle='->', lw=1.8, color='black'))
    ax_n.fill([-0.3, 0, 0], [1.4, 2.0, 1.5], color='black')
    ax_n.fill([0.3, 0, 0], [1.4, 2.0, 1.5], color='white',
              edgecolor='black', linewidth=0.5)
    ax_n.text(0, 2.15, 'N', ha='center', va='bottom',
              fontsize=int(round(11 * FONT_SCALE)), fontweight='bold', color='black')


def agregar_info_crs(ax, escala_texto):
    """Recuadro CRS + escala en esquina inferior izquierda."""
    texto = (f"SISTEMA DE REFERENCIA\nMAGNA SIRGAS\n"
             f"ORIGEN UNICO NACIONAL\nEPSG:{EPSG_SALIDA}\n\n"
             f"Escala aprox.: {escala_texto}")
    props = dict(boxstyle='round,pad=0.5', facecolor='white',
                 alpha=0.88, edgecolor='black', linewidth=0.8)
    ax.text(0.015, POS_Y_CRS_BOX, texto, transform=ax.transAxes,
            fontsize=int(round(7 * FONT_SCALE)), va='bottom', ha='left', bbox=props, zorder=18)


def calcular_intervalo_grilla(extent):
    """
    Calcula el intervalo de grilla = denominador_escala / 10.
    Ej.: escala 1:50 000  →  grilla 5 000 m
         escala 1:25 000  →  grilla 2 500 m
         escala 1: 5 000  →  grilla   500 m
    """
    if GRILLA_INTERVALO is not None:
        return GRILLA_INTERVALO

    # Calcular denominador de escala (ancho mapa en m / ancho figura en m_papel)
    ancho_m       = extent[1] - extent[0]          # metros
    ancho_fig_m   = (FIGSIZE[0] * 2.54) / 100.0    # pulgadas → metros papel
    escala_raw    = ancho_m / ancho_fig_m

    # Redondear escala a valor cerrado (misma lógica que calcular_escala_texto)
    magnitud = 10 ** int(np.log10(max(escala_raw, 1)))
    factores = [1, 2, 2.5, 5, 10]
    escala_cerrada = magnitud
    for f in factores:
        candidato = f * magnitud
        if abs(candidato - escala_raw) < abs(escala_cerrada - escala_raw):
            escala_cerrada = candidato

    # Intervalo = escala / 10, redondeado al múltiplo redondo más próximo
    intervalo_raw = escala_cerrada / 10.0
    opciones = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 25000, 50000]
    return min(opciones, key=lambda x: abs(x - intervalo_raw))


def calcular_escala_texto(extent_m, intervalo_g):
    """Escala cerrada aproximada alineada al intervalo de grilla."""
    ancho_m = extent_m[1] - extent_m[0]   # xmax - xmin
    ancho_fig_cm = FIGSIZE[0] * 2.54
    escala_raw = ancho_m / (ancho_fig_cm / 100)
    # Redondear a la escala cerrada mas proxima (1:5000, 1:10000, etc.)
    magnitud = 10 ** int(np.log10(escala_raw))
    factores = [1, 2, 2.5, 5, 10]
    escala_cerrada = magnitud
    for f in factores:
        candidato = f * magnitud
        if abs(candidato - escala_raw) < abs(escala_cerrada - escala_raw):
            escala_cerrada = candidato
    escala_cerrada = int(escala_cerrada)
    return f"1:{escala_cerrada:,}".replace(',', ' ')


def configurar_grilla(ax, extent, intervalo_g):
    """
    Configura ticks y grilla en metros EPSG:9377.
    - Lineas grises oscuras
    - Labels con prefijo N (Norte) en Y y sufijo E (Este) en X
    - extent = [xmin, xmax, ymin, ymax]
    """
    xticks = np.arange(
        np.ceil(extent[0] / intervalo_g) * intervalo_g,
        extent[1], intervalo_g)
    yticks = np.arange(
        np.ceil(extent[2] / intervalo_g) * intervalo_g,
        extent[3], intervalo_g)

    ax.set_xticks(xticks)
    ax.set_yticks(yticks)

    # Labels Este (X) — formato: 1 234 567 E
    ax.set_xticklabels(
        [f"{int(x):,}E".replace(',', ' ') for x in xticks],
        fontsize=GRILLA_FONTSIZE, rotation=0, color='black')

    # Labels Norte (Y) — acostados (rotation=90, paralelos al eje)
    ax.set_yticklabels(
        [f"N {int(y):,}".replace(',', ' ') for y in yticks],
        fontsize=GRILLA_FONTSIZE, color='black', rotation=90, va='center')

    ax.tick_params(axis='both', direction='in', length=4,
                   width=0.5, color='black')

    ax.grid(True, color=GRILLA_COLOR, linewidth=GRILLA_LINEWIDTH,
            alpha=GRILLA_ALPHA, linestyle='--', zorder=1)

    for spine in ax.spines.values():
        spine.set_edgecolor('black')
        spine.set_linewidth(1.2)

    # Etiquetas de ejes
    ax.set_xlabel('Este (m)  —  EPSG:9377', fontsize=int(round(7 * FONT_SCALE)), labelpad=4, color='#333333')
    ax.set_ylabel('Norte (m)  —  EPSG:9377', fontsize=int(round(7 * FONT_SCALE)), labelpad=4, color='#333333')

    print(f"  Grilla: intervalo {intervalo_g} m | "
          f"{len(xticks)} lineas E, {len(yticks)} lineas N")


# ==============================================================================
# 6. FUNCION PRINCIPAL
# ==============================================================================

def generar_mapa():
    print("=" * 65)
    print("MAPA SENTINEL-2 — PLANTILLA EXTENSIBLE")
    print(f"CRS SALIDA: EPSG:{EPSG_SALIDA}  |  Buffer: {BUFFER_M} m")
    print("=" * 65)

    os.makedirs(DIR_SALIDA, exist_ok=True)

    # ------------------------------------------------------------------
    # A. Capa de referencia → calcula extent del mapa
    # ------------------------------------------------------------------
    print(f"\n[1] Capa de referencia: {os.path.basename(SHP_REFERENCIA)}")
    gdf_ref = gpd.read_file(SHP_REFERENCIA)
    print(f"    CRS detectado: {gdf_ref.crs}  ({gdf_ref.crs.to_epsg()})")
    gdf_ref = reproyectar_gdf(gdf_ref)

    bounds = gdf_ref.total_bounds   # [xmin, ymin, xmax, ymax] en 9377
    buf = float(BUFFER_M)
    xmin = bounds[0] - buf
    ymin = bounds[1] - buf
    xmax = bounds[2] + buf
    ymax = bounds[3] + buf
    # Ajustar extent para que coincida con el aspecto ANCHO_PX / ALTO_PX
    # → el mapa llena el canvas sin distorsión; cambiar ANCHO/ALTO muestra más área
    ratio_fig = ANCHO_PX / ALTO_PX
    cx = (xmin + xmax) / 2
    cy = (ymin + ymax) / 2
    ancho_geo = xmax - xmin
    alto_geo  = ymax - ymin
    if ratio_fig > ancho_geo / alto_geo:   # figura más ancha → expandir E-W
        ancho_geo = alto_geo * ratio_fig
    else:                                   # figura más alta  → expandir N-S
        alto_geo  = ancho_geo / ratio_fig
    xmin = cx - ancho_geo / 2
    xmax = cx + ancho_geo / 2
    ymin = cy - alto_geo  / 2
    ymax = cy + alto_geo  / 2

    bbox_mapa = (xmin, ymin, xmax, ymax)
    extent    = [xmin, xmax, ymin, ymax]   # formato matplotlib [L, R, B, T]

    print(f"    Extent mapa EPSG:{EPSG_SALIDA}: "
          f"X[{xmin:.0f} – {xmax:.0f}]  Y[{ymin:.0f} – {ymax:.0f}]")

    # Calcular intervalo de grilla ahora (se reutiliza para la escala)
    intervalo_g = calcular_intervalo_grilla(extent)
    print(f"    Intervalo grilla: {intervalo_g} m")

    # ------------------------------------------------------------------
    # B. DEM de elevación (opcional)
    # ------------------------------------------------------------------
    dem_data = dem_extent = im_dem = None
    dem_vmin = dem_vmax = 0.0
    if ACTIVO_DEM:
        print(f"\n[2] DEM: {os.path.basename(RUTA_DEM)}")
        if os.path.exists(RUTA_DEM):
            dem_data, dem_extent, dem_vmin, dem_vmax, dem_ok = leer_raster_dem(
                RUTA_DEM, CRS_SALIDA, bbox_mapa)
            # Respetar vmin/vmax manuales si el usuario los definió
            if DEM_VMIN is not None:
                dem_vmin = DEM_VMIN
            if DEM_VMAX is not None:
                dem_vmax = DEM_VMAX
        else:
            print(f"    ADVERTENCIA: DEM no encontrado → omitido")
            dem_data = None
    else:
        print(f"\n[2] DEM desactivado (ACTIVO_DEM=0)")

    # ------------------------------------------------------------------
    # C. Raster de fondo Sentinel-2
    # ------------------------------------------------------------------
    print(f"\n[3] Raster de fondo: {os.path.basename(RUTA_RASTER_FONDO)}")
    if not ACTIVO_IMAGEN_SATELITAL:
        print(f"    Imagen satelital desactivada (ACTIVO_IMAGEN_SATELITAL=0) → fondo gris")
        raster_ok = False
    elif os.path.exists(RUTA_RASTER_FONDO):
        rgb_fondo, ext_raster, raster_ok = leer_raster_como_rgb(
            RUTA_RASTER_FONDO, BANDAS_RGB, CRS_SALIDA, bbox_mapa,
            PERCENTIL_LOW, PERCENTIL_HIGH, GAMMA_RASTER, BRILLO_RASTER, DESAT_RASTER)
    else:
        print(f"    ADVERTENCIA: raster no encontrado → fondo gris")
        raster_ok = False

    # ------------------------------------------------------------------
    # C. Leer y reproyectar todas las capas vectoriales
    # ------------------------------------------------------------------
    print(f"\n[3] Cargando capas vectoriales...")
    gdfs_capas = {}
    for capa in CAPAS_VECTOR:
        if not capa['visible']:
            print(f"    [ ] {capa['nombre']} (desactivada)")
            continue
        if not os.path.exists(capa['ruta']):
            print(f"    [!] {capa['nombre']}: ruta no encontrada → omitida")
            continue

        layer = capa.get('layer')   # None para SHP, nombre del FC para GDB
        nombre_display = (f"{os.path.basename(capa['ruta'])} [{layer}]"
                          if layer else os.path.basename(capa['ruta']))
        print(f"    [+] {capa['nombre']}: {nombre_display}")

        try:
            if layer:
                # GDB: leer una fila para conocer el CRS nativo antes de filtrar
                _muestra = gpd.read_file(capa['ruta'], layer=layer,
                                         engine='fiona', rows=1)
                native_crs = _muestra.crs
                # Si el WKT de la GDB no tiene AUTHORITY, to_epsg() devuelve None
                # pero las coordenadas ya están en 9377 → tratar como CRS_SALIDA
                if native_crs is not None and native_crs.to_epsg() is None:
                    if native_crs == CRS_SALIDA or str(native_crs) == str(CRS_SALIDA):
                        native_crs = CRS_SALIDA
                    else:
                        # Intentar matchear por WKT aproximado con EPSG:9377
                        try:
                            from pyproj import CRS as _CRS
                            native_crs = _CRS.from_user_input(native_crs.to_wkt())
                        except Exception:
                            pass
                # Transformar bbox al CRS nativo para que el filtro espacial sea correcto
                if native_crs and native_crs != CRS_SALIDA:
                    tf_inv = Transformer.from_crs(CRS_SALIDA, native_crs, always_xy=True)
                    x0, y0 = tf_inv.transform(bbox_mapa[0], bbox_mapa[1])
                    x1, y1 = tf_inv.transform(bbox_mapa[2], bbox_mapa[3])
                    bbox_filtro = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
                    print(f"        bbox transformado a CRS nativo ({native_crs.to_epsg()})")
                else:
                    bbox_filtro = bbox_mapa
                gdf = gpd.read_file(capa['ruta'], layer=layer,
                                    bbox=bbox_filtro, engine='fiona')
            else:
                gdf = gpd.read_file(capa['ruta'])
        except Exception as e:
            print(f"    [!] Error leyendo {capa['nombre']}: {e} → omitida")
            continue

        print(f"        CRS detectado: {gdf.crs}  "
              f"({gdf.crs.to_epsg() if gdf.crs else 'Sin CRS'}) | "
              f"{len(gdf)} features")
        gdf = reproyectar_gdf(gdf)   # → todos quedan en EPSG:9377
        gdfs_capas[capa['nombre']] = gdf

    # ------------------------------------------------------------------
    # D. Crear figura y dibujar
    # ------------------------------------------------------------------
    print(f"\n[4] Generando figura ({FIGSIZE[0]}x{FIGSIZE[1]} in, {DPI_SALIDA} dpi)...")
    fig, ax = plt.subplots(1, 1, figsize=FIGSIZE, dpi=100)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_facecolor('#2c3e50')   # fondo oscuro si el raster no cubre el area

    # ── Fondo raster con transparencia configurable ────────────────────
    if raster_ok:
        ax.imshow(rgb_fondo,
                  extent=[ext_raster[0], ext_raster[1],
                           ext_raster[2], ext_raster[3]],
                  aspect='auto', zorder=0, interpolation='bilinear',
                  origin='upper', alpha=ALPHA_RASTER)
        print(f"  Fondo Sentinel-2 dibujado (alpha={ALPHA_RASTER}).")
    else:
        ax.set_facecolor('#3d5a73')
        print("  Fondo gris (sin raster).")

    # Restaurar extent (imshow puede modificarlo)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])

    # ── DEM con hillshading (encima del Sentinel, debajo de vectores) ────
    im_dem = None   # ScalarMappable para la colorbar
    if ACTIVO_DEM and dem_data is not None:
        from matplotlib.colors import LightSource, Normalize
        norm_dem = Normalize(vmin=dem_vmin, vmax=dem_vmax)

        if DEM_HILLSHADE:
            ls  = LightSource(azdeg=DEM_AZIMUTH, altdeg=DEM_ALTITUD_LUZ)
            # shade() devuelve RGBA con hillshade integrado
            rgb_dem = ls.shade(
                dem_data, cmap=CMAP_ELEVACION, norm=norm_dem,
                vert_exag=DEM_EXAGERACION, blend_mode=DEM_BLEND_MODE)
            ax.imshow(rgb_dem,
                      extent=[dem_extent[0], dem_extent[1],
                               dem_extent[2], dem_extent[3]],
                      aspect='auto', zorder=1, interpolation='bilinear',
                      origin='upper', alpha=DEM_ALPHA)
            print(f"  DEM hillshade (az={DEM_AZIMUTH}°, alt={DEM_ALTITUD_LUZ}°, "
                  f"exag={DEM_EXAGERACION}, blend={DEM_BLEND_MODE}, "
                  f"alpha={DEM_ALPHA}, {dem_vmin:.0f}–{dem_vmax:.0f} m).")
        else:
            ax.imshow(dem_data,
                      extent=[dem_extent[0], dem_extent[1],
                               dem_extent[2], dem_extent[3]],
                      cmap=CMAP_ELEVACION, norm=norm_dem,
                      aspect='auto', zorder=1, interpolation='bilinear',
                      origin='upper', alpha=DEM_ALPHA)
            print(f"  DEM color plano (alpha={DEM_ALPHA}, "
                  f"{dem_vmin:.0f}–{dem_vmax:.0f} m).")

        # ScalarMappable para la colorbar (hillshade destruye el mappable directo)
        im_dem = plt.cm.ScalarMappable(cmap=CMAP_ELEVACION, norm=norm_dem)
        im_dem.set_array([])

        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])

    # ── Capas vectoriales ─────────────────────────────────────────────
    for capa in CAPAS_VECTOR:
        if not capa['visible']:
            continue
        nombre = capa['nombre']
        if nombre not in gdfs_capas:
            continue
        dibujar_capa_vector(ax, gdfs_capas[nombre], capa)
        print(f"  Capa '{nombre}' dibujada.")

    # Asegurar extent
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])

    # ── Label central ─────────────────────────────────────────────────
    if NOMBRE_LABEL:
        centroide = gdf_ref.dissolve().geometry.centroid.iloc[0]
        ax.text(centroide.x, centroide.y, NOMBRE_LABEL,
                fontsize=int(round(NOMBRE_LABEL_SIZE * FONT_SCALE)), fontweight='bold',
                color='white', ha='center', va='center',
                path_effects=[pe.withStroke(linewidth=3.5, foreground='black')],
                zorder=15)
        print(f"  Label '{NOMBRE_LABEL}' agregado.")

    # ── Flecha de norte ───────────────────────────────────────────────
    dibujar_flecha_norte(ax, x=0.95, y=0.965)

    # ── Escala grafica — valor coherente con intervalo de grilla ──────
    # Se usa el intervalo de grilla directamente como longitud de barra
    longitud_barra_km = intervalo_g / 1000.0

    scalebar = ScaleBar(
        1, units='m', location='lower left',
        fixed_value=longitud_barra_km, fixed_units='km',
        box_alpha=0.85, box_color='white',
        color='black', font_properties={'size': int(round(8 * FONT_SCALE))},
        scale_loc='bottom', border_pad=0.8,
        sep=3, pad=0.5, frameon=True)
    ax.add_artist(scalebar)
    print(f"  Escala grafica: {longitud_barra_km} km (= intervalo grilla {intervalo_g} m).")

    # ── Grilla de coordenadas Norte/Este en EPSG:9377 ─────────────────
    configurar_grilla(ax, extent, intervalo_g)

    # ── Recuadro CRS (subido para no solaparse con la escala) ─────────
    escala_txt = calcular_escala_texto(extent, intervalo_g)
    agregar_info_crs(ax, escala_txt)

    # ── Leyenda (solo capas visibles con label) ────────────────────────
    leyenda_items = []
    for capa in CAPAS_VECTOR:
        if not capa['visible'] or capa['nombre'] not in gdfs_capas:
            continue
        if not capa.get('label'):
            continue
        tipo = capa['tipo']
        if tipo == 'poligono':
            item = mpatches.Patch(
                facecolor=capa['facecolor'] if capa['facecolor'] != 'none' else (0,0,0,0),
                edgecolor=capa['edgecolor'],
                linewidth=1.2,
                label=capa['label'])
        elif tipo == 'linea':
            item = mlines.Line2D([], [], color=capa['edgecolor'],
                                 linewidth=1.5, label=capa['label'])
        else:  # punto
            item = mlines.Line2D([], [], marker='o',
                                 color=capa['facecolor'],
                                 markeredgecolor=capa['edgecolor'],
                                 markersize=6, linewidth=0,
                                 label=capa['label'])
        leyenda_items.append(item)

    if leyenda_items:
        legend = ax.legend(
            handles=leyenda_items,
            loc='lower right',
            fontsize=int(round(8 * FONT_SCALE)), frameon=True, fancybox=True,
            framealpha=0.88, edgecolor='black',
            title='Convenciones', title_fontsize=int(round(9 * FONT_SCALE)),
            borderpad=0.8, labelspacing=0.5)
        legend.get_frame().set_linewidth(0.8)
        legend.set_zorder(18)
        print("  Leyenda agregada.")

    # ── Regleta de elevación (lateral derecha, toda la altura del mapa) ──
    if ACTIVO_DEM and im_dem is not None:
        from mpl_toolkits.axes_grid1.inset_locator import inset_axes as _inset_axes
        ax_cbar = _inset_axes(
            ax,
            width='2.5%',    # ancho relativo al axes
            height='100%',   # igual de alta que el mapa
            loc='center right',
            bbox_to_anchor=(0.02, 0.0, 1.0, 1.0),
            bbox_transform=ax.transAxes,
            borderpad=0)
        cbar = fig.colorbar(im_dem, cax=ax_cbar, orientation='vertical')
        cbar.set_label(DEM_LABEL, fontsize=8, rotation=270, labelpad=14,
                       color='black')
        cbar.ax.tick_params(labelsize=7, colors='black')
        for spine in cbar.ax.spines.values():
            spine.set_edgecolor('gray')
        print(f"  Regleta DEM agregada (lado derecho, altura completa).")

    # ------------------------------------------------------------------
    # E. Guardar
    # ------------------------------------------------------------------
    print(f"\n[5] Guardando: {RUTA_SALIDA}")
    plt.tight_layout(pad=0.1)   # ajusta el axes para llenar la figura respetando labels
    plt.savefig(RUTA_SALIDA, dpi=DPI_SALIDA,
                facecolor='white', edgecolor='none')
    plt.close()
    print(f"    Guardado OK. DPI: {DPI_SALIDA}")


# ==============================================================================
# 7. DIAGNOSTICO DE CRS
# ==============================================================================

def validar_crs_capas():
    """
    Imprime el CRS de todas las capas (rasters y vectoriales) y avisa si
    alguna no tiene CRS definido o si hay diferencias entre capas que pueden
    causar desplazamientos en el mapa.
    """
    sep = "=" * 65
    print(f"\n{sep}")
    print("DIAGNOSTICO DE SISTEMAS DE REFERENCIA (CRS)")
    print(sep)

    # ── Rasters ──────────────────────────────────────────────────────────────
    rasters = [
        ("Imagen Sentinel-2 (fondo)", RUTA_RASTER_FONDO),
        ("DEM",                        RUTA_DEM),
    ]
    print("\n  RASTERS:")
    for nombre, ruta in rasters:
        if not os.path.exists(ruta):
            print(f"    [?] {nombre}: archivo no encontrado ({ruta})")
            continue
        try:
            with rasterio.open(ruta) as src:
                crs = src.crs
                epsg = crs.to_epsg() if crs else None
                bounds = src.bounds
                print(f"    [+] {nombre}")
                print(f"        CRS   : {crs}")
                print(f"        EPSG  : {epsg}")
                print(f"        Bandas: {src.count}  |  Res: {src.res}")
                print(f"        Bounds: X[{bounds.left:.4f} – {bounds.right:.4f}]"
                      f"  Y[{bounds.bottom:.4f} – {bounds.top:.4f}]")
                if epsg != EPSG_SALIDA:
                    print(f"        >> DIFERENTE a EPSG:{EPSG_SALIDA} — se reproyectara al vuelo")
                if crs is None:
                    print(f"        >> SIN CRS — puede causar desplazamiento!")
        except Exception as e:
            print(f"    [!] {nombre}: error leyendo raster — {e}")

    # ── Vectoriales ───────────────────────────────────────────────────────────
    capas_vec = [
        ("Referencia (buffer/zoom)", SHP_REFERENCIA, None),
    ]
    for c in CAPAS_VECTOR:
        capas_vec.append((c['nombre'], c['ruta'], c.get('layer')))

    print("\n  VECTORIALES:")
    epsgs_encontrados = set()
    for nombre, ruta, layer in capas_vec:
        if not os.path.exists(ruta):
            print(f"    [?] {nombre}: archivo no encontrado")
            continue
        try:
            kwargs = dict(rows=5)
            if layer:
                kwargs['layer'] = layer
            gdf = gpd.read_file(ruta, **kwargs)
            crs = gdf.crs
            epsg = crs.to_epsg() if crs else None
            bounds = gdf.total_bounds  # [xmin, ymin, xmax, ymax]

            estado = "OK" if epsg == EPSG_SALIDA else (
                "SIN CRS — RIESGO DE DESPLAZAMIENTO!" if crs is None
                else f"DIFERENTE a EPSG:{EPSG_SALIDA} — se reproyectara"
            )
            print(f"    [+] {nombre}" + (f" [{layer}]" if layer else ""))
            print(f"        CRS   : {crs}")
            print(f"        EPSG  : {epsg}  →  {estado}")
            print(f"        Bounds: X[{bounds[0]:.4f} – {bounds[2]:.4f}]"
                  f"  Y[{bounds[1]:.4f} – {bounds[3]:.4f}]")
            print(f"        Geoms : {len(gdf)} features (muestra)")

            if epsg:
                epsgs_encontrados.add(epsg)

            # Alerta si los bounds parecen geográficos (lon/lat) pero el EPSG
            # sugiere proyectado o viceversa
            if epsg in (4326, 4686, 4258, 4269):  # geográficos comunes
                if abs(bounds[0]) > 180 or abs(bounds[2]) > 180:
                    print(f"        >> ALERTA: coordenadas fuera de rango lat/lon!")
            elif epsg == EPSG_SALIDA:  # proyectado Colombia
                if -180 <= bounds[0] <= 180 and -90 <= bounds[1] <= 90:
                    print(f"        >> ALERTA: bounds parecen geograficos pero EPSG es proyectado!")

        except Exception as e:
            print(f"    [!] {nombre}: error leyendo — {e}")

    # ── Resumen ───────────────────────────────────────────────────────────────
    print(f"\n  RESUMEN:")
    print(f"    CRS de salida del mapa : EPSG:{EPSG_SALIDA}")
    if epsgs_encontrados:
        print(f"    EPSGs encontrados      : {sorted(epsgs_encontrados)}")
        diferentes = epsgs_encontrados - {EPSG_SALIDA}
        if diferentes:
            print(f"    EPSGs distintos al destino: {sorted(diferentes)}")
            print(f"    >> Las capas con EPSG diferente se reproyectan automaticamente.")
            print(f"    >> Si hay desplazamiento, verificar que el CRS reportado")
            print(f"       sea el REAL del archivo (puede estar mal asignado).")
        else:
            print(f"    Todas las capas ya estan en EPSG:{EPSG_SALIDA} — no hay riesgo de desplazamiento por reproyeccion.")
    print(sep + "\n")


# ==============================================================================
# 8. EJECUCION
# ==============================================================================
if __name__ == "__main__":

    errores = []
    if not os.path.exists(SHP_REFERENCIA):
        errores.append(f"Capa de referencia no encontrada:\n  {SHP_REFERENCIA}")
    if not os.path.exists(RUTA_RASTER_FONDO):
        print(f"ADVERTENCIA: raster de fondo no encontrado:\n  {RUTA_RASTER_FONDO}")
        print("  El mapa se generara con fondo gris.\n")

    if errores:
        for e in errores:
            print(f"ERROR: {e}")
        exit(1)

    # Ejecutar diagnostico antes de generar el mapa
    validar_crs_capas()

    generar_mapa()

    print("\n" + "=" * 65)
    print("PROCESO COMPLETADO")
    print(f"Salida: {RUTA_SALIDA}")
    print("=" * 65)
