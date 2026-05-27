import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import os
from scipy import stats
import calendar
from matplotlib.colors import LinearSegmentedColormap
import matplotlib.patches as mpatches

# ==============================================================================
# CONFIGURACIÓN - MODIFICAR SEGÚN EL SITIO DE ANÁLISIS
# ==============================================================================
NOMBRE_SITIO = "SAN ZENON [25021030]"  # Nombre del sitio para títulos y reportes

# 1. Rutas
archivo = r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260413\IDEAM\SAN ZENON [25021030]\SAN_ZENON_[25021030] .csv"
nombre_archivo = os.path.splitext(os.path.basename(archivo))[0]
ruta_directorio = os.path.dirname(archivo)
ruta_png = os.path.join(ruta_directorio, f"{nombre_archivo}.png")
ruta_analisis = os.path.join(ruta_directorio, f"{nombre_archivo}_analisis_completo.txt")
ruta_tabla_intranual = os.path.join(ruta_directorio, f"{nombre_archivo}_tabla_intranual.png")
ruta_tabla_interanual = os.path.join(ruta_directorio, f"{nombre_archivo}_tabla_interanual.png")
ruta_heatmap = os.path.join(ruta_directorio, f"{nombre_archivo}_heatmap.png")
ruta_años_humedos = os.path.join(ruta_directorio, f"{nombre_archivo}_años_humedos.png")
ruta_analisis_anual = os.path.join(ruta_directorio, f"{nombre_archivo}_analisis_anual.png")

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

# 5.1 Filtrar valores 0 (datos faltantes o sin registro)
registros_originales = len(df)
df = df[df["VALOR"] > 0].copy()
registros_filtrados = registros_originales - len(df)
if registros_filtrados > 0:
    print(f"⚠️ Se omitieron {registros_filtrados} registros con valor 0 (datos faltantes)")
print(f"📊 Registros válidos para análisis: {len(df)}")

# 6. Calcular media móvil centrada de 12 meses
df["MA12"] = df["VALOR"].rolling(window=12, center=True).mean()

# 7. Variable 't' en años desde la primera fecha
df["t"] = (df["FECHA"] - df["FECHA"].min()).dt.days / 365.25

# 8. Ajustes de tendencia
y = df["VALOR"].values
t = df["t"].values

# Tendencia lineal
coef_lin = np.polyfit(t, y, 1)
tend_lin = np.poly1d(coef_lin)(t)
pendiente = coef_lin[0]
cambio_decadal = pendiente * 10

# Tendencia polinómica
coef_poly2 = np.polyfit(t, y, 2)
tend_poly2 = np.poly1d(coef_poly2)(t)

# 9. Análisis estadístico adicional
# 9.1 Estadísticas mensuales
estadisticas_mensuales = df.groupby("MES")["VALOR"].agg([
    'mean', 'std', 'min', 'max', 'median'
]).round(2)
estadisticas_mensuales['cv'] = (estadisticas_mensuales['std'] / estadisticas_mensuales['mean'] * 100).round(2)

# 9.2 Identificar régimen de lluvia (meses húmedos y secos)
media_anual = df["VALOR"].mean()
meses_humedos = estadisticas_mensuales[estadisticas_mensuales['mean'] > media_anual].index.tolist()
meses_secos = estadisticas_mensuales[estadisticas_mensuales['mean'] <= media_anual].index.tolist()

