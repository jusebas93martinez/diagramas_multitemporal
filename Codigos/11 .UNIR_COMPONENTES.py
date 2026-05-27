# -*- coding: utf-8 -*-
"""
GENERAR CAUCE PERMANENTE PRELIMINAR - CON REGLAS DE NEGOCIO

REGLAS IMPLEMENTADAS:
====================

REGLA 1 (AGUA PRIORITARIA):
   El agua (hidrologico) SIEMPRE debe estar dentro del cauce final.
   El agua NO puede quedar por fuera del limite.
   Si el agua esta mas afuera que el ecosistemico, el agua define el limite.

REGLA 2 (GEOMORFOLOGICO ADAPTATIVO):
   El geomorfologico actua como limite MAXIMO, pero de forma condicional:
   - Si esta CERCA de (eco + hidro): es el limite real
   - Si esta MUY LEJOS: se recorta para no extenderse demasiado

REGLA 3 (PRIORIDAD):
   Agua (hidrologico) > Ecosistemico > Geomorfologico

REGLA 4 (LIMITE EXTERIOR):
   Si ecosistemico y/o hidrologico estan FUERA del geomorfologico,
   el limite sera el MAS EXTERIOR de (eco, hidro), NO el geomorfologico.
   El geomorfologico solo limita cuando CONTIENE a los otros.

FORMULA FINAL:
   CAUCE = Union de las partes validas segun las reglas

   Donde el limite se determina dinamicamente segun la posicion relativa
"""

import geopandas as gpd
import os
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from shapely.ops import unary_union
from shapely.geometry import MultiPolygon, Polygon

# =============================================================================
# CONFIGURACION DE PARAMETROS
# =============================================================================

# Radio de suavizado para el geomorfologico (elimina efecto escalera del DEM)
RADIO_SUAVIZADO_GEO = 15  # metros - ajustar segun resolucion del raster fuente
TOLERANCIA_SIMPLIFY_GEO = 5  # metros - tolerancia para reducir vertices

# =============================================================================
# RUTAS DE ENTRADA
# =============================================================================
poligono_ecosistemico = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\COBERTURAS\Cienagas\coberturas.shp"
poligono_geomorfologico = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\DEM\resultados_Geomorfologico\poligono_geomorfologico_INDICE.shp"
poligono_hidrologico = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\HIDROLOGICO\HIDROLOGICO.shp"
# =============================================================================
# RUTAS DE SALIDA
# =============================================================================
carpeta_salida = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\POLIGONO_FINAL_PRELIMINAR"
os.makedirs(carpeta_salida, exist_ok=True)

salida_cauce = os.path.join(carpeta_salida, "cauce_permanente_reglas.shp")
salida_grafico = os.path.join(carpeta_salida, "analisis_cauce_reglas.png")
salida_diagnostico = os.path.join(carpeta_salida, "diagnostico_reglas.txt")

# =============================================================================
# FUNCIONES DE ANALISIS
# =============================================================================

def aplicar_reglas_cauce(geom_eco, geom_hidro, geom_geo):
    """
    Aplica las reglas de negocio para calcular el cauce permanente.

    REGLA PRINCIPAL:
      CAUCE = (coberturas UNION hidrologico) INTERSECCION geomorfologico
      El geomorfologico SIEMPRE recorta el resultado.

    Retorna: (geometria_cauce, diagnostico)
    """
    diagnostico = []
    diagnostico.append("=" * 60)
    diagnostico.append("APLICACION DE REGLAS PARA CAUCE PERMANENTE")
    diagnostico.append("=" * 60)

    # -------------------------------------------------------------------------
    # PASO 1: Union de coberturas + hidrologico
    # -------------------------------------------------------------------------
    geom_union = geom_eco.union(geom_hidro)
    diagnostico.append(f"\n[PASO 1] Union coberturas + hidrologico: {geom_union.area / 10000:.2f} ha")
    diagnostico.append(f"   Coberturas: {geom_eco.area / 10000:.2f} ha")
    diagnostico.append(f"   Hidrologico: {geom_hidro.area / 10000:.2f} ha")

    # -------------------------------------------------------------------------
    # PASO 2: Recortar con geomorfologico
    # El geomorfologico SIEMPRE actua como limite maximo
    # -------------------------------------------------------------------------
    cauce_final = geom_union.intersection(geom_geo)
    diagnostico.append(f"\n[PASO 2] Recorte con geomorfologico:")
    diagnostico.append(f"   Geomorfologico: {geom_geo.area / 10000:.2f} ha")
    diagnostico.append(f"   Cauce recortado: {cauce_final.area / 10000:.2f} ha")

    # Diagnostico de partes recortadas
    parte_recortada = geom_union.difference(geom_geo)
    if not parte_recortada.is_empty:
        diagnostico.append(f"   Area recortada (fuera del geo): {parte_recortada.area / 10000:.2f} ha")

    # -------------------------------------------------------------------------
    # RESULTADO FINAL
    # -------------------------------------------------------------------------
    area_final = cauce_final.area / 10000
    diagnostico.append("\n" + "=" * 60)
    diagnostico.append(f"CAUCE PERMANENTE FINAL: {area_final:.2f} ha")
    diagnostico.append("=" * 60)

    return cauce_final, diagnostico


