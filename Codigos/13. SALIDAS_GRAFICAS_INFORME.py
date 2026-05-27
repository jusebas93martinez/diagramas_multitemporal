# ==============================================================================
# SALIDAS GRÁFICAS PARA INFORME — SCRIPT UNIFICADO
# ==============================================================================
# Genera 4 tipos de visualizaciones:
#   1. Mosaicos de imágenes IR (falso color infrarrojo)
#   2. Mosaicos de índice MNDWI
#   3. Mapa de frecuencia de agua (MNDWI > umbral)
#   4. Mapa de clasificación de agua SAR
#
# Todas las salidas incluyen:
#   - Formato horizontal (más ancho que alto) para informe
#   - Flecha de norte gráfica
#   - Grilla de coordenadas en EPSG:9377 (CTM-12, Origen Nacional Colombia)
#   - Convenciones / leyenda
# ==============================================================================

import os
import math
import re
import numpy as np
import rasterio
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.patches import Patch
from matplotlib.lines import Line2D
from rasterio.plot import plotting_extent
from pyproj import Transformer

# ==============================================================================
#  ████  CONFIGURACIÓN — EDITAR SOLO ESTA SECCIÓN  ████
# ==============================================================================

# --- CARPETA DE SALIDA (todos los PNG se guardan aquí) ---
RUTA_SALIDA = r"C:\Users\sebas\OneDrive\Documentos\SYNC\ANT\2026-1\20260423\LA CHIQUITA\SALIDAS GRAFICAS\2"

# --- POLÍGONO SHAPEFILE (común a todas las secciones) ---
RUTA_SHP = r"C:\Users\sebas\OneDrive\Documentos\SYNC\ANT\2026-1\20260423\LA CHIQUITA\HIDROLOGICO\HIDROLOGICO.shp"

# ─────────────────────────────────────────────────────────
# 1) MOSAICOS IR (falso color infrarrojo)
# ─────────────────────────────────────────────────────────
IR_RUTA_CARPETA = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MEJORES_POR_AÑO\IR"
IR_ORDEN_BANDAS = "NIR_RED_GREEN"   # "NIR_RED_GREEN" o "RGB"
IR_ESTILO_BORDE = {
    'color_glow':  '#00FFFF',   # Cyan brillante (complementario al rojo)
    'color_borde': '#F7E707',   # Amarillo para definición
    'ancho_glow':  4.5,
    'ancho_borde': 1.2,
    'alpha_glow':  0.85,
}

# ─────────────────────────────────────────────────────────
# 2) MOSAICOS MNDWI
# ─────────────────────────────────────────────────────────
MNDWI_RUTA_CARPETA = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MEJORES_POR_AÑO\MNDWI"
MNDWI_CMAP         = "BrBG"
MNDWI_VMIN         = -1.0
MNDWI_VMAX         =  1.0
MNDWI_ESTILO_BORDE = {
    'color_glow':  '#9D0D9DD3',  # Magenta (contrasta con marrón y azul)
    'color_borde': '#000000',    # Negro para definición
    'ancho_glow':  4.5,
    'ancho_borde': 1.2,
    'alpha_glow':  0.85,
}

# ─────────────────────────────────────────────────────────
# 3) MAPA FRECUENCIA DE AGUA
# ─────────────────────────────────────────────────────────
FREQ_RUTA_TIF  = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IMAGENES_MOSAICO\MEJORES_POR_AÑO\SALIDAS_humedo_MNDWI\Frecuencia_Total_MNDWI.tif"
FREQ_CMAP      = "GnBu"
FREQ_TITULO    = "Frecuencia de Agua (MNDWI > 0.10)"
FREQ_LABEL_CB  = "Número de veces con MNDWI > 0.10"

# ─────────────────────────────────────────────────────────
# 4) CLASIFICACIÓN DE AGUA SAR
# ─────────────────────────────────────────────────────────
SAR_RUTA_BINARIO  = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\SAR\S1_ASCENDING_2024_09_COMPOSITE_MERGE.tif"
SAR_NOMBRE_RASTER = "S1_AGUA_BINARIO_2019_10.tif"
SAR_UMBRAL_DB     = -14

# ─────────────────────────────────────────────────────────
# Buffer visual alrededor del shapefile (en metros)
# Controla cuánto contexto se ve fuera del polígono en TODOS los mapas.
# 0 = encuadre exacto al shapefile | 500 = 500 m extra por lado
# ─────────────────────────────────────────────────────────
BUFFER_M = 600   # metros