# 9.3 Análisis por décadas
df['DECADA'] = (df['AÑO'] // 10) * 10
estadisticas_decadas = df.groupby('DECADA')['VALOR'].agg(['mean', 'sum', 'count']).round(2)

# 9.4 Identificar años extremos
estadisticas_anuales = df.groupby('AÑO')['VALOR'].agg(['sum', 'mean']).round(2)
percentil_10 = estadisticas_anuales['sum'].quantile(0.1)
percentil_90 = estadisticas_anuales['sum'].quantile(0.9)
años_secos = estadisticas_anuales[estadisticas_anuales['sum'] <= percentil_10].index.tolist()
años_humedos = estadisticas_anuales[estadisticas_anuales['sum'] >= percentil_90].index.tolist()

# 9.5 Detección de anomalías
df['ANOMALIA'] = df['VALOR'] - media_anual
df['ANOMALIA_PORCENTUAL'] = ((df['VALOR'] - media_anual) / media_anual * 100).round(2)

# ==============================================================================
# 9.6 ANÁLISIS DETALLADO DE LOS 10 AÑOS MÁS HÚMEDOS
# ==============================================================================

# Calcular precipitación anual total por año
precipitacion_anual = df.groupby('AÑO')['VALOR'].sum().sort_values(ascending=False)
media_anual_total = precipitacion_anual.mean()

# Top 10 años más húmedos
top10_años_humedos = precipitacion_anual.head(10)

# Top 10 años más secos
top10_años_secos = precipitacion_anual.tail(10).sort_values()

# Crear DataFrame detallado de los 10 años más húmedos con sus meses
analisis_años_humedos = []
for año in top10_años_humedos.index:
    datos_año = df[df['AÑO'] == año].copy()
    precip_total = datos_año['VALOR'].sum()
    anomalia_anual = ((precip_total / media_anual_total) - 1) * 100

    # Encontrar los meses más húmedos del año
    meses_ordenados = datos_año.sort_values('VALOR', ascending=False)
    top3_meses = meses_ordenados.head(3)

    meses_info = []
    for _, row in top3_meses.iterrows():
        meses_info.append({
            'mes': int(row['MES']),
            'valor': row['VALOR'],
            'anomalia': row['ANOMALIA_PORCENTUAL']
        })

    analisis_años_humedos.append({
        'año': int(año),
        'precip_total': precip_total,
        'anomalia_anual': anomalia_anual,
        'meses_top': meses_info,
        'n_meses': len(datos_año),
        'mes_max': datos_año.loc[datos_año['VALOR'].idxmax()],
        'mes_min': datos_año.loc[datos_año['VALOR'].idxmin()]
    })

# Análisis de períodos consecutivos húmedos
def encontrar_periodos_humedos(df, umbral_percentil=75):
    """Encuentra períodos consecutivos con precipitación sobre el percentil"""
    umbral = df['VALOR'].quantile(umbral_percentil/100)
    df_temp = df.copy()
    df_temp['sobre_umbral'] = df_temp['VALOR'] > umbral

    periodos = []
    inicio = None
    for idx, row in df_temp.iterrows():
        if row['sobre_umbral']:
            if inicio is None:
                inicio = row['FECHA']
                acum = row['VALOR']
            else:
                acum += row['VALOR']
        else:
            if inicio is not None:
                fin = df_temp.loc[idx-1, 'FECHA'] if idx > 0 else inicio
                duracion = (fin.year - inicio.year) * 12 + (fin.month - inicio.month) + 1
                if duracion >= 2:  # Solo períodos de 2+ meses
                    periodos.append({
                        'inicio': inicio,
                        'fin': fin,
                        'duracion_meses': duracion,
                        'precip_acumulada': acum
                    })
                inicio = None

    # Ordenar por precipitación acumulada
    periodos.sort(key=lambda x: x['precip_acumulada'], reverse=True)
    return periodos[:10]  # Top 10 períodos

periodos_humedos = encontrar_periodos_humedos(df.reset_index(drop=True))

# Análisis de distribución estacional por año
distribucion_estacional = df.pivot_table(values='VALOR', index='AÑO', columns='MES', aggfunc='sum')

# Percentiles anuales para clasificación
P25_anual = precipitacion_anual.quantile(0.25)
P75_anual = precipitacion_anual.quantile(0.75)
P10_anual = precipitacion_anual.quantile(0.10)
P90_anual = precipitacion_anual.quantile(0.90)

# Clasificación de años
años_muy_humedos = precipitacion_anual[precipitacion_anual >= P90_anual].index.tolist()
años_humedos_p75 = precipitacion_anual[(precipitacion_anual >= P75_anual) & (precipitacion_anual < P90_anual)].index.tolist()
años_normales = precipitacion_anual[(precipitacion_anual > P25_anual) & (precipitacion_anual < P75_anual)].index.tolist()
años_secos_p25 = precipitacion_anual[(precipitacion_anual <= P25_anual) & (precipitacion_anual > P10_anual)].index.tolist()
años_muy_secos = precipitacion_anual[precipitacion_anual <= P10_anual].index.tolist()

print(f"\n📈 ANÁLISIS DE AÑOS EXTREMOS:")
print(f"   Media anual histórica: {media_anual_total:.1f} mm")
print(f"   P10 anual: {P10_anual:.1f} mm | P90 anual: {P90_anual:.1f} mm")
print(f"   Años muy húmedos (>P90): {len(años_muy_humedos)}")
print(f"   Años muy secos (<P10): {len(años_muy_secos)}")

# 10. Crear figura mejorada
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), height_ratios=[3, 1])

