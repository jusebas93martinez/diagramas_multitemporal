import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os
import calendar
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches

# ==============================================================================
# CONFIGURACIÓN - MODIFICAR SEGÚN EL SITIO DE ANÁLISIS
# ==============================================================================
NOMBRE_SITIO = "MONTERIA  - AUT [13067020]"  # Nombre del sitio para títulos y reportes
# 1. Rutas
archivo = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260423\LA CHIQUITA\IDEAM\MONTERIA\descargaDhime.csv"
nombre_archivo = os.path.splitext(os.path.basename(archivo))[0]
ruta_directorio = os.path.dirname(archivo)
ruta_png             = os.path.join(ruta_directorio, f"{nombre_archivo}.png")
ruta_analisis        = os.path.join(ruta_directorio, f"{nombre_archivo}_analisis_completo.txt")
ruta_tabla_intranual = os.path.join(ruta_directorio, f"{nombre_archivo}_tabla_intranual.png")
ruta_tabla_interanual= os.path.join(ruta_directorio, f"{nombre_archivo}_tabla_interanual.png")
ruta_heatmap         = os.path.join(ruta_directorio, f"{nombre_archivo}_heatmap.png")
ruta_analisis_anual  = os.path.join(ruta_directorio, f"{nombre_archivo}_analisis_anual.png")
ruta_duracion        = os.path.join(ruta_directorio, f"{nombre_archivo}_curva_duracion.png")
ruta_hidrograma      = os.path.join(ruta_directorio, f"{nombre_archivo}_hidrograma_anual.png")
ruta_parrafos        = os.path.join(ruta_directorio, f"{nombre_archivo}_parrafos.txt")

# 2. Leer CSV
df = pd.read_csv(archivo, sep=',', encoding='latin1')

# 3. Normalizar nombres de columnas
df.columns = df.columns.str.strip().str.upper()

# 4. Validar columnas necesarias
columnas_necesarias = {"AÑO", "MES", "VALOR"}
if not columnas_necesarias.issubset(set(df.columns)):
    print("❌ Faltan columnas necesarias. Las columnas encontradas fueron:")
    print(df.columns.tolist())
    exit()

# 5. Crear columna de fecha y ordenar
df["FECHA"] = pd.to_datetime(
    df["AÑO"].astype(str) + "-" + df["MES"].astype(str) + "-01",
    format="%Y-%m-%d"
)
df = df.sort_values("FECHA")

# 5.1 Filtrar valores negativos (inválidos en limnimetría; cero es nivel válido)
registros_originales = len(df)
df = df[df["VALOR"] >= 0].copy()
registros_filtrados = registros_originales - len(df)
if registros_filtrados > 0:
    print(f"⚠️  Se omitieron {registros_filtrados} registros con valor negativo (datos inválidos)")
print(f"📊 Registros válidos para análisis: {len(df)}")

# 5.2 Reporte de completitud del período
fecha_ini = df["FECHA"].min()
fecha_fin = df["FECHA"].max()
meses_esperados = (fecha_fin.year - fecha_ini.year) * 12 + (fecha_fin.month - fecha_ini.month) + 1
completitud = len(df) / meses_esperados * 100
meses_faltantes = meses_esperados - len(df)
print(f"📅 Período: {fecha_ini.strftime('%Y-%m')} — {fecha_fin.strftime('%Y-%m')} ({meses_esperados} meses esperados)")
print(f"📊 Completitud: {completitud:.1f}%  ({meses_faltantes} meses faltantes)")

# 6. Media móvil centrada de 12 meses
df["MA12"] = df["VALOR"].rolling(window=12, center=True).mean()

# 7. Variable 't' en años desde la primera fecha
df["t"] = (df["FECHA"] - df["FECHA"].min()).dt.days / 365.25

# 8. Ajustes de tendencia
y = df["VALOR"].values
t = df["t"].values

coef_lin  = np.polyfit(t, y, 1)
tend_lin  = np.poly1d(coef_lin)(t)
pendiente = coef_lin[0]
cambio_decadal = pendiente * 10


# ==============================================================================
# 9. ANÁLISIS ESTADÍSTICO
# ==============================================================================

# 9.1 Estadísticas mensuales
estadisticas_mensuales = df.groupby("MES")["VALOR"].agg(
    ['mean', 'std', 'min', 'max', 'median']
).round(2)
estadisticas_mensuales['cv'] = (
    estadisticas_mensuales['std'] / estadisticas_mensuales['mean'] * 100
).round(2)

# 9.2 Régimen hídrico: meses de aguas altas y bajas
media_general = df["VALOR"].mean()
meses_altos = estadisticas_mensuales[estadisticas_mensuales['mean'] > media_general].index.tolist()
meses_bajos = estadisticas_mensuales[estadisticas_mensuales['mean'] <= media_general].index.tolist()

# 9.3 Análisis por décadas
df['DECADA'] = (df['AÑO'] // 10) * 10
estadisticas_decadas = df.groupby('DECADA')['VALOR'].agg(
    ['mean', 'max', 'min', 'count']
).round(2)

# 9.4 Estadísticas anuales: nivel medio, máximo, mínimo
estadisticas_anuales = df.groupby('AÑO')['VALOR'].agg(
    ['mean', 'max', 'min', 'std']
).round(2)
nivel_anual = estadisticas_anuales['mean']

# 9.5 Percentiles anuales y clasificación de años
P10_anual = nivel_anual.quantile(0.10)
P25_anual = nivel_anual.quantile(0.25)
P75_anual = nivel_anual.quantile(0.75)
P90_anual = nivel_anual.quantile(0.90)

años_muy_altos  = nivel_anual[nivel_anual >= P90_anual].index.tolist()
años_altos_p75  = nivel_anual[(nivel_anual >= P75_anual) & (nivel_anual < P90_anual)].index.tolist()
años_normales   = nivel_anual[(nivel_anual > P25_anual) & (nivel_anual < P75_anual)].index.tolist()
años_bajos_p25  = nivel_anual[(nivel_anual <= P25_anual) & (nivel_anual > P10_anual)].index.tolist()
años_muy_bajos  = nivel_anual[nivel_anual <= P10_anual].index.tolist()

# 9.6 Anomalías respecto a la media histórica
df['ANOMALIA']            = df['VALOR'] - media_general
df['ANOMALIA_PORCENTUAL'] = ((df['VALOR'] - media_general) / media_general * 100).round(2)

# 9.7 Percentiles globales y mensuales para tablas
P25_global = df['VALOR'].quantile(0.25)
P75_global = df['VALOR'].quantile(0.75)

percentiles_mensuales = df.groupby('MES')['VALOR'].agg(
    P25=lambda x: x.quantile(0.25),
    P75=lambda x: x.quantile(0.75),
    Media='mean'
)

meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']

print(f"\n📈 ANÁLISIS DE NIVELES EXTREMOS:")
print(f"   Nivel medio histórico: {media_general:.1f} cm")
print(f"   P10 anual: {P10_anual:.1f} cm | P90 anual: {P90_anual:.1f} cm")
print(f"   Años con nivel muy alto (>P90): {len(años_muy_altos)}")
print(f"   Años con nivel muy bajo (<P10): {len(años_muy_bajos)}")

# ==============================================================================
# 10. GRÁFICA PRINCIPAL — Serie temporal con tendencia y anomalías
# ==============================================================================
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[3, 1])