# ─────────────────────────────────────────────────────────
# Parámetros de mosaico (aplica a IR y MNDWI)
# Formato HORIZONTAL: ancho > alto por celda
# ─────────────────────────────────────────────────────────
MOSAICO_COLUMNAS    = 5
MOSAICO_FILAS       = 2
MOSAICO_ANCHO_CELDA = 3.2   # pulgadas por celda (horizontal)
MOSAICO_ALTO_CELDA  = 2.5

# ─────────────────────────────────────────────────────────
# Grilla de coordenadas EPSG:9377 (CTM-12 Origen Nacional)
# ─────────────────────────────────────────────────────────
GRILLA_CRS          = "EPSG:9377"
GRILLA_NUM_LINEAS   = 5      # número aprox. de líneas por eje
GRILLA_ALPHA        = 0.30   # transparencia de líneas
GRILLA_COLOR        = '#555555'
GRILLA_LW           = 0.4
GRILLA_FONT_SIZE    = 5      # tamaño de etiquetas en mosaicos
GRILLA_FONT_SIZE_XL = 8      # tamaño de etiquetas en mapas individuales

# ==============================================================================
#  FIN DE CONFIGURACIÓN
# ==============================================================================

os.makedirs(RUTA_SALIDA, exist_ok=True)


# ==============================================================================
# FUNCIONES COMPARTIDAS
# ==============================================================================

def extraer_mision_año(nombre_archivo):
    nombre_base = os.path.splitext(nombre_archivo)[0]
    for patron in [
        r'^(LC09|LC08|LE07|LT05|LT04|S2)_(\d{4})',
        r'mosaico_(LC09|LC08|LE07|LT05|LT04|S2)_(\d{4})',
    ]:
        m = re.search(patron, nombre_base)
        if m:
            return (m.group(1), int(m.group(2)))
    m = re.search(r'(\d{4})', nombre_base)
    if m:
        año = int(m.group(1))
        for codigo in ['LC09', 'LC08', 'LE07', 'LT05', 'LT04', 'S2']:
            if codigo in nombre_base.upper():
                return (codigo, año)
        if 'SENTINEL' in nombre_base.upper():
            return ('S2', año)
        return ('UNKNOWN', año)
    return ('UNKNOWN', 9999)


def obtener_nombre_mision_completo(codigo):
    return {
        'LC09': 'Landsat 9', 'LC08': 'Landsat 8',
        'LE07': 'Landsat 7', 'LT05': 'Landsat 5',
        'LT04': 'Landsat 4', 'S2':   'Sentinel-2',
        'UNKNOWN': 'Desconocida',
    }.get(codigo, codigo)


def dibujar_borde_glow(ax, geometria, estilo):
    geometria.boundary.plot(
        ax=ax, edgecolor=estilo['color_glow'],
        linewidth=estilo['ancho_glow'], alpha=estilo['alpha_glow'], zorder=2
    )
    geometria.boundary.plot(
        ax=ax, edgecolor=estilo['color_borde'],
        linewidth=estilo['ancho_borde'], alpha=1.0, zorder=3
    )


def agregar_titulo_panel(ax, mision_completa, año):
    ax.text(
        0.5, 0.97, f"{mision_completa} - {año}",
        transform=ax.transAxes, ha='center', va='top',
        fontsize=9, fontweight='bold', color='white',
        bbox=dict(facecolor=(0, 0, 0, 0.55), edgecolor='none', boxstyle='round,pad=0.25'),
        clip_on=True, zorder=5
    )


def aplicar_buffer(ax, shp_proj):
    """Ajusta los límites del eje al bbox del shapefile + BUFFER_M."""
    minx, miny, maxx, maxy = shp_proj.total_bounds
    ax.set_xlim(minx - BUFFER_M, maxx + BUFFER_M)
    ax.set_ylim(miny - BUFFER_M, maxy + BUFFER_M)