# 10.1 Gráfico principal
ax1.bar(df["FECHA"], df["VALOR"], width=20, color='skyblue', alpha=0.5,
        label="Registro pluviométrico mensual", edgecolor='navy', linewidth=0.5)
ax1.plot(df["FECHA"], df["VALOR"], color='blue', linewidth=0.8, alpha=0.7)
ax1.plot(df["FECHA"], df["MA12"], color='red', linewidth=2,
         label=f"Media móvil 12 meses", alpha=0.9)
ax1.plot(df["FECHA"], tend_lin, color='green', linestyle='--', linewidth=2,
         label=f"Tendencia lineal (Cambio: {cambio_decadal:.1f} mm/década)")
ax1.axhline(y=media_anual, color='gray', linestyle=':', linewidth=1.5,
            label=f'Media histórica: {media_anual:.1f} mm', alpha=0.7)

# Líneas de máximo y mínimo histórico
valor_max = df["VALOR"].max()
valor_min = df["VALOR"].min()
fecha_max = df.loc[df["VALOR"].idxmax(), "FECHA"]
fecha_min = df.loc[df["VALOR"].idxmin(), "FECHA"]
ax1.axhline(y=valor_max, color='darkblue', linestyle='-.', linewidth=1.5,
            label=f'Máximo histórico: {valor_max:.1f} mm ({fecha_max.strftime("%Y-%m")})', alpha=0.85)
ax1.axhline(y=valor_min, color='darkorange', linestyle='-.', linewidth=1.5,
            label=f'Mínimo histórico: {valor_min:.1f} mm ({fecha_min.strftime("%Y-%m")})', alpha=0.85)

# Marcar valores extremos
percentil_95 = df["VALOR"].quantile(0.95)
valores_extremos = df[df["VALOR"] > percentil_95]
ax1.scatter(valores_extremos["FECHA"], valores_extremos["VALOR"],
            color='red', s=50, zorder=5, label='Valores extremos (>P95)')

ax1.set_title(f"Análisis Pluviométrico Mensual - Estación IDEAM {NOMBRE_SITIO}", fontsize=14, fontweight='bold')
ax1.set_ylabel("Registro Pluviométrico (mm)", fontsize=12)
ax1.grid(True, alpha=0.3, linestyle='--')
ax1.legend(loc='upper left', fontsize=10, framealpha=0.9)
ax1.set_xlim(df["FECHA"].min(), df["FECHA"].max())

# 10.2 Gráfico de anomalías porcentuales (más intuitivo)
colores = ['#d73027' if x < 0 else '#4575b4' for x in df['ANOMALIA_PORCENTUAL']]
ax2.bar(df["FECHA"], df['ANOMALIA_PORCENTUAL'], width=20, color=colores, alpha=0.7,
        edgecolor='none')
ax2.axhline(y=0, color='black', linewidth=1.2)

# Bandas de referencia para clasificar la anomalía
ax2.axhspan(-25, 25, color='#ffffbf', alpha=0.2)
ax2.axhspan(25, 100, color='#4575b4', alpha=0.1)
ax2.axhspan(100, ax2.get_ylim()[1] if ax2.get_ylim()[1] > 100 else 200, color='#4575b4', alpha=0.1)
ax2.axhspan(-100, -25, color='#d73027', alpha=0.1)
ax2.axhspan(ax2.get_ylim()[0] if ax2.get_ylim()[0] < -100 else -200, -100, color='#d73027', alpha=0.1)

ax2.set_xlabel("Fecha", fontsize=12)
ax2.set_ylabel("Variación (%)", fontsize=12)
ax2.set_title(f"Variación porcentual respecto a la media histórica ({media_anual:.1f} mm)  —  "
              f"▲ Más húmedo  |  ▼ Más seco  |  Banda amarilla = Normal (±25%)",
              fontsize=10, fontstyle='italic', loc='left')