# --- Panel superior: niveles mensuales ---
ax1.fill_between(df["FECHA"], df["VALOR"], alpha=0.25, color='steelblue')
ax1.plot(df["FECHA"], df["VALOR"], color='steelblue', linewidth=0.8,
         alpha=0.85, label="Nivel limnimétrico mensual")
ax1.plot(df["FECHA"], df["MA12"], color='red', linewidth=2,
         label="Media móvil 12 meses", alpha=0.9)
ax1.plot(df["FECHA"], tend_lin, color='green', linestyle='--', linewidth=2,
         label=f"Tendencia lineal ({cambio_decadal:+.1f} cm/década)")
ax1.axhline(y=media_general, color='gray', linestyle=':', linewidth=1.5,
            label=f'Nivel medio histórico: {media_general:.1f} cm', alpha=0.7)

valor_max  = df["VALOR"].max()
valor_min  = df["VALOR"].min()
fecha_max  = df.loc[df["VALOR"].idxmax(), "FECHA"]
fecha_min  = df.loc[df["VALOR"].idxmin(), "FECHA"]

ax1.axhline(y=valor_max, color='darkblue', linestyle='-.', linewidth=1.5,
            label=f'Nivel máximo histórico: {valor_max:.1f} cm ({fecha_max.strftime("%Y-%m")})',
            alpha=0.85)
ax1.axhline(y=valor_min, color='sienna', linestyle='-.', linewidth=1.5,
            label=f'Nivel mínimo histórico: {valor_min:.1f} cm ({fecha_min.strftime("%Y-%m")})',
            alpha=0.85)

percentil_95 = df["VALOR"].quantile(0.95)
percentil_5  = df["VALOR"].quantile(0.05)

ax1.set_title(f"Análisis Limnimétrico Mensual — Estación IDEAM {NOMBRE_SITIO}",
              fontsize=14, fontweight='bold')
ax1.set_ylabel("Nivel del agua (cm)", fontsize=12)
ax1.grid(True, alpha=0.3, linestyle='--')
ax1.legend(loc='upper left', fontsize=9, framealpha=0.9)
ax1.set_xlim(df["FECHA"].min(), df["FECHA"].max())

# --- Panel inferior: anomalías porcentuales ---
colores_anom = ['#8B4513' if x < 0 else '#1565C0' for x in df['ANOMALIA_PORCENTUAL']]
ax2.bar(df["FECHA"], df['ANOMALIA_PORCENTUAL'], width=20,
        color=colores_anom, alpha=0.7, edgecolor='none')
ax2.axhline(y=0, color='black', linewidth=1.2)
ax2.axhspan(-25, 25, color='#ffffbf', alpha=0.25)
ax2.axhspan(25,  300, color='#1565C0', alpha=0.08)
ax2.axhspan(-300, -25, color='#8B4513', alpha=0.08)

ax2.set_xlabel("Fecha", fontsize=12)
ax2.set_ylabel("Variación (%)", fontsize=12)
ax2.set_title(
    f"Variación porcentual respecto al nivel medio histórico ({media_general:.1f} cm)  —  "
    f"▲ Nivel alto  |  ▼ Nivel bajo  |  Banda amarilla = Normal (±25%)",
    fontsize=10, fontstyle='italic', loc='left')
ax2.grid(True, alpha=0.3, linestyle='--')
ax2.set_xlim(df["FECHA"].min(), df["FECHA"].max())

for ax in [ax1, ax2]:
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax.xaxis.set_minor_locator(mdates.YearLocator(1))
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('right')

plt.tight_layout()
plt.savefig(ruta_png, dpi=300, bbox_inches='tight')
plt.show()
print(f"✅ Gráfica principal guardada como: {ruta_png}")

# ==============================================================================
# 11. TABLAS PNG — Intranual e Interanual
# ==============================================================================

# Tabla pivote: nivel medio por mes/año
tabla = df.pivot_table(values='VALOR', index='AÑO', columns='MES', aggfunc='mean')
meses_en_tabla = tabla.columns.tolist()  # números reales de mes presentes (ej: [1,2,...,12])
tabla.columns = [meses_nombres[int(c)-1] for c in meses_en_tabla]

n_rows, n_cols = tabla.shape
cell_height = 0.8 / n_rows
cell_width  = 0.75 / n_cols

# ---- 11.2 TABLA INTRANUAL ----
def color_celda_intranual(valor):
    if pd.isna(valor):   return '#FFFFFF'
    if valor >= P75_global: return '#1565C0'   # Azul — nivel alto
    if valor <= P25_global: return '#8B4513'   # Marrón — nivel bajo
    return '#ffffbf'                            # Amarillo — normal

fig_intra, ax_intra = plt.subplots(figsize=(16, max(10, n_rows * 0.35)))
ax_intra.axis('off')

for i, año in enumerate(tabla.index):
    for j, mes in enumerate(tabla.columns):
        valor = tabla.loc[año, mes]
        color = color_celda_intranual(valor)
        x = 0.12 + j * cell_width
        y = 0.88 - (i + 1) * cell_height
        ax_intra.add_patch(plt.Rectangle(
            (x, y), cell_width, cell_height,
            facecolor=color, edgecolor='gray', linewidth=0.5))
        if not pd.isna(valor):
            tc = 'white' if color in ['#1565C0', '#8B4513'] else 'black'
            ax_intra.text(x + cell_width/2, y + cell_height/2, f'{valor:.0f}',
                          ha='center', va='center', fontsize=8, fontweight='bold', color=tc)
        else:
            ax_intra.text(x + cell_width/2, y + cell_height/2, '-',
                          ha='center', va='center', fontsize=8, color='gray')

for j, mes in enumerate(tabla.columns):
    ax_intra.text(0.12 + j*cell_width + cell_width/2, 0.90, mes,
                  ha='center', va='bottom', fontsize=10, fontweight='bold')
for i, año in enumerate(tabla.index):
    ax_intra.text(0.10, 0.88 - (i+1)*cell_height + cell_height/2,
                  str(int(año)), ha='right', va='center', fontsize=9, fontweight='bold')

ax_intra.text(0.5, 0.96, f'TABLA INTRANUAL DE NIVELES LIMNIMÉTRICOS (cm) — Estación IDEAM {NOMBRE_SITIO}',
              ha='center', va='bottom', fontsize=14, fontweight='bold', transform=ax_intra.transAxes)
ax_intra.text(0.5, 0.93, f'Período: {int(tabla.index.min())} - {int(tabla.index.max())} | Fuente: IDEAM',
              ha='center', va='bottom', fontsize=10, fontstyle='italic', transform=ax_intra.transAxes)