def aplicar_buffer_mosaico(ax, shp_proj):
    """
    Ajusta los límites del eje al bbox del shapefile + BUFFER_M,
    expandiendo un eje para que la proporción de datos coincida
    con la proporción de la celda del mosaico (ANCHO/ALTO).
    Esto elimina espacios en blanco causados por set_aspect('equal').
    """
    minx, miny, maxx, maxy = shp_proj.total_bounds
    x0, x1 = minx - BUFFER_M, maxx + BUFFER_M
    y0, y1 = miny - BUFFER_M, maxy + BUFFER_M
    dx = x1 - x0
    dy = y1 - y0
    ratio_celda = MOSAICO_ANCHO_CELDA / MOSAICO_ALTO_CELDA  # ratio objetivo
    ratio_datos = dx / dy
    if ratio_datos < ratio_celda:
        # Dato más alto que la celda → expandir X
        nuevo_dx = dy * ratio_celda
        cx = (x0 + x1) / 2
        x0 = cx - nuevo_dx / 2
        x1 = cx + nuevo_dx / 2
    else:
        # Dato más ancho que la celda → expandir Y
        nuevo_dy = dx / ratio_celda
        cy = (y0 + y1) / 2
        y0 = cy - nuevo_dy / 2
        y1 = cy + nuevo_dy / 2
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def aplicar_buffer_horizontal(ax, shp_proj, ratio_min=1.4):
    """
    Ajusta los límites del eje al bbox del shapefile + BUFFER_M,
    expandiendo el eje X si es necesario para garantizar formato horizontal.
    ratio_min: ancho/alto mínimo del viewport (1.4 = 40% más ancho que alto).
    """
    minx, miny, maxx, maxy = shp_proj.total_bounds
    x0, x1 = minx - BUFFER_M, maxx + BUFFER_M
    y0, y1 = miny - BUFFER_M, maxy + BUFFER_M
    dx = x1 - x0
    dy = y1 - y0
    if dx / dy < ratio_min:
        # Expandir horizontalmente para alcanzar el ratio deseado
        nuevo_dx = dy * ratio_min
        cx = (x0 + x1) / 2
        x0 = cx - nuevo_dx / 2
        x1 = cx + nuevo_dx / 2
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)


def listar_y_ordenar_tifs(ruta_carpeta, etiqueta=""):
    archivos = [f for f in os.listdir(ruta_carpeta) if f.lower().endswith(".tif")]
    info = [{'nombre': f, **dict(zip(('mision', 'año'), extraer_mision_año(f)))}
            for f in archivos]
    info.sort(key=lambda x: (x['año'], x['mision']))
    print(f"\n{'='*70}")
    print(f"ARCHIVOS {etiqueta} ({len(info)} imágenes):")
    print(f"{'='*70}")
    for d in info:
        print(f"  {d['año']} | {d['mision']:6s} ({obtener_nombre_mision_completo(d['mision']):12s}) | {d['nombre']}")
    print(f"{'='*70}")
    return info


# ==============================================================================
# FUNCIONES DE NORTE GRÁFICO Y GRILLA EPSG:9377
# ==============================================================================

def dibujar_norte(ax, x=0.96, y=0.95, tamaño=0.07):
    """Dibuja una flecha de norte gráfica sobre el eje."""
    ax.annotate(
        '', xy=(x, y), xytext=(x, y - tamaño),
        xycoords='axes fraction', textcoords='axes fraction',
        arrowprops=dict(arrowstyle='->', lw=1.8, color='black'),
        zorder=12
    )
    ax.text(
        x, y + 0.015, 'N', transform=ax.transAxes,
        ha='center', va='bottom', fontsize=10, fontweight='bold',
        color='black', zorder=12,
        bbox=dict(facecolor='white', edgecolor='black',
                  boxstyle='round,pad=0.15', alpha=0.9, linewidth=0.6)
    )


def dibujar_norte_pequeño(ax, x=0.93, y=0.93, tamaño=0.05):
    """Norte compacto para paneles de mosaico."""
    ax.annotate(
        '', xy=(x, y), xytext=(x, y - tamaño),
        xycoords='axes fraction', textcoords='axes fraction',
        arrowprops=dict(arrowstyle='->', lw=1.2, color='black'),
        zorder=12
    )
    ax.text(
        x, y + 0.01, 'N', transform=ax.transAxes,
        ha='center', va='bottom', fontsize=7, fontweight='bold',
        color='black', zorder=12,
        bbox=dict(facecolor='white', edgecolor='black',
                  boxstyle='round,pad=0.1', alpha=0.9, linewidth=0.5)
    )


def _intervalo_bonito(rango, num_lineas=5):
    """Calcula un intervalo redondeado para la grilla."""
    if rango <= 0:
        return 1.0
    intervalo = rango / num_lineas
    magnitud = 10 ** math.floor(math.log10(intervalo))
    r = intervalo / magnitud
    if r <= 1.5:
        return magnitud
    elif r <= 3.5:
        return 2 * magnitud
    elif r <= 7.5:
        return 5 * magnitud
    return 10 * magnitud