ax2.grid(True, alpha=0.3, linestyle='--')
ax2.set_xlim(df["FECHA"].min(), df["FECHA"].max())

# Formato del eje X
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

print(f"✅ Gráfica guardada como: {ruta_png}")

# ==============================================================================
# 11. GENERACIÓN DE TABLAS PNG CON ESTILOS Y CONVENCIONES
# ==============================================================================

# 11.1 Crear tabla pivote (Año vs Mes)
meses_nombres = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun',
                 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic']
tabla = df.pivot_table(values='VALOR', index='AÑO', columns='MES', aggfunc='first')
tabla.columns = meses_nombres[:len(tabla.columns)]

# Calcular percentiles para clasificación
P25_global = df['VALOR'].quantile(0.25)
P75_global = df['VALOR'].quantile(0.75)

# Calcular percentiles mensuales para tabla interanual
percentiles_mensuales = df.groupby('MES')['VALOR'].agg(
    P25=lambda x: x.quantile(0.25),
    P75=lambda x: x.quantile(0.75),
    Media='mean'
)

# ==============================================================================
# 11.2 TABLA INTRANUAL - Colores por percentiles globales
# ==============================================================================
def color_celda_intranual(valor):
    """Asigna color según percentiles globales"""
    if pd.isna(valor):
        return '#FFFFFF'  # Blanco para sin datos
    elif valor >= P75_global:
        return '#4575b4'  # Azul - Húmedo (>P75)
    elif valor <= P25_global:
        return '#d73027'  # Rojo - Seco (<P25)
    else:
        return '#ffffbf'  # Amarillo - Normal

fig_intra, ax_intra = plt.subplots(figsize=(16, max(10, len(tabla) * 0.35)))
ax_intra.axis('off')

# Crear tabla con colores
n_rows, n_cols = tabla.shape
cell_height = 0.8 / n_rows
cell_width = 0.75 / n_cols

# Dibujar celdas con colores
for i, año in enumerate(tabla.index):
    for j, mes in enumerate(tabla.columns):
        valor = tabla.loc[año, mes]
        color = color_celda_intranual(valor)

        x = 0.12 + j * cell_width
        y = 0.88 - (i + 1) * cell_height

        rect = plt.Rectangle((x, y), cell_width, cell_height,
                            facecolor=color, edgecolor='gray', linewidth=0.5)
        ax_intra.add_patch(rect)

        # Texto del valor
        if not pd.isna(valor):
            text_color = 'white' if color in ['#4575b4', '#d73027'] else 'black'
            ax_intra.text(x + cell_width/2, y + cell_height/2, f'{valor:.0f}',
                        ha='center', va='center', fontsize=8, fontweight='bold',
                        color=text_color)
        else:
            ax_intra.text(x + cell_width/2, y + cell_height/2, '-',
                        ha='center', va='center', fontsize=8, color='gray')

# Encabezados de meses
for j, mes in enumerate(tabla.columns):
    x = 0.12 + j * cell_width
    ax_intra.text(x + cell_width/2, 0.90, mes, ha='center', va='bottom',
                fontsize=10, fontweight='bold')

# Encabezados de años
for i, año in enumerate(tabla.index):
    y = 0.88 - (i + 1) * cell_height
    ax_intra.text(0.10, y + cell_height/2, str(int(año)), ha='right', va='center',
                fontsize=9, fontweight='bold')

# Título
ax_intra.text(0.5, 0.96, f'TABLA INTRANUAL DE PRECIPITACIÓN (mm) - Estación IDEAM {NOMBRE_SITIO}',
            ha='center', va='bottom', fontsize=14, fontweight='bold',
            transform=ax_intra.transAxes)
ax_intra.text(0.5, 0.93, f'Período: {int(tabla.index.min())} - {int(tabla.index.max())} | Fuente: IDEAM',
            ha='center', va='bottom', fontsize=10, fontstyle='italic',
            transform=ax_intra.transAxes)