legend_patches = [
    mpatches.Patch(facecolor='#1565C0', edgecolor='gray', label=f'Nivel alto (>P75 = {P75_global:.0f} cm)'),
    mpatches.Patch(facecolor='#ffffbf', edgecolor='gray', label='Normal (P25–P75)'),
    mpatches.Patch(facecolor='#8B4513', edgecolor='gray', label=f'Nivel bajo (<P25 = {P25_global:.0f} cm)'),
    mpatches.Patch(facecolor='white',   edgecolor='gray', label='Sin datos'),
]
ax_intra.legend(handles=legend_patches, loc='lower center', ncol=4,
                fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

stats_text = (f'Nivel medio histórico: {df["VALOR"].mean():.1f} cm  |  '
              f'P25: {P25_global:.1f} cm  |  P75: {P75_global:.1f} cm  |  '
              f'CV: {(df["VALOR"].std()/df["VALOR"].mean()*100):.1f}%')
ax_intra.text(0.5, 0.10, stats_text, ha='center', va='top', fontsize=9,
              transform=ax_intra.transAxes,
              bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.5))

plt.savefig(ruta_tabla_intranual, dpi=300, bbox_inches='tight', facecolor='white')
plt.close(fig_intra)
print(f"✅ Tabla intranual guardada como: {ruta_tabla_intranual}")

# ---- 11.3 TABLA INTERANUAL ----
def color_celda_interanual(valor, mes_idx):
    if pd.isna(valor): return '#FFFFFF'
    mes = meses_en_tabla[mes_idx]  # número real del mes según datos disponibles
    if mes in percentiles_mensuales.index:
        if valor >= percentiles_mensuales.loc[mes, 'P75']: return '#1565C0'
        if valor <= percentiles_mensuales.loc[mes, 'P25']: return '#8B4513'
    return '#ffffbf'

fig_inter, ax_inter = plt.subplots(figsize=(16, max(10, n_rows * 0.35)))
ax_inter.axis('off')

for i, año in enumerate(tabla.index):
    for j, mes in enumerate(tabla.columns):
        valor = tabla.loc[año, mes]
        color = color_celda_interanual(valor, j)
        x = 0.12 + j * cell_width
        y = 0.88 - (i + 1) * cell_height
        ax_inter.add_patch(plt.Rectangle(
            (x, y), cell_width, cell_height,
            facecolor=color, edgecolor='gray', linewidth=0.5))
        if not pd.isna(valor):
            tc = 'white' if color in ['#1565C0', '#8B4513'] else 'black'
            ax_inter.text(x + cell_width/2, y + cell_height/2, f'{valor:.0f}',
                          ha='center', va='center', fontsize=8, fontweight='bold', color=tc)
        else:
            ax_inter.text(x + cell_width/2, y + cell_height/2, '-',
                          ha='center', va='center', fontsize=8, color='gray')

for j, mes in enumerate(tabla.columns):
    ax_inter.text(0.12 + j*cell_width + cell_width/2, 0.90, mes,
                  ha='center', va='bottom', fontsize=10, fontweight='bold')
for i, año in enumerate(tabla.index):
    ax_inter.text(0.10, 0.88 - (i+1)*cell_height + cell_height/2,
                  str(int(año)), ha='right', va='center', fontsize=9, fontweight='bold')

ax_inter.text(0.5, 0.96, f'TABLA INTERANUAL DE NIVELES LIMNIMÉTRICOS (cm) — Estación IDEAM {NOMBRE_SITIO}',
              ha='center', va='bottom', fontsize=14, fontweight='bold', transform=ax_inter.transAxes)
ax_inter.text(0.5, 0.93, f'Clasificación por percentiles mensuales | Período: {int(tabla.index.min())} - {int(tabla.index.max())}',
              ha='center', va='bottom', fontsize=10, fontstyle='italic', transform=ax_inter.transAxes)