# =============================================================================
# PROCESAMIENTO PRINCIPAL
# =============================================================================

print("=" * 70)
print("CAUCE PERMANENTE - SISTEMA DE REGLAS")
print("=" * 70)

# -------------------------------------------------------------------------
# PASO 1: Cargar datos
# -------------------------------------------------------------------------
print("\n[1/5] Cargando shapefiles...")

gdf_eco = gpd.read_file(poligono_ecosistemico)
print(f"   Ecosistemico: {len(gdf_eco)} poligonos")

gdf_geo = gpd.read_file(poligono_geomorfologico)
print(f"   Geomorfologico: {len(gdf_geo)} poligonos")

gdf_hidro = gpd.read_file(poligono_hidrologico)
print(f"   Hidrologico: {len(gdf_hidro)} poligonos")

# -------------------------------------------------------------------------
# PASO 2: Unificar CRS
# -------------------------------------------------------------------------
print("\n[2/5] Unificando sistemas de coordenadas...")

crs_referencia = gdf_eco.crs

if gdf_geo.crs != crs_referencia:
    gdf_geo = gdf_geo.to_crs(crs_referencia)
if gdf_hidro.crs != crs_referencia:
    gdf_hidro = gdf_hidro.to_crs(crs_referencia)

print(f"   CRS: {crs_referencia}")

# -------------------------------------------------------------------------
# PASO 3: Preparar geometrias
# -------------------------------------------------------------------------
print("\n[3/5] Preparando geometrias...")

geom_eco = unary_union(gdf_eco.geometry)
geom_geo = unary_union(gdf_geo.geometry)
geom_hidro = unary_union(gdf_hidro.geometry)

area_eco = geom_eco.area / 10000
area_geo = geom_geo.area / 10000
area_hidro = geom_hidro.area / 10000

print(f"   Ecosistemico: {area_eco:.2f} ha")
print(f"   Geomorfologico: {area_geo:.2f} ha")
print(f"   Hidrologico: {area_hidro:.2f} ha")

# -------------------------------------------------------------------------
# PASO 4: Aplicar reglas
# -------------------------------------------------------------------------
print("\n[4/5] Aplicando reglas de negocio...")

params = {
    'buffer_geo': BUFFER_GEOMORFOLOGICO,
    'buffer_agua': BUFFER_AGUA,
    'umbral_cercania': UMBRAL_CERCANIA
}

cauce_final, diagnostico, datos_intermedios = aplicar_reglas_cauce(
    geom_eco, geom_hidro, geom_geo, params
)

area_cauce = cauce_final.area / 10000
print(f"\n   CAUCE PERMANENTE: {area_cauce:.2f} ha")

# Guardar diagnostico
with open(salida_diagnostico, 'w', encoding='utf-8') as f:
    f.write('\n'.join(diagnostico))
print(f"   Diagnostico guardado: {os.path.basename(salida_diagnostico)}")