# Leyenda de convenciones
legend_y = 0.06
legend_patches = [
    mpatches.Patch(facecolor='#4575b4', edgecolor='gray', label=f'Húmedo (>P75 = {P75_global:.0f} mm)'),
    mpatches.Patch(facecolor='#ffffbf', edgecolor='gray', label=f'Normal (P25-P75)'),
    mpatches.Patch(facecolor='#d73027', edgecolor='gray', label=f'Seco (<P25 = {P25_global:.0f} mm)'),
    mpatches.Patch(facecolor='white', edgecolor='gray', label='Sin datos'),
]
ax_intra.legend(handles=legend_patches, loc='lower center', ncol=4,
               fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

# Estadísticas en pie de tabla
stats_text = f'Media histórica: {df["VALOR"].mean():.1f} mm | P25: {P25_global:.1f} mm | P75: {P75_global:.1f} mm | CV: {(df["VALOR"].std()/df["VALOR"].mean()*100):.1f}%'
ax_intra.text(0.5, 0.10, stats_text, ha='center', va='top', fontsize=9,
            transform=ax_intra.transAxes, bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.5))

plt.savefig(ruta_tabla_intranual, dpi=300, bbox_inches='tight', facecolor='white')
plt.close(fig_intra)
print(f"✅ Tabla intranual guardada como: {ruta_tabla_intranual}")

# ==============================================================================
# 11.3 TABLA INTERANUAL - Colores por percentiles mensuales
# ==============================================================================
def color_celda_interanual(valor, mes_idx):
    """Asigna color según percentiles del mes específico"""
    if pd.isna(valor):
        return '#FFFFFF'
    mes = mes_idx + 1
    if mes in percentiles_mensuales.index:
        p25_mes = percentiles_mensuales.loc[mes, 'P25']
        p75_mes = percentiles_mensuales.loc[mes, 'P75']
        if valor >= p75_mes:
            return '#4575b4'  # Azul - Por encima del P75 del mes
        elif valor <= p25_mes:
            return '#d73027'  # Rojo - Por debajo del P25 del mes
        else:
            return '#ffffbf'  # Amarillo - Normal para el mes
    return '#ffffbf'

fig_inter, ax_inter = plt.subplots(figsize=(16, max(10, len(tabla) * 0.35)))
ax_inter.axis('off')

# Dibujar celdas con colores (por percentiles mensuales)
for i, año in enumerate(tabla.index):
    for j, mes in enumerate(tabla.columns):
        valor = tabla.loc[año, mes]
        color = color_celda_interanual(valor, j)

        x = 0.12 + j * cell_width
        y = 0.88 - (i + 1) * cell_height

        rect = plt.Rectangle((x, y), cell_width, cell_height,
                            facecolor=color, edgecolor='gray', linewidth=0.5)
        ax_inter.add_patch(rect)

        if not pd.isna(valor):
            text_color = 'white' if color in ['#4575b4', '#d73027'] else 'black'
            ax_inter.text(x + cell_width/2, y + cell_height/2, f'{valor:.0f}',
                        ha='center', va='center', fontsize=8, fontweight='bold',
                        color=text_color)
        else:
            ax_inter.text(x + cell_width/2, y + cell_height/2, '-',
                        ha='center', va='center', fontsize=8, color='gray')

# Encabezados de meses
for j, mes in enumerate(tabla.columns):
    x = 0.12 + j * cell_width
    ax_inter.text(x + cell_width/2, 0.90, mes, ha='center', va='bottom',
                fontsize=10, fontweight='bold')

# Encabezados de años
for i, año in enumerate(tabla.index):
    y = 0.88 - (i + 1) * cell_height
    ax_inter.text(0.10, y + cell_height/2, str(int(año)), ha='right', va='center',
                fontsize=9, fontweight='bold')

# Título
ax_inter.text(0.5, 0.96, f'TABLA INTERANUAL DE PRECIPITACIÓN (mm) - Estación IDEAM {NOMBRE_SITIO}',
            ha='center', va='bottom', fontsize=14, fontweight='bold',
            transform=ax_inter.transAxes)
ax_inter.text(0.5, 0.93, f'Clasificación por percentiles mensuales | Período: {int(tabla.index.min())} - {int(tabla.index.max())}',
            ha='center', va='bottom', fontsize=10, fontstyle='italic',
            transform=ax_inter.transAxes)

# Leyenda
legend_patches_inter = [
    mpatches.Patch(facecolor='#4575b4', edgecolor='gray', label='Por encima del P75 del mes (Húmedo)'),
    mpatches.Patch(facecolor='#ffffbf', edgecolor='gray', label='Normal para el mes (P25-P75)'),
    mpatches.Patch(facecolor='#d73027', edgecolor='gray', label='Por debajo del P25 del mes (Seco)'),
    mpatches.Patch(facecolor='white', edgecolor='gray', label='Sin datos'),
]
ax_inter.legend(handles=legend_patches_inter, loc='lower center', ncol=4,
               fontsize=9, framealpha=0.9, bbox_to_anchor=(0.5, 0.01))