legend_patches_inter = [
    mpatches.Patch(facecolor='#1565C0', edgecolor='gray', label='Nivel alto (>P75 del mes)'),
    mpatches.Patch(facecolor='#ffffbf', edgecolor='gray', label='Normal para el mes (P25–P75)'),
    mpatches.Patch(facecolor='#8B4513', edgecolor='gray', label='Nivel bajo (<P25 del mes)'),
    mpatches.Patch(facecolor='white',   edgecolor='gray', label='Sin datos'),
]
ax_inter.legend(handles=legend_patches_inter, loc='lower center', ncol=4,
                fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

ref_text = "Percentiles mensuales de referencia:\n"
for j, mes in enumerate(meses_nombres):
    mes_num = j + 1
    if mes_num in percentiles_mensuales.index:
        p25 = percentiles_mensuales.loc[mes_num, 'P25']
        p75 = percentiles_mensuales.loc[mes_num, 'P75']
        ref_text += f"{mes}: P25={p25:.0f}, P75={p75:.0f}  |  "
        if (j + 1) % 4 == 0:
            ref_text += "\n"
ax_inter.text(0.5, 0.10, ref_text.strip(), ha='center', va='top', fontsize=8,
              transform=ax_inter.transAxes,
              bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

plt.savefig(ruta_tabla_interanual, dpi=300, bbox_inches='tight', facecolor='white')
plt.close(fig_inter)
print(f"✅ Tabla interanual guardada como: {ruta_tabla_interanual}")

# ==============================================================================
# 11.4 HEATMAP Año × Mes
# ==============================================================================
fig_heat, ax_heat = plt.subplots(figsize=(14, max(8, n_rows * 0.3)))
im = ax_heat.imshow(tabla.values, cmap='Blues', aspect='auto')

for i in range(len(tabla.index)):
    for j in range(len(tabla.columns)):
        valor = tabla.iloc[i, j]
        if not pd.isna(valor):
            tc = 'white' if valor > np.nanmean(tabla.values) else 'black'
            ax_heat.text(j, i, f'{valor:.0f}', ha='center', va='center',
                         fontsize=7, fontweight='bold', color=tc)

ax_heat.set_xticks(np.arange(len(tabla.columns)))
ax_heat.set_yticks(np.arange(len(tabla.index)))
ax_heat.set_xticklabels(tabla.columns, fontsize=10, fontweight='bold')
ax_heat.set_yticklabels([int(y) for y in tabla.index], fontsize=9)
ax_heat.set_xlabel('Mes', fontsize=12, fontweight='bold')
ax_heat.set_ylabel('Año', fontsize=12, fontweight='bold')
ax_heat.set_title(f'Heatmap de Niveles Limnimétricos (cm) — Estación IDEAM {NOMBRE_SITIO}',
                  fontsize=13, fontweight='bold')
cbar = plt.colorbar(im, ax=ax_heat, shrink=0.8, pad=0.02)
cbar.set_label('Nivel limnimétrico (cm)', fontsize=11)
cbar.ax.tick_params(labelsize=9)
ax_heat.set_xticks(np.arange(-.5, len(tabla.columns), 1), minor=True)
ax_heat.set_yticks(np.arange(-.5, len(tabla.index), 1), minor=True)
ax_heat.grid(which='minor', color='white', linestyle='-', linewidth=1)

plt.tight_layout(pad=0.5)
plt.savefig(ruta_heatmap, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0.1)
plt.close(fig_heat)
print(f"✅ Heatmap guardado como: {ruta_heatmap}")

# ==============================================================================
# 12. ANÁLISIS ANUAL — Máximo, Medio y Mínimo por año
# ==============================================================================
años = estadisticas_anuales.index.values
t_anual = np.arange(len(años))

fig_anual, axes = plt.subplots(3, 1, figsize=(16, 14), sharex=True)

# --- Nivel máximo anual ---
coef_max = np.polyfit(t_anual, estadisticas_anuales['max'].values, 1)
axes[0].bar(años, estadisticas_anuales['max'], color='#1565C0', alpha=0.7, label='Nivel máximo anual')
axes[0].plot(años, np.poly1d(coef_max)(t_anual), 'r--', linewidth=2,
             label=f'Tendencia ({coef_max[0]*10:+.1f} cm/década)')
axes[0].axhline(estadisticas_anuales['max'].mean(), color='gray', linestyle=':',
                label=f'Media: {estadisticas_anuales["max"].mean():.1f} cm')
axes[0].set_ylabel('Nivel (cm)', fontsize=11)
axes[0].set_title('Niveles Máximos Anuales — Pico de creciente', fontsize=12, fontweight='bold')
axes[0].legend(fontsize=9, loc='upper left')
axes[0].grid(True, alpha=0.3)

# --- Nivel medio anual (coloreado según clasificación) ---
colores_años = ['#1565C0' if a in años_muy_altos else
                '#8B4513' if a in años_muy_bajos else
                'steelblue' for a in años]
coef_med = np.polyfit(t_anual, estadisticas_anuales['mean'].values, 1)
axes[1].bar(años, estadisticas_anuales['mean'], color=colores_años, alpha=0.8, label='Nivel medio anual')
axes[1].plot(años, np.poly1d(coef_med)(t_anual), 'r--', linewidth=2,
             label=f'Tendencia ({coef_med[0]*10:+.1f} cm/década)')
axes[1].axhline(nivel_anual.mean(), color='gray', linestyle=':',
                label=f'Media histórica: {nivel_anual.mean():.1f} cm')
axes[1].axhline(P90_anual, color='#1565C0', linestyle='--', alpha=0.7, linewidth=1.5,
                label=f'P90: {P90_anual:.1f} cm')
axes[1].axhline(P10_anual, color='sienna', linestyle='--', alpha=0.7, linewidth=1.5,
                label=f'P10: {P10_anual:.1f} cm')
axes[1].set_ylabel('Nivel (cm)', fontsize=11)
axes[1].set_title('Niveles Medios Anuales', fontsize=12, fontweight='bold')
axes[1].legend(fontsize=9, loc='upper left', ncol=3)
axes[1].grid(True, alpha=0.3)

# Etiqueta sobre barras extremas
for a, v in zip(años, estadisticas_anuales['mean']):
    if a in años_muy_altos or a in años_muy_bajos:
        axes[1].text(a, v + nivel_anual.std()*0.1, str(int(a)),
                     ha='center', va='bottom', fontsize=7, fontweight='bold')

# --- Nivel mínimo anual ---
coef_min = np.polyfit(t_anual, estadisticas_anuales['min'].values, 1)
axes[2].bar(años, estadisticas_anuales['min'], color='sienna', alpha=0.7, label='Nivel mínimo anual')
axes[2].plot(años, np.poly1d(coef_min)(t_anual), 'r--', linewidth=2,
             label=f'Tendencia ({coef_min[0]*10:+.1f} cm/década)')
axes[2].axhline(estadisticas_anuales['min'].mean(), color='gray', linestyle=':',
                label=f'Media: {estadisticas_anuales["min"].mean():.1f} cm')
axes[2].set_ylabel('Nivel (cm)', fontsize=11)
axes[2].set_xlabel('Año', fontsize=11)
axes[2].set_title('Niveles Mínimos Anuales — Estiaje', fontsize=12, fontweight='bold')
axes[2].legend(fontsize=9, loc='upper left')
axes[2].grid(True, alpha=0.3)

plt.suptitle(f'Análisis de Niveles Anuales — Estación IDEAM {NOMBRE_SITIO}',
             fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig(ruta_analisis_anual, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Análisis anual guardado como: {ruta_analisis_anual}")

# ==============================================================================
# 13. CURVA DE DURACIÓN DE NIVELES
# ==============================================================================
valores_ordenados = np.sort(df['VALOR'].dropna().values)[::-1]
n_obs = len(valores_ordenados)
prob_excedencia = np.arange(1, n_obs + 1) / (n_obs + 1) * 100

fig_dur, ax_dur = plt.subplots(figsize=(12, 7))
ax_dur.plot(prob_excedencia, valores_ordenados, color='steelblue', linewidth=2.5,
            label='Curva de duración de niveles')
ax_dur.fill_between(prob_excedencia, valores_ordenados, alpha=0.15, color='steelblue')

# Líneas de percentiles clave
for p in [5, 10, 25, 50, 75, 90, 95]:
    nivel_p = np.percentile(df['VALOR'].dropna(), 100 - p)
    ax_dur.axvline(x=p, color='gray', linestyle=':', alpha=0.5, linewidth=1)
    ax_dur.text(p + 0.5, nivel_p, f'Q{p:02d}\n{nivel_p:.0f} cm',
                fontsize=8, va='bottom', color='dimgray')

ax_dur.axhline(y=media_general, color='red', linestyle='--', linewidth=1.5,
               label=f'Nivel medio histórico: {media_general:.1f} cm')

ax_dur.axvspan(0,  10, alpha=0.07, color='darkblue', label='Crecientes extremas (<10%)')
ax_dur.axvspan(90, 100, alpha=0.07, color='sienna',  label='Estiajes extremos (>90%)')

ax_dur.set_xlabel('Porcentaje del tiempo que el nivel es excedido (%)', fontsize=12)
ax_dur.set_ylabel('Nivel limnimétrico (cm)', fontsize=12)
ax_dur.set_title(
    f'Curva de Duración de Niveles — Estación IDEAM {NOMBRE_SITIO}\n'
    f'Período: {df["FECHA"].min().year}–{df["FECHA"].max().year}  |  N = {n_obs} meses',
    fontsize=12, fontweight='bold')
ax_dur.legend(fontsize=10, loc='upper right')
ax_dur.grid(True, alpha=0.3, linestyle='--')
ax_dur.set_xlim(0, 100)

stats_box = (
    f'Máximo:       {valores_ordenados[0]:.1f} cm\n'
    f'Q05 (5%):    {np.percentile(df["VALOR"].dropna(), 95):.1f} cm\n'
    f'Q25 (25%):  {np.percentile(df["VALOR"].dropna(), 75):.1f} cm\n'
    f'Mediana:      {np.percentile(df["VALOR"].dropna(), 50):.1f} cm\n'
    f'Q75 (75%):  {np.percentile(df["VALOR"].dropna(), 25):.1f} cm\n'
    f'Q95 (95%):  {np.percentile(df["VALOR"].dropna(), 5):.1f} cm\n'
    f'Mínimo:       {valores_ordenados[-1]:.1f} cm'
)
ax_dur.text(0.02, 0.05, stats_box, transform=ax_dur.transAxes, fontsize=9,
            verticalalignment='bottom',
            bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.9))

plt.tight_layout()
plt.savefig(ruta_duracion, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Curva de duración guardada como: {ruta_duracion}")

# ==============================================================================
# 14. HIDROGRAMA MEDIO ANUAL — Régimen estacional de niveles
# ==============================================================================
regimen = df.groupby('MES')['VALOR'].agg(
    media  ='mean',
    std    ='std',
    p25    =lambda x: x.quantile(0.25),
    p75    =lambda x: x.quantile(0.75),
    maximo ='max',
    minimo ='min',
    mediana='median'
).round(2)

meses_num = regimen.index.values

fig_hidro, ax_hidro = plt.subplots(figsize=(12, 7))

ax_hidro.fill_between(meses_num, regimen['p25'], regimen['p75'],
                       alpha=0.25, color='steelblue', label='Rango intercuartílico (P25–P75)')
ax_hidro.fill_between(meses_num,
                       regimen['media'] - regimen['std'],
                       regimen['media'] + regimen['std'],
                       alpha=0.12, color='navy', label='Media ± 1 desv. estándar')
ax_hidro.plot(meses_num, regimen['maximo'], 'b--', linewidth=1, alpha=0.6, label='Máximo histórico')
ax_hidro.plot(meses_num, regimen['minimo'], color='sienna', linestyle='--',
              linewidth=1, alpha=0.6, label='Mínimo histórico')
ax_hidro.plot(meses_num, regimen['mediana'], color='steelblue', linewidth=2,
              linestyle='--', label='Mediana mensual')
ax_hidro.plot(meses_num, regimen['media'], color='navy', linewidth=2.5,
              marker='o', markersize=6, label='Nivel medio mensual')
ax_hidro.axhline(y=media_general, color='gray', linestyle=':', linewidth=1.5,
                  label=f'Nivel medio histórico: {media_general:.1f} cm', alpha=0.7)

ax_hidro.set_xticks(range(1, 13))
ax_hidro.set_xticklabels(meses_nombres, fontsize=11)
ax_hidro.set_xlabel('Mes', fontsize=12)
ax_hidro.set_ylabel('Nivel limnimétrico (cm)', fontsize=12)
ax_hidro.set_title(
    f'Hidrograma Medio Anual — Estación IDEAM {NOMBRE_SITIO}\n'
    f'Régimen estacional de niveles | Período: {df["FECHA"].min().year}–{df["FECHA"].max().year}',
    fontsize=12, fontweight='bold')
ax_hidro.legend(fontsize=9, loc='upper left', ncol=2, framealpha=0.9)
ax_hidro.grid(True, alpha=0.3, linestyle='--')
ax_hidro.set_xlim(0.5, 12.5)

# Tabla de estadísticas mensuales bajo el gráfico
def fila(etiqueta, campo):
    linea = f'{etiqueta:<9}'
    for m in range(1, 13):
        linea += f'{regimen.loc[m, campo]:>6.0f}' if m in regimen.index else '     -'
    return linea

cab = f'{"Mes":<9}' + ''.join(f'{m:>6}' for m in meses_nombres)
tabla_texto = '\n'.join([cab,
                         fila('Media:',  'media'),
                         fila('Máximo:', 'maximo'),
                         fila('Mínimo:', 'minimo'),
                         fila('Median:', 'mediana')])
ax_hidro.text(0.5, -0.28, tabla_texto, transform=ax_hidro.transAxes,
              fontsize=8.5, ha='center', va='top', fontfamily='monospace',
              bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.85))

plt.tight_layout()
plt.subplots_adjust(bottom=0.28)
plt.savefig(ruta_hidrograma, dpi=300, bbox_inches='tight')
plt.close()
print(f"✅ Hidrograma anual guardado como: {ruta_hidrograma}")

# ==============================================================================
# 15. ARCHIVO DE ANÁLISIS COMPLETO TXT
# ==============================================================================
with open(ruta_analisis, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write(f"ANÁLISIS LIMNIMÉTRICO COMPLETO — Estación IDEAM {NOMBRE_SITIO}\n")
    f.write("=" * 80 + "\n\n")

    f.write("1. INFORMACIÓN GENERAL\n")
    f.write("-" * 40 + "\n")
    f.write(f"Período analizado : {df['FECHA'].min().strftime('%Y-%m')} — {df['FECHA'].max().strftime('%Y-%m')}\n")
    f.write(f"Total de registros: {len(df)} meses\n")
    f.write(f"Meses esperados   : {meses_esperados} meses\n")
    f.write(f"Completitud       : {completitud:.1f}%  ({meses_faltantes} meses faltantes)\n")
    f.write(f"Años con datos    : {df['AÑO'].nunique()}\n\n")

    f.write("2. ESTADÍSTICAS BÁSICAS DE NIVELES\n")
    f.write("-" * 40 + "\n")
    f.write(f"Nivel medio histórico : {df['VALOR'].mean():.2f} cm\n")
    f.write(f"Mediana               : {df['VALOR'].median():.2f} cm\n")
    f.write(f"Desviación estándar   : {df['VALOR'].std():.2f} cm\n")
    f.write(f"Coef. de variación    : {(df['VALOR'].std()/df['VALOR'].mean()*100):.2f}%\n")
    f.write(f"Nivel mínimo registrado: {df['VALOR'].min():.2f} cm  "
            f"({df.loc[df['VALOR'].idxmin(), 'FECHA'].strftime('%Y-%m')})\n")
    f.write(f"Nivel máximo registrado: {df['VALOR'].max():.2f} cm  "
            f"({df.loc[df['VALOR'].idxmax(), 'FECHA'].strftime('%Y-%m')})\n")
    f.write(f"Rango total           : {df['VALOR'].max() - df['VALOR'].min():.2f} cm\n\n")

    f.write("3. ANÁLISIS DE TENDENCIA\n")
    f.write("-" * 40 + "\n")
    dir_tend = "CRECIENTE (niveles en aumento)" if pendiente > 0 else "DECRECIENTE (niveles en descenso)"
    f.write(f"Dirección        : {dir_tend}\n")
    f.write(f"Cambio/década    : {cambio_decadal:+.2f} cm/década\n")
    f.write(f"Cambio total est.: {pendiente*(df['t'].max()-df['t'].min()):+.2f} cm en el período\n\n")

    f.write("4. RÉGIMEN LIMNIMÉTRICO MENSUAL\n")
    f.write("-" * 40 + "\n")
    f.write(f"{'Mes':<5} {'Media':>6} {'Std':>6} {'CV%':>6} {'Mín':>6} {'Máx':>6} {'Med':>6}\n")
    f.write("-" * 45 + "\n")
    for mes in range(1, 13):
        if mes in estadisticas_mensuales.index:
            s = estadisticas_mensuales.loc[mes]
            f.write(f"{meses_nombres[mes-1]:<5} {s['mean']:>6.1f} {s['std']:>6.1f} "
                    f"{s['cv']:>6.1f} {s['min']:>6.1f} {s['max']:>6.1f} {s['median']:>6.1f}\n")
    f.write(f"\nMeses de aguas altas (> media): "
            f"{', '.join([meses_nombres[m-1] for m in meses_altos])}\n")
    f.write(f"Meses de aguas bajas (≤ media): "
            f"{', '.join([meses_nombres[m-1] for m in meses_bajos])}\n")
    amplitud = estadisticas_mensuales['mean'].max() - estadisticas_mensuales['mean'].min()
    f.write(f"Amplitud del régimen estacional: {amplitud:.1f} cm\n\n")

    f.write("5. CURVA DE DURACIÓN — PERCENTILES CLAVE\n")
    f.write("-" * 40 + "\n")
    for p in [5, 10, 20, 25, 50, 75, 80, 90, 95]:
        nivel_p = np.percentile(df['VALOR'].dropna(), 100 - p)
        f.write(f"Q{p:02d} — excedido el {p:2d}% del tiempo: {nivel_p:7.2f} cm\n")
    f.write("\n")

    f.write("6. ESTADÍSTICAS ANUALES\n")
    f.write("-" * 40 + "\n")
    f.write(f"{'Año':<6} {'Medio':>7} {'Máximo':>8} {'Mínimo':>8} {'Std':>7}\n")
    f.write("-" * 40 + "\n")
    for año, row in estadisticas_anuales.iterrows():
        f.write(f"{int(año):<6} {row['mean']:>7.1f} {row['max']:>8.1f} "
                f"{row['min']:>8.1f} {row['std']:>7.1f}\n")
    f.write("\n")

    f.write("7. CLASIFICACIÓN DE AÑOS POR NIVEL MEDIO\n")
    f.write("-" * 40 + "\n")
    f.write(f"P10={P10_anual:.1f} cm  |  P25={P25_anual:.1f} cm  |  "
            f"P75={P75_anual:.1f} cm  |  P90={P90_anual:.1f} cm\n\n")
    f.write(f"Años muy altos  (>P90): {', '.join(map(str, años_muy_altos))}\n")
    f.write(f"Años altos  (P75–P90) : {', '.join(map(str, años_altos_p75))}\n")
    f.write(f"Años normales (P25–P75): {', '.join(map(str, años_normales))}\n")
    f.write(f"Años bajos  (P10–P25) : {', '.join(map(str, años_bajos_p25))}\n")
    f.write(f"Años muy bajos  (<P10): {', '.join(map(str, años_muy_bajos))}\n\n")

    f.write("8. TOP 10 NIVELES MÁS ALTOS (CRECIENTES)\n")
    f.write("-" * 40 + "\n")
    f.write(f"{'Pos':<4} {'Fecha':<9} {'Nivel(cm)':>10} {'Anomalía(%)':>12}\n")
    for i, (_, row) in enumerate(df.nlargest(10, 'VALOR')[['FECHA', 'VALOR', 'ANOMALIA_PORCENTUAL']].iterrows(), 1):
        f.write(f"{i:<4} {row['FECHA'].strftime('%Y-%m'):<9} {row['VALOR']:>10.2f} "
                f"{row['ANOMALIA_PORCENTUAL']:>+12.1f}%\n")

    f.write("\n9. TOP 10 NIVELES MÁS BAJOS (ESTIAJES)\n")
    f.write("-" * 40 + "\n")
    f.write(f"{'Pos':<4} {'Fecha':<9} {'Nivel(cm)':>10} {'Anomalía(%)':>12}\n")
    for i, (_, row) in enumerate(df.nsmallest(10, 'VALOR')[['FECHA', 'VALOR', 'ANOMALIA_PORCENTUAL']].iterrows(), 1):
        f.write(f"{i:<4} {row['FECHA'].strftime('%Y-%m'):<9} {row['VALOR']:>10.2f} "
                f"{row['ANOMALIA_PORCENTUAL']:>+12.1f}%\n")

    f.write("\n10. ANÁLISIS POR DÉCADAS\n")
    f.write("-" * 40 + "\n")
    f.write(f"{'Década':<8} {'Medio':>7} {'Máximo':>8} {'Mínimo':>8} {'N reg.':>8}\n")
    f.write("-" * 44 + "\n")
    for dec, s in estadisticas_decadas.iterrows():
        f.write(f"{int(dec)}s    {s['mean']:>7.2f} {s['max']:>8.2f} "
                f"{s['min']:>8.2f} {int(s['count']):>8}\n")

    f.write("\n11. CONCLUSIONES DEL ANÁLISIS LIMNIMÉTRICO\n")
    f.write("-" * 40 + "\n")
    cv_gen = df['VALOR'].std() / df['VALOR'].mean() * 100
    if len(meses_altos) >= 9:
        patron = "predominantemente de aguas altas durante casi todo el año"
    elif len(meses_altos) >= 5:
        patron = "bimodal con dos períodos de aguas altas y estiaje"
    elif len(meses_altos) >= 3:
        patron = "estacional con un período definido de aguas altas"
    else:
        patron = "de aguas bajas dominantes con crecientes cortas"
    f.write(f"• Régimen hídrico: {patron}\n")
    variab = "baja" if cv_gen < 30 else "moderada" if cv_gen < 60 else "alta"
    f.write(f"• Variabilidad de niveles: {variab} (CV={cv_gen:.1f}%)\n")
    umbral_tendencia = media_general * 0.05  # 5% del nivel medio histórico
    if abs(cambio_decadal) < umbral_tendencia:
        tend_desc = "estable sin cambios significativos"
    elif cambio_decadal > umbral_tendencia:
        tend_desc = (f"creciente +{cambio_decadal:.1f} cm/década "
                     "(posible sedimentación o aumento de caudales)")
    else:
        tend_desc = (f"decreciente {cambio_decadal:.1f} cm/década "
                     "(posible descenso de caudales o cambio en la sección)")
    f.write(f"• Tendencia a largo plazo: {tend_desc}\n")
    mes_max_id = estadisticas_mensuales['mean'].idxmax()
    mes_min_id = estadisticas_mensuales['mean'].idxmin()
    f.write(f"• Mes de mayor nivel promedio: {meses_nombres[mes_max_id-1]} "
            f"({estadisticas_mensuales.loc[mes_max_id,'mean']:.1f} cm)\n")
    f.write(f"• Mes de menor nivel promedio: {meses_nombres[mes_min_id-1]} "
            f"({estadisticas_mensuales.loc[mes_min_id,'mean']:.1f} cm)\n")
    amplitud_e = estadisticas_mensuales['mean'].max() - estadisticas_mensuales['mean'].min()
    f.write(f"• Amplitud del régimen estacional: {amplitud_e:.1f} cm\n")
    n_crecientes = len(df[df['VALOR'] > percentil_95])
    n_estiajes   = len(df[df['VALOR'] < percentil_5])
    f.write(f"• Eventos de creciente extrema (>P95): {n_crecientes} meses\n")
    f.write(f"• Eventos de estiaje extremo (<P5):    {n_estiajes} meses\n")

    f.write("\n12. RECOMENDACIONES PARA GESTIÓN HÍDRICA\n")
    f.write("-" * 40 + "\n")
    if variab == "alta":
        f.write("• Alta variabilidad: posible influencia de ENSO o régimen torrencial.\n"
                "  Implementar monitoreo continuo y sistemas de alerta temprana.\n")
    if len(meses_bajos) >= 4:
        meses_estiaje = ', '.join([meses_nombres[m-1] for m in sorted(meses_bajos)[:4]])
        f.write(f"• Período de estiaje crítico: {meses_estiaje}. Planificar usos del recurso\n"
                "  hídrico con base en niveles mínimos esperados (ver Q95 en curva de duración).\n")
    if cambio_decadal < -5:
        f.write("• Tendencia decreciente: posible disminución de caudales base,\n"
                "  deforestación de cuenca o cambio climático. Requiere análisis de causa.\n")
    elif cambio_decadal > 5:
        f.write("• Tendencia creciente: posible aumento de sedimentos o cambios morfológicos.\n"
                "  Verificar sección de aforo y condiciones del cauce.\n")
    if len(años_muy_altos) > 0:
        f.write(f"• Años con nivel muy alto: {', '.join(map(str, años_muy_altos))}.\n"
                "  Asociar con fenómenos La Niña u eventos hidrometeorológicos extremos.\n")
    if len(años_muy_bajos) > 0:
        f.write(f"• Años con nivel muy bajo: {', '.join(map(str, años_muy_bajos))}.\n"
                "  Asociar con fenómenos El Niño o sequías regionales.\n")

print(f"✅ Análisis completo guardado como: {ruta_analisis}")

# ==============================================================================
# RESUMEN EN CONSOLA
# ==============================================================================
print("\n" + "=" * 60)
print("RESUMEN DEL ANÁLISIS LIMNIMÉTRICO")
print("=" * 60)
print(f"Nivel medio histórico : {df['VALOR'].mean():.2f} cm")
print(f"Nivel máximo registrado: {df['VALOR'].max():.1f} cm  ({fecha_max.strftime('%Y-%m')})")
print(f"Nivel mínimo registrado: {df['VALOR'].min():.1f} cm  ({fecha_min.strftime('%Y-%m')})")
print(f"Tendencia              : {cambio_decadal:+.2f} cm/década")
print(f"Meses de aguas altas  : {', '.join([meses_nombres[m-1] for m in meses_altos])}")
print(f"Meses de aguas bajas  : {', '.join([meses_nombres[m-1] for m in meses_bajos])}")
print(f"Variabilidad (CV)     : {(df['VALOR'].std()/df['VALOR'].mean()*100):.1f}%")
print(f"Años muy altos (>P90) : {años_muy_altos}")
print(f"Años muy bajos (<P10) : {años_muy_bajos}")
print("=" * 60)
print(f"\n📁 Archivos generados en: {ruta_directorio}")
print(f"   1. {os.path.basename(ruta_png)}")
print(f"   2. {os.path.basename(ruta_tabla_intranual)}")
print(f"   3. {os.path.basename(ruta_tabla_interanual)}")
print(f"   4. {os.path.basename(ruta_heatmap)}")
print(f"   5. {os.path.basename(ruta_analisis_anual)}")
print(f"   6. {os.path.basename(ruta_duracion)}")
print(f"   7. {os.path.basename(ruta_hidrograma)}")
print(f"   8. {os.path.basename(ruta_analisis)}")

# ==============================================================================
# 16. PÁRRAFOS PARA INFORME
# ==============================================================================

# Variables auxiliares para redacción
periodo_str   = f"{df['FECHA'].min().year}–{df['FECHA'].max().year}"
n_años        = df['AÑO'].nunique()
cv_str        = f"{(df['VALOR'].std()/df['VALOR'].mean()*100):.1f}"
mes_max_nom   = meses_nombres[estadisticas_mensuales['mean'].idxmax() - 1]
mes_min_nom   = meses_nombres[estadisticas_mensuales['mean'].idxmin() - 1]
meses_altos_str = ', '.join([meses_nombres[m-1] for m in sorted(meses_altos)])
meses_bajos_str = ', '.join([meses_nombres[m-1] for m in sorted(meses_bajos)])
amplitud_str  = f"{(estadisticas_mensuales['mean'].max() - estadisticas_mensuales['mean'].min()):.1f}"

umbral_tend   = media_general * 0.05
if abs(cambio_decadal) < umbral_tend:
    tend_parrafo = "no presenta una tendencia estadísticamente significativa, manteniéndose relativamente estable a lo largo del período"
elif cambio_decadal > 0:
    tend_parrafo = (f"muestra una tendencia creciente de {cambio_decadal:+.1f} cm por década, "
                   f"lo que podría asociarse a procesos de sedimentación en el cauce o incremento de caudales base")
else:
    tend_parrafo = (f"muestra una tendencia decreciente de {cambio_decadal:.1f} cm por década, "
                   f"lo que podría indicar una reducción de los caudales base, cambios morfológicos en la sección o efectos del cambio climático")

variab_str    = "baja" if float(cv_str) < 30 else "moderada" if float(cv_str) < 60 else "alta"
q05_val       = np.percentile(df['VALOR'].dropna(), 95)
q95_val       = np.percentile(df['VALOR'].dropna(), 5)
años_altos_str = ', '.join(map(str, años_muy_altos)) if años_muy_altos else "ninguno identificado"
años_bajos_str = ', '.join(map(str, años_muy_bajos)) if años_muy_bajos else "ninguno identificado"
amplitud_reg  = estadisticas_mensuales['mean'].max() - estadisticas_mensuales['mean'].min()

with open(ruta_parrafos, "w", encoding="utf-8") as f:
    f.write("=" * 80 + "\n")
    f.write(f"PÁRRAFOS PARA INFORME — Estación IDEAM {NOMBRE_SITIO}\n")
    f.write(f"Período: {periodo_str}  |  Generado automáticamente\n")
    f.write("=" * 80 + "\n\n")

    # ── Figura 1: Serie temporal principal ────────────────────────────────────
    f.write(f"FIGURA 1. Análisis Limnimétrico Mensual — Serie temporal, tendencia y anomalías\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 1 presenta la serie temporal de niveles limnimétricos mensuales registrados en la estación "
        f"IDEAM {NOMBRE_SITIO} durante el período {periodo_str} ({n_años} años), con una completitud del {completitud:.1f}% "
        f"de los registros esperados. El nivel medio histórico de la estación es {media_general:.1f} cm, con un máximo "
        f"registrado de {valor_max:.1f} cm en {fecha_max.strftime('%B de %Y')} y un mínimo de {valor_min:.1f} cm en "
        f"{fecha_min.strftime('%B de %Y')}. La media móvil de 12 meses (línea roja) permite identificar ciclos "
        f"interanuales de variación del nivel, suavizando la variabilidad estacional. En cuanto a la tendencia a largo "
        f"plazo, la serie {tend_parrafo}. El panel inferior muestra las anomalías porcentuales respecto al nivel medio "
        f"histórico, donde los valores positivos (azul) indican períodos con niveles por encima de lo normal y los "
        f"negativos (marrón) reflejan condiciones de estiaje o déficit hídrico.\n\n"
    )

    # ── Figura 2: Tabla intranual ──────────────────────────────────────────────
    f.write(f"FIGURA 2. Tabla Intranual de Niveles Limnimétricos\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 2 presenta la tabla intranual de niveles limnimétricos medios mensuales (en cm) para cada año "
        f"del período {periodo_str}. Cada celda representa el nivel medio de un mes determinado y está coloreada "
        f"según su posición respecto a los percentiles globales de la serie: en azul oscuro los valores superiores "
        f"al percentil 75 (P75 = {P75_global:.0f} cm), en marrón los inferiores al percentil 25 (P25 = {P25_global:.0f} cm) "
        f"y en amarillo claro los valores dentro del rango normal. Las celdas en blanco corresponden a meses sin "
        f"registro. Esta representación permite identificar visualmente años y meses con comportamiento hídrico "
        f"atípico dentro del contexto histórico de la estación.\n\n"
    )

    # ── Figura 3: Tabla interanual ─────────────────────────────────────────────
    f.write(f"FIGURA 3. Tabla Interanual de Niveles Limnimétricos\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 3 complementa la tabla anterior mediante una clasificación interanual, en la que cada valor "
        f"mensual se compara no con los percentiles globales, sino con los percentiles P25 y P75 propios de cada "
        f"mes calendario. De esta manera, un nivel alto en enero se evalúa frente a lo que históricamente es alto "
        f"para enero, eliminando el efecto de la estacionalidad. La colorimetría es la misma que en la Figura 2: "
        f"azul para niveles altos respecto al mes, amarillo para condiciones normales y marrón para niveles bajos. "
        f"Este análisis resulta especialmente útil para detectar años con déficit o superávit hídrico en meses "
        f"específicos del ciclo estacional.\n\n"
    )

    # ── Figura 4: Heatmap ─────────────────────────────────────────────────────
    f.write(f"FIGURA 4. Heatmap de Niveles Limnimétricos (Año × Mes)\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 4 presenta un mapa de calor (heatmap) que organiza los niveles limnimétricos medios mensuales "
        f"en una matriz año × mes, utilizando una escala de color continua en tonos azules donde las intensidades "
        f"más altas representan niveles mayores. Esta visualización permite identificar de forma simultánea el "
        f"régimen estacional (columnas) y la variabilidad interanual (filas), facilitando la detección de patrones "
        f"de largo plazo, anomalías puntuales y la estacionalidad característica de la estación {NOMBRE_SITIO}. "
        f"Los valores numéricos en cada celda corresponden al nivel medio mensual en centímetros.\n\n"
    )

    # ── Figura 5: Análisis anual ───────────────────────────────────────────────
    f.write(f"FIGURA 5. Análisis de Niveles Anuales (Máximo, Medio y Mínimo)\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 5 muestra la evolución temporal de los niveles limnimétricos anuales en tres paneles: "
        f"el nivel máximo anual (pico de creciente), el nivel medio anual y el nivel mínimo anual (estiaje). "
        f"En cada panel se incluye una línea de tendencia lineal y la media histórica correspondiente. "
        f"En el panel del nivel medio anual, las barras coloreadas en azul oscuro identifican los años clasificados "
        f"como muy altos (>{P90_anual:.1f} cm, percentil 90): {años_altos_str}; mientras que las barras en marrón "
        f"corresponden a años muy bajos (<{P10_anual:.1f} cm, percentil 10): {años_bajos_str}. "
        f"Este análisis permite evaluar la frecuencia e intensidad de eventos extremos a escala anual y detectar "
        f"cambios en los regímenes de creciente y estiaje a lo largo del período estudiado.\n\n"
    )

    # ── Figura 6: Curva de duración ────────────────────────────────────────────
    f.write(f"FIGURA 6. Curva de Duración de Niveles\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 6 presenta la curva de duración de niveles de la estación {NOMBRE_SITIO}, construida a partir "
        f"de los {len(df)} registros mensuales del período {periodo_str}. El eje horizontal indica el porcentaje del "
        f"tiempo en que el nivel del agua iguala o supera el valor correspondiente en el eje vertical. Los niveles "
        f"clave de la curva son: Q05 = {q05_val:.1f} cm (superado el 5% del tiempo, eventos de creciente extrema), "
        f"nivel medio histórico = {media_general:.1f} cm, y Q95 = {q95_val:.1f} cm (superado el 95% del tiempo, "
        f"condición de estiaje extremo). Las zonas sombreadas en azul oscuro (0–10%) y marrón (90–100%) delimitan "
        f"los rangos de crecientes y estiajes extremos, respectivamente. Esta curva es fundamental para el diseño "
        f"de obras hidráulicas, la gestión del recurso hídrico y la evaluación de disponibilidad de agua.\n\n"
    )

    # ── Figura 7: Hidrograma medio anual ──────────────────────────────────────
    f.write(f"FIGURA 7. Hidrograma Medio Anual — Régimen Estacional de Niveles\n")
    f.write("-" * 70 + "\n")
    f.write(
        f"La Figura 7 presenta el hidrograma medio anual de la estación {NOMBRE_SITIO}, que describe el régimen "
        f"estacional típico de niveles limnimétricos a lo largo del año calendario. El nivel medio mensual (línea "
        f"azul oscuro con marcadores) refleja el comportamiento promedio de la estación para cada mes del período "
        f"{periodo_str}. Los meses de aguas altas, con niveles superiores al promedio histórico ({media_general:.1f} cm), "
        f"son: {meses_altos_str}; mientras que los meses de estiaje son: {meses_bajos_str}. "
        f"El mes con mayor nivel promedio es {mes_max_nom} ({estadisticas_mensuales.loc[estadisticas_mensuales['mean'].idxmax(), 'mean']:.1f} cm) "
        f"y el de menor nivel es {mes_min_nom} ({estadisticas_mensuales.loc[estadisticas_mensuales['mean'].idxmin(), 'mean']:.1f} cm), "
        f"con una amplitud estacional de {amplitud_str} cm. Las bandas sombreadas muestran el rango intercuartílico "
        f"(P25–P75) y la dispersión (media ± desviación estándar), permitiendo evaluar la variabilidad "
        f"intraanual del régimen limnimétrico.\n\n"
    )

print(f"✅ Párrafos para informe guardados como: {ruta_parrafos}")
print(f"   9. {os.path.basename(ruta_parrafos)}")