def dibujar_grilla_9377(ax, crs_origen, font_size=None, mostrar_etiquetas=True):
    """
    Dibuja grilla de coordenadas en EPSG:9377 (CTM-12) sobre el eje.
    Transforma las líneas de grilla desde EPSG:9377 al CRS del raster.
    La densidad se calcula proporcionalmente a la escala de la imagen.
    """
    if font_size is None:
        font_size = GRILLA_FONT_SIZE

    try:
        to_9377 = Transformer.from_crs(crs_origen, GRILLA_CRS, always_xy=True)
        from_9377 = Transformer.from_crs(GRILLA_CRS, crs_origen, always_xy=True)
    except Exception as e:
        print(f"  ⚠ No se pudo crear transformer a EPSG:9377: {e}")
        return

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()

    corners_x = [xlim[0], xlim[1], xlim[0], xlim[1]]
    corners_y = [ylim[0], ylim[0], ylim[1], ylim[1]]
    cx9, cy9 = to_9377.transform(corners_x, corners_y)

    x_min9, x_max9 = min(cx9), max(cx9)
    y_min9, y_max9 = min(cy9), max(cy9)

    dx = _intervalo_bonito(x_max9 - x_min9, GRILLA_NUM_LINEAS)
    dy = _intervalo_bonito(y_max9 - y_min9, GRILLA_NUM_LINEAS)

    xs = np.arange(math.floor(x_min9 / dx) * dx, x_max9 + dx, dx)
    ys = np.arange(math.floor(y_min9 / dy) * dy, y_max9 + dy, dy)

    n_pts = 100
    stroke = [pe.withStroke(linewidth=2, foreground='white')]

    for xg in xs:
        yy = np.linspace(y_min9 - dy, y_max9 + dy, n_pts)
        xx = np.full_like(yy, xg)
        px, py = from_9377.transform(xx, yy)
        ax.plot(px, py, color=GRILLA_COLOR, linewidth=GRILLA_LW,
                alpha=GRILLA_ALPHA, linestyle='--', zorder=1)
        if mostrar_etiquetas:
            lx, ly = from_9377.transform([xg], [y_min9])
            if xlim[0] <= lx[0] <= xlim[1]:
                ax.text(lx[0], ylim[0] + (ylim[1] - ylim[0]) * 0.01,
                        f'{xg:,.0f}',
                        fontsize=font_size, ha='center', va='bottom',
                        color=GRILLA_COLOR, alpha=0.8, rotation=90,
                        zorder=10, path_effects=stroke)

    for yg in ys:
        xx = np.linspace(x_min9 - dx, x_max9 + dx, n_pts)
        yy = np.full_like(xx, yg)
        px, py = from_9377.transform(xx, yy)
        ax.plot(px, py, color=GRILLA_COLOR, linewidth=GRILLA_LW,
                alpha=GRILLA_ALPHA, linestyle='--', zorder=1)
        if mostrar_etiquetas:
            lx, ly = from_9377.transform([x_min9], [yg])
            if ylim[0] <= ly[0] <= ylim[1]:
                ax.text(xlim[0] + (xlim[1] - xlim[0]) * 0.01, ly[0],
                        f'{yg:,.0f}',
                        fontsize=font_size, ha='left', va='center',
                        color=GRILLA_COLOR, alpha=0.8,
                        zorder=10, path_effects=stroke)

    if mostrar_etiquetas:
        ax.text(0.99, 0.01, 'Coord. EPSG:9377\n(CTM-12 Origen Nacional)',
                transform=ax.transAxes, fontsize=max(font_size - 1, 4),
                ha='right', va='bottom', color=GRILLA_COLOR, alpha=0.7,
                fontstyle='italic', zorder=10,
                bbox=dict(facecolor='white', alpha=0.7, edgecolor='none',
                          boxstyle='round,pad=0.2'))


# ==============================================================================
# 1) MOSAICOS IR
# ==============================================================================

def percent_clip(arr, p_low=2, p_high=98):
    data = arr.compressed() if isinstance(arr, np.ma.MaskedArray) else arr[np.isfinite(arr)]
    if data.size == 0:
        return np.zeros_like(arr, dtype=np.float32)
    lo, hi = np.percentile(data, p_low), np.percentile(data, p_high)
    if hi <= lo:
        hi = lo + 1e-6
    return np.clip((arr.astype(np.float32) - lo) / (hi - lo), 0, 1)