# Tabla de percentiles mensuales de referencia
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
            transform=ax_inter.transAxes, bbox=dict(boxstyle='round', facecolor='lightyellow', alpha=0.7))

plt.savefig(ruta_tabla_interanual, dpi=300, bbox_inches='tight', facecolor='white')
plt.close(fig_inter)
print(f"✅ Tabla interanual guardada como: {ruta_tabla_interanual}")

# ==============================================================================
# 11.4 HEATMAP AÑO vs MES
# ==============================================================================
fig_heat, ax_heat = plt.subplots(figsize=(14, max(8, len(tabla) * 0.3)))

# Crear heatmap con imshow
im = ax_heat.imshow(tabla.values, cmap='YlGnBu', aspect='auto')

# Añadir valores en cada celda
for i in range(len(tabla.index)):
    for j in range(len(tabla.columns)):
        valor = tabla.iloc[i, j]
        if not pd.isna(valor):
            # Determinar color del texto según intensidad del fondo
            color_text = 'white' if valor > tabla.values[~np.isnan(tabla.values)].mean() else 'black'
            ax_heat.text(j, i, f'{valor:.0f}', ha='center', va='center',
                        fontsize=7, fontweight='bold', color=color_text)

# Configurar ejes
ax_heat.set_xticks(np.arange(len(tabla.columns)))
ax_heat.set_yticks(np.arange(len(tabla.index)))
ax_heat.set_xticklabels(tabla.columns, fontsize=10, fontweight='bold')
ax_heat.set_yticklabels([int(y) for y in tabla.index], fontsize=9)

# Etiquetas (sin título)
ax_heat.set_xlabel('Mes', fontsize=12, fontweight='bold')
ax_heat.set_ylabel('Año', fontsize=12, fontweight='bold')

# Colorbar
cbar = plt.colorbar(im, ax=ax_heat, shrink=0.8, pad=0.02)
cbar.set_label('Lectura Limnimétrica (mm)', fontsize=11)
cbar.ax.tick_params(labelsize=9)

# Líneas de división
ax_heat.set_xticks(np.arange(-.5, len(tabla.columns), 1), minor=True)
ax_heat.set_yticks(np.arange(-.5, len(tabla.index), 1), minor=True)
ax_heat.grid(which='minor', color='white', linestyle='-', linewidth=1)

plt.tight_layout(pad=0.5)
plt.savefig(ruta_heatmap, dpi=300, bbox_inches='tight', facecolor='white', pad_inches=0.1)
plt.close(fig_heat)
print(f"✅ Heatmap guardado como: {ruta_heatmap}")