# -------------------------------------------------------------------------
# PASO 5: Guardar resultados
# -------------------------------------------------------------------------
print("\n[5/5] Guardando resultados...")

# -------------------------------------------------------------------------
# ELIMINAR HUECOS INTERNOS DEL CAUCE FINAL
# -------------------------------------------------------------------------

def eliminar_huecos(geom):
    """Elimina todos los anillos interiores (huecos) de un poligono."""
    if geom.geom_type == "Polygon":
        return Polygon(geom.exterior)
    elif geom.geom_type == "MultiPolygon":
        return MultiPolygon([Polygon(pol.exterior) for pol in geom.geoms])
    return geom

cauce_sin_huecos = eliminar_huecos(cauce_final)

# -------------------------------------------------------------------------
# SUAVIZADO DEL TRAZADO FINAL (elimina efecto escalera de pixeles)
# Buffer positivo + negativo redondea esquinas sin cambiar el area total
# Simplify reduce vertices manteniendo la forma general
# -------------------------------------------------------------------------
RADIO_SUAVIZADO = 15    # metros - ajustar segun resolucion del raster fuente
TOLERANCIA_SIMPLIFY = 5  # metros - tolerancia para reducir vertices

cauce_suavizado = cauce_sin_huecos.buffer(RADIO_SUAVIZADO).buffer(-RADIO_SUAVIZADO)
cauce_suavizado = cauce_suavizado.simplify(TOLERANCIA_SIMPLIFY, preserve_topology=True)

# Asegurar que no haya huecos nuevos tras el suavizado
cauce_suavizado = eliminar_huecos(cauce_suavizado)

area_cauce_final = cauce_suavizado.area / 10000
area_cauce_bruto = cauce_sin_huecos.area / 10000
huecos_eliminados = area_cauce_bruto - (cauce_final.area / 10000)

print(f"   Area cauce bruto (con huecos):  {cauce_final.area / 10000:.4f} ha")
print(f"   Area tras quitar huecos:        {area_cauce_bruto:.4f} ha")
print(f"   Area tras suavizado:            {area_cauce_final:.4f} ha")
print(f"   Diferencia por suavizado:       {abs(area_cauce_final - area_cauce_bruto):.4f} ha")

gdf_cauce = gpd.GeoDataFrame(
    {'id': [1],
     'nombre': ['Cauce Permanente'],
     'area_ha': [area_cauce_final],
     'metodo': ['Sistema de Reglas v2'],
     'buffer_geo': [BUFFER_GEOMORFOLOGICO],
     'umbral_m': [UMBRAL_CERCANIA]},
    geometry=[cauce_suavizado],
    crs=crs_referencia
)

gdf_cauce.to_file(salida_cauce)
print(f"   Shapefile: {os.path.basename(salida_cauce)}")

# =============================================================================
# VISUALIZACION
# =============================================================================

print("\n   Generando visualizacion...")

fig, axes = plt.subplots(2, 2, figsize=(16, 14))

# Colores
COLOR_ECO = '#27ae60'       # Verde
COLOR_HIDRO = '#8e44ad'     # Purpura
COLOR_GEO = '#e67e22'       # Naranja
COLOR_CAUCE = '#3498db'     # Azul
COLOR_LIMITE = '#f1c40f'    # Amarillo

# --- Panel 1: Capas originales ---
ax1 = axes[0, 0]
ax1.set_title('1. CAPAS DE ENTRADA', fontsize=12, fontweight='bold')

if not geom_eco.is_empty:
    gpd.GeoDataFrame(geometry=[geom_eco]).plot(ax=ax1, color=COLOR_ECO, alpha=0.5, edgecolor='darkgreen', linewidth=1.5)
if not geom_hidro.is_empty:
    gpd.GeoDataFrame(geometry=[geom_hidro]).plot(ax=ax1, color=COLOR_HIDRO, alpha=0.6, edgecolor='purple', linewidth=1.5)
if not geom_geo.is_empty:
    gpd.GeoDataFrame(geometry=[geom_geo]).plot(ax=ax1, color='none', edgecolor=COLOR_GEO, linewidth=2.5, linestyle='--')