def leer_rgb(ruta_tif, shp):
    with rasterio.open(ruta_tif) as src:
        bandas = [src.read(i, masked=True) for i in (1, 2, 3)]
        extent = plotting_extent(src)
        crs = src.crs
        canales = [percent_clip(b) for b in bandas]
        canales = [c.filled(0) if np.ma.isMaskedArray(c) else c for c in canales]
        rgb = np.stack(canales, axis=-1).astype(np.float32)
        shp_proj = shp.to_crs(src.crs)
    return rgb, extent, shp_proj, crs


def generar_mosaicos_ir():
    print("\n" + "█"*70)
    print("  1/4  MOSAICOS IR")
    print("█"*70)

    shp = gpd.read_file(RUTA_SHP)
    info_archivos = listar_y_ordenar_tifs(IR_RUTA_CARPETA, "IR")
    total = len(info_archivos)
    por_mosaico = MOSAICO_FILAS * MOSAICO_COLUMNAS
    num_mosaicos = math.ceil(total / por_mosaico)

    for i in range(num_mosaicos):
        grupo = info_archivos[i * por_mosaico: (i + 1) * por_mosaico]
        fig, axes = plt.subplots(
            MOSAICO_FILAS, MOSAICO_COLUMNAS,
            figsize=(MOSAICO_ANCHO_CELDA * MOSAICO_COLUMNAS,
                     MOSAICO_ALTO_CELDA * MOSAICO_FILAS)
        )
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.06, top=0.92,
                            wspace=0.02, hspace=0.03)
        axes = axes.flatten()

        for idx, info in enumerate(grupo):
            ax = axes[idx]
            try:
                rgb, extent, shp_proj, crs = leer_rgb(
                    os.path.join(IR_RUTA_CARPETA, info['nombre']), shp)
                ax.imshow(rgb, extent=extent, interpolation="nearest")
                dibujar_borde_glow(ax, shp_proj, IR_ESTILO_BORDE)
                aplicar_buffer_mosaico(ax, shp_proj)
                dibujar_grilla_9377(ax, crs, font_size=GRILLA_FONT_SIZE,
                                    mostrar_etiquetas=False)
                dibujar_norte_pequeño(ax)
                agregar_titulo_panel(ax, obtener_nombre_mision_completo(info['mision']),
                                     info['año'])
                ax.set_aspect('equal')
                ax.axis("off")
            except Exception as e:
                ax.text(0.5, 0.5, f"Error\n{info['nombre']}\n{e}",
                        ha='center', va='center', fontsize=8)
                ax.axis("off")

        for ax in axes[len(grupo):]:
            ax.axis("off")

        # Leyenda IR
        leyenda_ir = [
            Line2D([0], [0], color=IR_ESTILO_BORDE['color_borde'], linewidth=2,
                   label='Límite del predio'),
            Patch(facecolor='red', alpha=0.7, label='Banda NIR'),
            Patch(facecolor='green', alpha=0.7, label='Banda RED'),
            Patch(facecolor='blue', alpha=0.7, label='Banda GREEN'),
        ]
        fig.legend(handles=leyenda_ir, loc='lower center', ncol=4, fontsize=8,
                   framealpha=0.95, edgecolor='gray',
                   bbox_to_anchor=(0.5, 0.005))

        salida = os.path.join(RUTA_SALIDA, f"mosaico_IR_{i + 1:02d}.png")
        fig.savefig(salida, dpi=300, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        print(f"  ✓ IR {i + 1}/{num_mosaicos}: {salida}")

    print(f"  Total IR: {total} imágenes | {num_mosaicos} mosaico(s)")


# ==============================================================================
# 2) MOSAICOS MNDWI
# ==============================================================================

def generar_mosaicos_mndwi():
    print("\n" + "█"*70)
    print("  2/4  MOSAICOS MNDWI")
    print("█"*70)

    shp = gpd.read_file(RUTA_SHP)
    info_archivos = listar_y_ordenar_tifs(MNDWI_RUTA_CARPETA, "MNDWI")
    total = len(info_archivos)
    por_mosaico = MOSAICO_FILAS * MOSAICO_COLUMNAS
    num_mosaicos = math.ceil(total / por_mosaico)

    for i in range(num_mosaicos):
        grupo = info_archivos[i * por_mosaico: (i + 1) * por_mosaico]
        fig, axes = plt.subplots(
            MOSAICO_FILAS, MOSAICO_COLUMNAS,
            figsize=(MOSAICO_ANCHO_CELDA * MOSAICO_COLUMNAS,
                     MOSAICO_ALTO_CELDA * MOSAICO_FILAS)
        )
        fig.subplots_adjust(left=0.01, right=0.99, bottom=0.10, top=0.92,
                            wspace=0.02, hspace=0.03)
        axes = axes.flatten()
        im_last = None

        for idx, info in enumerate(grupo):
            ax = axes[idx]
            try:
                with rasterio.open(os.path.join(MNDWI_RUTA_CARPETA, info['nombre'])) as src:
                    banda = src.read(1).astype(np.float32)
                    if src.nodata is not None:
                        banda[banda == src.nodata] = np.nan
                    banda    = np.clip(banda, MNDWI_VMIN, MNDWI_VMAX)
                    extent   = plotting_extent(src)
                    crs      = src.crs
                    shp_proj = shp.to_crs(src.crs)

                im_last = ax.imshow(banda, cmap=MNDWI_CMAP,
                                    vmin=MNDWI_VMIN, vmax=MNDWI_VMAX,
                                    extent=extent, interpolation='nearest')
                dibujar_borde_glow(ax, shp_proj, MNDWI_ESTILO_BORDE)
                aplicar_buffer_mosaico(ax, shp_proj)
                dibujar_grilla_9377(ax, crs, font_size=GRILLA_FONT_SIZE,
                                    mostrar_etiquetas=False)
                dibujar_norte_pequeño(ax)
                agregar_titulo_panel(ax, obtener_nombre_mision_completo(info['mision']),
                                     info['año'])
                ax.set_aspect('equal')
                ax.axis("off")
            except Exception as e:
                ax.text(0.5, 0.5, f"Error\n{info['nombre']}\n{e}",
                        ha='center', va='center', fontsize=8, color='red')
                ax.axis("off")
                print(f"  ⚠ Error {info['nombre']}: {e}")

        for ax in axes[len(grupo):]:
            ax.axis("off")

        if im_last is not None:
            cbar_ax = fig.add_axes([0.1, 0.05, 0.8, 0.018])
            cbar = fig.colorbar(im_last, cax=cbar_ax, orientation="horizontal")
            cbar.set_label("MNDWI (Índice de Agua)", fontsize=10, fontweight='bold')
            cbar.ax.tick_params(labelsize=9)
            cbar.ax.text(-0.9, -1.8, 'Tierra/Vegetación',
                         ha='left', va='top', fontsize=8, fontweight='bold', color='#8B4513')
            cbar.ax.text(0.9, -1.8, 'Agua',
                         ha='right', va='top', fontsize=8, fontweight='bold', color='#0066CC')

        # Leyenda MNDWI — al lado derecho del colorbar para evitar solapamiento
        leyenda_mndwi = [
            Line2D([0], [0], color=MNDWI_ESTILO_BORDE['color_borde'], linewidth=2,
                   label='Límite predio'),
            Patch(facecolor='#8B4513', alpha=0.7, label='Tierra/Veg. (MNDWI<0)'),
            Patch(facecolor='#0066CC', alpha=0.7, label='Agua (MNDWI>0)'),
        ]
        fig.legend(handles=leyenda_mndwi, loc='lower right', ncol=1, fontsize=6,
                   framealpha=0.95, edgecolor='gray',
                   bbox_to_anchor=(0.99, 0.005))

        salida = os.path.join(RUTA_SALIDA, f"mosaico_MNDWI_{i + 1:02d}.png")
        fig.savefig(salida, dpi=300, facecolor='white', bbox_inches='tight')
        plt.close(fig)
        print(f"  ✓ MNDWI {i + 1}/{num_mosaicos}: {salida}")

    print(f"  Total MNDWI: {total} imágenes | {num_mosaicos} mosaico(s)")


# ==============================================================================
# 3) MAPA FRECUENCIA DE AGUA
# ==============================================================================

def generar_mapa_frecuencia():
    print("\n" + "█"*70)
    print("  3/4  MAPA FRECUENCIA DE AGUA")
    print("█"*70)

    with rasterio.open(FREQ_RUTA_TIF) as src:
        data      = src.read(1).astype(np.float32)
        crs       = src.crs
        extent    = plotting_extent(src)
        nodata    = src.nodata

    if nodata is not None:
        data = np.where(data == nodata, np.nan, data)

    vmax = float(np.nanmax(data)) if np.isfinite(np.nanmax(data)) else 1.0

    shp_proj = gpd.read_file(RUTA_SHP).to_crs(crs)

    # Calcular viewport horizontal real
    minx, miny, maxx, maxy = shp_proj.total_bounds
    x0, x1 = minx - BUFFER_M, maxx + BUFFER_M
    y0, y1 = miny - BUFFER_M, maxy + BUFFER_M
    dx = x1 - x0
    dy = y1 - y0
    ratio_min = 1.5
    if dx / dy < ratio_min:
        nuevo_dx = dy * ratio_min
        cx = (x0 + x1) / 2
        x0 = cx - nuevo_dx / 2
        x1 = cx + nuevo_dx / 2
    ratio = (x1 - x0) / (y1 - y0)
    fig_w = max(10.0, min(16.0, 12.0 * ratio))
    fig_h = fig_w / ratio

    fig, ax = plt.subplots(figsize=(fig_w, fig_h))
    img = ax.imshow(data, cmap=FREQ_CMAP, vmin=0.0, vmax=vmax, extent=extent)
    shp_proj.boundary.plot(ax=ax, edgecolor='white', linewidth=1.8, zorder=3)
    shp_proj.boundary.plot(ax=ax, edgecolor='black', linewidth=0.9, zorder=4)
    aplicar_buffer_horizontal(ax, shp_proj, ratio_min=ratio_min)

    # Grilla EPSG:9377 y norte
    dibujar_grilla_9377(ax, crs, font_size=GRILLA_FONT_SIZE_XL, mostrar_etiquetas=True)
    dibujar_norte(ax, x=0.96, y=0.95)

    ax.set_aspect('equal')
    ax.set_title(FREQ_TITULO, fontsize=14, fontweight="bold", pad=8)
    ax.axis("off")

    cbar = fig.colorbar(img, ax=ax, orientation='horizontal',
                        fraction=0.046, pad=0.06, aspect=40)
    cbar.set_label(FREQ_LABEL_CB, fontsize=12)
    cbar.ax.tick_params(labelsize=10)

    # Convenciones
    leyenda = [
        Line2D([0], [0], color='black', linewidth=1.5, label='Límite del predio'),
        Patch(facecolor='#d4eac7', edgecolor='none', label='Baja frecuencia de agua'),
        Patch(facecolor='#4eb3d3', edgecolor='none', label='Alta frecuencia de agua'),
        Line2D([0], [0], color=GRILLA_COLOR, linewidth=0.8, linestyle='--',
               label='Grilla EPSG:9377 (CTM-12)'),
    ]
    ax.legend(handles=leyenda, loc='upper left', fontsize=9,
              framealpha=0.95, edgecolor='gray', title='Convenciones',
              title_fontsize=10)

    salida = os.path.join(RUTA_SALIDA, "mapa_frecuencia_agua.png")
    fig.savefig(salida, dpi=300, facecolor='white', bbox_inches='tight')
    plt.close(fig)
    print(f"  ✓ Guardado: {salida}")


# ==============================================================================
# 4) CLASIFICACIÓN DE AGUA SAR
# ==============================================================================

def generar_mapa_sar():
    print("\n" + "█"*70)
    print("  4/4  MAPA CLASIFICACIÓN SAR")
    print("█"*70)

    with rasterio.open(SAR_RUTA_BINARIO) as src:
        binario = src.read(1)
        extent  = plotting_extent(src)
        crs     = src.crs

    gdf = gpd.read_file(RUTA_SHP)
    if gdf.crs != crs:
        gdf = gdf.to_crs(crs)

    validos         = binario != 255
    px_agua         = int(np.sum((binario == 1) & validos))
    px_no_agua      = int(np.sum((binario == 0) & validos))
    total           = px_agua + px_no_agua
    pct_agua        = px_agua    / total * 100 if total > 0 else 0
    pct_no_agua     = px_no_agua / total * 100 if total > 0 else 0

    print(f"  Pixeles agua:    {px_agua:,} ({pct_agua:.1f}%)")
    print(f"  Pixeles no-agua: {px_no_agua:,} ({pct_no_agua:.1f}%)")

    colores = np.zeros((*binario.shape, 4))
    colores[binario == 0]   = [0.85, 0.85, 0.85, 1.0]  # gris: sin agua
    colores[binario == 1]   = [0.00, 0.45, 0.75, 1.0]  # azul: agua
    colores[binario == 255] = [1.00, 1.00, 1.00, 0.0]  # transparente: nodata

    # Formato HORIZONTAL: expandir viewport X si el área es cuadrada/vertical
    minx, miny, maxx, maxy = gdf.total_bounds
    is_geographic = gdf.crs is not None and gdf.crs.is_geographic
    buf = BUFFER_M / 111320 if is_geographic else BUFFER_M
    x0, x1 = minx - buf, maxx + buf
    y0, y1 = miny - buf, maxy + buf
    dx = x1 - x0
    dy = y1 - y0
    ratio_min = 1.5
    if dx / dy < ratio_min:
        nuevo_dx = dy * ratio_min
        cx = (x0 + x1) / 2
        x0 = cx - nuevo_dx / 2
        x1 = cx + nuevo_dx / 2
    ratio = (x1 - x0) / (y1 - y0)
    fig_w = max(12.0, min(16.0, 13.0 * ratio))
    fig_h = fig_w / ratio

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), dpi=150)

    # Fondo SAR (backscatter en escala de grises)
    with rasterio.open(SAR_RUTA_BINARIO) as src:
        sar_raw = src.read(1).astype(np.float32)
        nodata_val = src.nodata
    if nodata_val is not None:
        sar_raw[sar_raw == nodata_val] = np.nan
    sar_valid = sar_raw[np.isfinite(sar_raw)]
    if sar_valid.size > 0:
        p2, p98 = np.percentile(sar_valid, 2), np.percentile(sar_valid, 98)
        sar_norm = np.clip((sar_raw - p2) / (p98 - p2 + 1e-9), 0, 1)
    else:
        sar_norm = np.zeros_like(sar_raw)
    ax.imshow(sar_norm, cmap='Blues_r', extent=extent, origin='upper', zorder=0)

    # Clasificación binaria encima
    ax.imshow(colores, extent=extent, origin='upper', zorder=1)
    gdf.boundary.plot(ax=ax, color='red', linewidth=1.5, zorder=2)

    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)

    # Grilla EPSG:9377 y norte
    dibujar_grilla_9377(ax, crs, font_size=GRILLA_FONT_SIZE_XL, mostrar_etiquetas=True)
    dibujar_norte(ax, x=0.96, y=0.95)

    # Convenciones
    leyenda = [
        Patch(facecolor=(0.0, 0.45, 0.75), edgecolor='black', linewidth=0.5,
              label=f'Agua detectada ({pct_agua:.1f}%)'),
        Patch(facecolor=(0.85, 0.85, 0.85), edgecolor='black', linewidth=0.5,
              label=f'Sin agua ({pct_no_agua:.1f}%)'),
        Line2D([0], [0], color='red', linewidth=1.5, label='Límite del predio'),
        Line2D([0], [0], color=GRILLA_COLOR, linewidth=0.8, linestyle='--',
               label='Grilla EPSG:9377 (CTM-12)'),
    ]
    ax.legend(handles=leyenda, loc='upper left', fontsize=9,
              framealpha=0.95, edgecolor='gray', title='Convenciones',
              title_fontsize=10)

    ax.set_title(f'Clasificación de Agua SAR + Shapefile\n(Umbral: < {SAR_UMBRAL_DB} dB)',
                 fontsize=12, fontweight='bold')
    ax.set_xlabel('Coordenada Este (m)', fontsize=10)
    ax.set_ylabel('Coordenada Norte (m)', fontsize=10)
    ax.ticklabel_format(style='plain', axis='both')
    ax.tick_params(axis='both', labelsize=8)
    ax.text(0.02, 0.02, f'Pixeles agua: {px_agua:,}\nRaster: {SAR_NOMBRE_RASTER}',
            transform=ax.transAxes, fontsize=8, va='bottom', ha='left',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.9, edgecolor='gray'))

    plt.tight_layout()
    salida = os.path.join(RUTA_SALIDA, "mapa_clasificacion_SAR.png")
    fig.savefig(salida, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    print(f"  ✓ Guardado: {salida}")


# ==============================================================================
# EJECUCIÓN PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("  SALIDAS GRÁFICAS PARA INFORME")
    print(f"  Salida: {RUTA_SALIDA}")
    print("="*70)

    generar_mosaicos_ir()
    generar_mosaicos_mndwi()
    generar_mapa_frecuencia()
    generar_mapa_sar()

    print("\n" + "="*70)
    print("  ✅ PROCESO COMPLETADO")
    print(f"  Archivos generados en: {RUTA_SALIDA}")
    print("="*70 + "\n")