# 12. Generar análisis completo en archivo TXT
with open(ruta_analisis, "w", encoding="utf-8") as f:
    f.write("="*80 + "\n")
    f.write(f"ANÁLISIS COMPLETO DE PRECIPITACIÓN - Estación IDEAM {NOMBRE_SITIO}\n")
    f.write("="*80 + "\n\n")
    
    # Información general
    f.write("1. INFORMACIÓN GENERAL DEL DATASET\n")
    f.write("-"*40 + "\n")
    f.write(f"Período analizado: {df['FECHA'].min().strftime('%Y-%m')} hasta {df['FECHA'].max().strftime('%Y-%m')}\n")
    f.write(f"Total de registros: {len(df)} meses\n")
    f.write(f"Años completos: {len(df)//12} años\n\n")
    
    # Estadísticas básicas
    f.write("2. ESTADÍSTICAS BÁSICAS DE PRECIPITACIÓN\n")
    f.write("-"*40 + "\n")
    f.write(f"Media histórica: {df['VALOR'].mean():.2f} mm\n")
    f.write(f"Mediana: {df['VALOR'].median():.2f} mm\n")
    f.write(f"Desviación estándar: {df['VALOR'].std():.2f} mm\n")
    f.write(f"Coeficiente de variación: {(df['VALOR'].std()/df['VALOR'].mean()*100):.2f}%\n")
    f.write(f"Valor mínimo: {df['VALOR'].min():.2f} mm ({df.loc[df['VALOR'].idxmin(), 'FECHA'].strftime('%Y-%m')})\n")
    f.write(f"Valor máximo: {df['VALOR'].max():.2f} mm ({df.loc[df['VALOR'].idxmax(), 'FECHA'].strftime('%Y-%m')})\n\n")
    
    # Análisis de tendencia
    f.write("3. ANÁLISIS DE TENDENCIA\n")
    f.write("-"*40 + "\n")
    if pendiente > 0:
        f.write(f"Tendencia: CRECIENTE\n")
    else:
        f.write(f"Tendencia: DECRECIENTE\n")
    f.write(f"Cambio por década: {cambio_decadal:.2f} mm/década\n")
    f.write(f"Cambio total estimado en el período: {pendiente * (df['t'].max() - df['t'].min()):.2f} mm\n\n")
    
    # Régimen pluviométrico
    f.write("4. RÉGIMEN PLUVIOMÉTRICO MENSUAL\n")
    f.write("-"*40 + "\n")
    f.write("Mes\tMedia\tDesv.Est\tCV(%)\tMín\tMáx\tMed\n")
    f.write("-"*60 + "\n")
    for mes in range(1, 13):
        if mes in estadisticas_mensuales.index:
            stats = estadisticas_mensuales.loc[mes]
            f.write(f"{meses_nombres[mes-1]}\t{stats['mean']:.1f}\t{stats['std']:.1f}\t"
                   f"{stats['cv']:.1f}\t{stats['min']:.1f}\t{stats['max']:.1f}\t{stats['median']:.1f}\n")
    
    f.write(f"\nMeses húmedos (precipitación > media): ")
    f.write(", ".join([meses_nombres[m-1] for m in meses_humedos]) + "\n")
    f.write(f"Meses secos (precipitación ≤ media): ")
    f.write(", ".join([meses_nombres[m-1] for m in meses_secos]) + "\n\n")
    
    # 10 valores más altos
    f.write("5. 10 VALORES MÁS ALTOS DE PRECIPITACIÓN\n")
    f.write("-"*40 + "\n")
    f.write("Pos\tFecha\t\tValor(mm)\tAnomalia(%)\n")
    f.write("-"*50 + "\n")
    top10 = df.nlargest(10, 'VALOR')[['FECHA', 'VALOR', 'ANOMALIA_PORCENTUAL']]
    for i, (_, row) in enumerate(top10.iterrows(), start=1):
        f.write(f"{i}\t{row['FECHA'].strftime('%Y-%m')}\t{row['VALOR']:.2f}\t\t"
                f"{row['ANOMALIA_PORCENTUAL']:+.1f}%\n")
    
    # 10 valores más bajos
    f.write("\n6. 10 VALORES MÁS BAJOS DE PRECIPITACIÓN\n")
    f.write("-"*40 + "\n")
    f.write("Pos\tFecha\t\tValor(mm)\tAnomalia(%)\n")
    f.write("-"*50 + "\n")
    bottom10 = df.nsmallest(10, 'VALOR')[['FECHA', 'VALOR', 'ANOMALIA_PORCENTUAL']]
    for i, (_, row) in enumerate(bottom10.iterrows(), start=1):
        f.write(f"{i}\t{row['FECHA'].strftime('%Y-%m')}\t{row['VALOR']:.2f}\t\t"
                f"{row['ANOMALIA_PORCENTUAL']:+.1f}%\n")
    
    # Años extremos
    f.write("\n7. AÑOS EXTREMOS\n")
    f.write("-"*40 + "\n")
    f.write(f"Años más secos (percentil 10): {', '.join(map(str, años_secos))}\n")
    f.write(f"Años más húmedos (percentil 90): {', '.join(map(str, años_humedos))}\n\n")
    
    # Análisis por décadas
    f.write("8. ANÁLISIS POR DÉCADAS\n")
    f.write("-"*40 + "\n")
    f.write("Década\tMedia(mm)\tTotal acum.\tNº registros\n")
    f.write("-"*50 + "\n")
    for decada, stats in estadisticas_decadas.iterrows():
        f.write(f"{int(decada)}s\t{stats['mean']:.2f}\t\t{stats['sum']:.0f}\t\t{int(stats['count'])}\n")
    
    # Conclusiones
    f.write("\n9. CONCLUSIONES DEL ANÁLISIS\n")
    f.write("-"*40 + "\n")
    
    # Identificar el patrón predominante
    if len(meses_humedos) == 12:
        patron = "uniforme durante todo el año"
    elif len(meses_humedos) >= 9:
        patron = "predominantemente húmedo"
    elif len(meses_humedos) >= 6:
        patron = "bimodal o estacional marcado"
    else:
        patron = "predominantemente seco con períodos húmedos cortos"
    
    f.write(f"• El régimen pluviométrico muestra un patrón {patron}\n")
    
    # Variabilidad
    cv_general = (df['VALOR'].std()/df['VALOR'].mean()*100)
    if cv_general < 30:
        variabilidad = "baja"
    elif cv_general < 60:
        variabilidad = "moderada"
    else:
        variabilidad = "alta"
    
    f.write(f"• La variabilidad de la precipitación es {variabilidad} (CV={cv_general:.1f}%)\n")
    
    # Tendencia
    if abs(cambio_decadal) < 5:
        tendencia_desc = "estable sin cambios significativos"
    elif cambio_decadal > 5:
        tendencia_desc = f"creciente con un aumento de {cambio_decadal:.1f} mm por década"
    else:
        tendencia_desc = f"decreciente con una disminución de {abs(cambio_decadal):.1f} mm por década"
    
    f.write(f"• La tendencia a largo plazo es {tendencia_desc}\n")
    
    # Meses críticos
    mes_mas_lluvioso = estadisticas_mensuales['mean'].idxmax()
    mes_mas_seco = estadisticas_mensuales['mean'].idxmin()
    f.write(f"• El mes más lluvioso es {meses_nombres[mes_mas_lluvioso-1]} "
           f"con {estadisticas_mensuales.loc[mes_mas_lluvioso, 'mean']:.1f} mm promedio\n")
    f.write(f"• El mes más seco es {meses_nombres[mes_mas_seco-1]} "
           f"con {estadisticas_mensuales.loc[mes_mas_seco, 'mean']:.1f} mm promedio\n")
    
    # Eventos extremos
    eventos_extremos = len(df[df['VALOR'] > df['VALOR'].quantile(0.95)])
    f.write(f"• Se identificaron {eventos_extremos} eventos extremos "
           f"(valores superiores al percentil 95)\n")
    
    # Recomendaciones
    f.write("\n10. RECOMENDACIONES PARA GESTIÓN HÍDRICA\n")
    f.write("-"*40 + "\n")
    
    if variabilidad == "alta":
        f.write("• La alta variabilidad sugiere la necesidad de sistemas de almacenamiento\n")
        f.write("  y regulación para gestionar los períodos de exceso y déficit\n")
    
    if len(meses_secos) >= 3:
        f.write("• Implementar estrategias de conservación durante los meses secos:\n")
        f.write(f"  {', '.join([meses_nombres[m-1] for m in meses_secos])}\n")
    
    if len(años_secos) > 0:
        f.write("• Desarrollar planes de contingencia para años secos extremos\n")
        f.write(f"  basados en los patrones históricos observados\n")
    
    if cambio_decadal < -10:
        f.write("• La tendencia decreciente requiere adaptación de los sistemas\n")
        f.write("  de aprovechamiento hídrico a menor disponibilidad futura\n")
    elif cambio_decadal > 10:
        f.write("• La tendencia creciente sugiere necesidad de mejorar sistemas\n")
        f.write("  de drenaje y control de inundaciones\n")

print(f"✅ Análisis completo guardado como: {ruta_analisis}")

# 12. Mostrar resumen en consola
print("\n" + "="*60)
print("RESUMEN DEL ANÁLISIS")
print("="*60)
print(f"Precipitación media: {df['VALOR'].mean():.2f} mm")
print(f"Tendencia: {cambio_decadal:+.2f} mm/década")
print(f"Meses más lluviosos: {', '.join([meses_nombres[m-1] for m in meses_humedos[:3]])}")
print(f"Meses más secos: {', '.join([meses_nombres[m-1] for m in meses_secos[:3]])}")
print(f"Variabilidad (CV): {(df['VALOR'].std()/df['VALOR'].mean()*100):.1f}%")
print("="*60)