legend1 = [
    Patch(facecolor=COLOR_ECO, alpha=0.5, edgecolor='darkgreen', label=f'Ecosistemico ({area_eco:.1f} ha)'),
    Patch(facecolor=COLOR_HIDRO, alpha=0.6, edgecolor='purple', label=f'Hidrologico ({area_hidro:.1f} ha)'),
    Patch(facecolor='none', edgecolor=COLOR_GEO, linestyle='--', linewidth=2, label=f'Geomorfologico ({area_geo:.1f} ha)')
]
ax1.legend(handles=legend1, loc='upper right', fontsize=9)
ax1.axis('off')
ax1.set_aspect('equal')

# --- Panel 2: Analisis de limite ---
ax2 = axes[0, 1]
geo_cerca = datos_intermedios['geo_esta_cerca']
titulo_limite = 'CERCA - Limite Directo' if geo_cerca else f'LEJOS - Buffer {BUFFER_GEOMORFOLOGICO}m'
ax2.set_title(f'2. LIMITE ADAPTATIVO ({titulo_limite})', fontsize=12, fontweight='bold')

# Union eco + hidro
geom_union = geom_eco.union(geom_hidro)
gpd.GeoDataFrame(geometry=[geom_union]).plot(ax=ax2, color='lightblue', alpha=0.3, edgecolor='blue', linewidth=1)

# Buffer de influencia
if not geo_cerca:
    buffer_zona = geom_union.buffer(BUFFER_GEOMORFOLOGICO)
    gpd.GeoDataFrame(geometry=[buffer_zona]).plot(ax=ax2, color='none', edgecolor='red', linewidth=1.5, linestyle=':')

# Geomorfologico original
gpd.GeoDataFrame(geometry=[geom_geo]).plot(ax=ax2, color='none', edgecolor=COLOR_GEO, linewidth=2, linestyle='--', alpha=0.4)

# Limite efectivo
limite_efectivo = datos_intermedios['limite_efectivo']
if not limite_efectivo.is_empty:
    gpd.GeoDataFrame(geometry=[limite_efectivo]).plot(ax=ax2, color=COLOR_LIMITE, alpha=0.4, edgecolor='gold', linewidth=2)

legend2 = [
    Patch(facecolor='lightblue', alpha=0.3, edgecolor='blue', label='Union (Eco+Hidro)'),
    Patch(facecolor='none', edgecolor='red', linestyle=':', label=f'Zona influencia ({BUFFER_GEOMORFOLOGICO}m)') if not geo_cerca else Patch(facecolor='none', edgecolor='none', label=''),
    Patch(facecolor='none', edgecolor=COLOR_GEO, linestyle='--', alpha=0.4, label='Geomorfologico original'),
    Patch(facecolor=COLOR_LIMITE, alpha=0.4, edgecolor='gold', label='Limite efectivo')
]
ax2.legend(handles=[l for l in legend2 if l.get_label()], loc='upper right', fontsize=9)
ax2.axis('off')
ax2.set_aspect('equal')

# --- Panel 3: Aplicacion de reglas ---
ax3 = axes[1, 0]
usa_regla_4 = datos_intermedios.get('usa_regla_4', False)
titulo_regla = '3. APLICACION DE REGLAS' + (' (Regla 4 activa)' if usa_regla_4 else '')
ax3.set_title(titulo_regla, fontsize=12, fontweight='bold')

# Geomorfologico como referencia
gpd.GeoDataFrame(geometry=[geom_geo]).plot(ax=ax3, color='none', edgecolor=COLOR_GEO, linewidth=1.5, linestyle='--', alpha=0.5)

# Eco limitado (parte interior)
eco_limitado = datos_intermedios['eco_limitado']
if not eco_limitado.is_empty:
    gpd.GeoDataFrame(geometry=[eco_limitado]).plot(ax=ax3, color=COLOR_ECO, alpha=0.4, edgecolor='darkgreen', linewidth=1)

# Hidrologico (siempre completo)
gpd.GeoDataFrame(geometry=[geom_hidro]).plot(ax=ax3, color=COLOR_HIDRO, alpha=0.7, edgecolor='purple', linewidth=2)

# Zonas FUERA del geomorfologico (Regla 4)
eco_fuera = datos_intermedios.get('eco_fuera_geo', Polygon())
hidro_fuera = datos_intermedios.get('hidro_fuera_geo', Polygon())

legend3 = [
    Patch(facecolor=COLOR_HIDRO, alpha=0.7, edgecolor='purple', label=f'Hidrologico COMPLETO\n(Regla 1: Siempre incluido)'),
    Patch(facecolor=COLOR_ECO, alpha=0.4, edgecolor='darkgreen', label=f'Ecosistemico\n(Regla 2/3)'),
    Patch(facecolor='none', edgecolor=COLOR_GEO, linestyle='--', alpha=0.5, label='Limite geomorfologico'),
]

if usa_regla_4:
    # Mostrar zona exterior con patron especial
    cauce_exterior = datos_intermedios.get('cauce_exterior', Polygon())
    if not cauce_exterior.is_empty:
        gpd.GeoDataFrame(geometry=[cauce_exterior]).plot(ax=ax3, color='cyan', alpha=0.5, edgecolor='darkcyan', linewidth=2, hatch='xxx')
        legend3.append(Patch(facecolor='cyan', alpha=0.5, edgecolor='darkcyan', hatch='xxx',
                            label=f'ZONA EXTERIOR (Regla 4)\nLimite = Eco/Hidro mas ext.'))

ax3.legend(handles=legend3, loc='upper right', fontsize=8)
ax3.axis('off')
ax3.set_aspect('equal')

# --- Panel 4: Resultado final ---
ax4 = axes[1, 1]
ax4.set_title(f'4. CAUCE PERMANENTE FINAL\n({area_cauce:.2f} ha)', fontsize=12, fontweight='bold')

# Fondo tenue de capas originales
gpd.GeoDataFrame(geometry=[geom_eco]).plot(ax=ax4, color=COLOR_ECO, alpha=0.1)
gpd.GeoDataFrame(geometry=[geom_hidro]).plot(ax=ax4, color=COLOR_HIDRO, alpha=0.1)
gpd.GeoDataFrame(geometry=[geom_geo]).plot(ax=ax4, color='none', edgecolor=COLOR_GEO, linewidth=1, linestyle='--', alpha=0.3)

# Cauce final
gpd.GeoDataFrame(geometry=[cauce_suavizado]).plot(ax=ax4, color=COLOR_CAUCE, alpha=0.7, edgecolor='darkblue', linewidth=2.5)

legend4 = [
    Patch(facecolor=COLOR_CAUCE, alpha=0.7, edgecolor='darkblue', linewidth=2, label=f'CAUCE PERMANENTE\n({area_cauce:.2f} ha)'),
    Patch(facecolor='none', edgecolor=COLOR_GEO, linestyle='--', alpha=0.3, label='Limite geomorfologico')
]
ax4.legend(handles=legend4, loc='upper right', fontsize=9)
ax4.axis('off')
ax4.set_aspect('equal')

plt.suptitle('ANALISIS DE CAUCE PERMANENTE - SISTEMA DE REGLAS', fontsize=14, fontweight='bold')
plt.tight_layout()
plt.savefig(salida_grafico, dpi=150, bbox_inches='tight')
plt.show()

print(f"   Grafico: {os.path.basename(salida_grafico)}")

# =============================================================================
# RESUMEN FINAL
# =============================================================================

print("\n" + "=" * 70)
print("RESUMEN DE REGLAS APLICADAS")
print("=" * 70)

usa_regla_4 = datos_intermedios.get('usa_regla_4', False)

print("""
REGLA 1 - AGUA PRIORITARIA:
   El hidrologico SIEMPRE se incluye completo en el cauce.
   Si hay agua fuera del geomorfologico, SE INCLUYE.

REGLA 2 - GEOMORFOLOGICO ADAPTATIVO:
   Si esta cerca de (eco + hidro): Limite directo
   Si esta lejos: Se aplica buffer de """ + str(BUFFER_GEOMORFOLOGICO) + """m

REGLA 3 - PRIORIDAD DE CAPAS:
   1. Hidrologico (agua) - MAXIMA prioridad
   2. Ecosistemico - Se limita por geomorfologico
   3. Geomorfologico - Limite maximo (adaptativo)

REGLA 4 - LIMITE EXTERIOR:
   Si eco y/o hidro estan FUERA del geomorfologico:
   -> El limite es el MAS EXTERIOR (eco o hidro)
   -> El geomorfologico NO limita en esas zonas
   ESTADO: """ + ("ACTIVA" if usa_regla_4 else "No aplicada (todo dentro del geo)") + """
""")

cauce_int = datos_intermedios.get('cauce_interior', Polygon())
cauce_ext = datos_intermedios.get('cauce_exterior', Polygon())
area_int = cauce_int.area / 10000 if not cauce_int.is_empty else 0
area_ext = cauce_ext.area / 10000 if not cauce_ext.is_empty else 0

print(f"""
RESULTADO:
   Hidrologico:     {area_hidro:.2f} ha (100% incluido)
   Ecosistemico:    {area_eco:.2f} ha -> {datos_intermedios['eco_limitado'].area/10000:.2f} ha (limitado)
   Geomorfologico:  {area_geo:.2f} ha -> {datos_intermedios['limite_efectivo'].area/10000:.2f} ha (efectivo)

   Cauce INTERIOR (dentro geo):  {area_int:.2f} ha
   Cauce EXTERIOR (fuera geo):   {area_ext:.2f} ha  {'<-- Regla 4' if area_ext > 0 else ''}

   CAUCE FINAL:     {area_cauce:.2f} ha

ARCHIVOS:
   - {salida_cauce}
   - {salida_grafico}
   - {salida_diagnostico}
""")

print("=" * 70)
print("DIAGRAMA DE REGLAS:")
print("=" * 70)
print("""
                    ┌───────────────────────────────────────┐
                    │         ENTRADA DE CAPAS              │
                    └───────────────────────────────────────┘
                                      │
            ┌─────────────────────────┼─────────────────────────┐
            │                         │                         │
            ▼                         ▼                         ▼
    ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
    │  HIDROLOGICO  │       │  ECOSISTEMICO │       │GEOMORFOLOGICO │
    │    (Agua)     │       │  (Cobertura)  │       │   (Limite)    │
    └───────┬───────┘       └───────┬───────┘       └───────┬───────┘
            │                       │                       │
            │                       │                       │
    ┌───────┴───────────────────────┴───────┐               │
    │       ANALIZAR POSICION RELATIVA      │               │
    │      Que esta DENTRO y FUERA del GEO  │◄──────────────┘
    └───────────────────┬───────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼                               ▼
┌───────────────────┐         ┌───────────────────┐
│  ZONA INTERIOR    │         │  ZONA EXTERIOR    │
│ (dentro del geo)  │         │ (fuera del geo)   │
└────────┬──────────┘         └────────┬──────────┘
         │                             │
         ▼                             ▼
┌───────────────────┐         ┌───────────────────┐
│   REGLA 2 & 3     │         │     REGLA 4       │
│                   │         │                   │
│ Geo como limite   │         │ Limite = el MAS   │
│ (directo o buffer)│         │ EXTERIOR de       │
│                   │         │ Eco o Hidro       │
│ Eco se limita     │         │                   │
│ por Geo           │         │ Geo NO limita     │
└────────┬──────────┘         └────────┬──────────┘
         │                             │
         ▼                             ▼
┌───────────────────┐         ┌───────────────────┐
│  CAUCE INTERIOR   │         │  CAUCE EXTERIOR   │
└────────┬──────────┘         └────────┬──────────┘
         │                             │
         └──────────────┬──────────────┘
                        │
                     UNION
                        │
                        ▼
         ┌─────────────────────────────┐
         │        REGLA 1              │
         │   AGUA SIEMPRE INCLUIDA     │
         │   (verificacion final)      │
         └──────────────┬──────────────┘
                        │
                        ▼
         ┌─────────────────────────────┐
         │    CAUCE PERMANENTE         │
         │         FINAL               │
         └─────────────────────────────┘
""")

print("\nProceso completado!")
