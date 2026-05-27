#DESCARGAR datos de precipitación mensual para Colombia desde agosto de 2025 hasta marzo de 2026
import ee
import requests
import os
import io
import zipfile
from calendar import monthrange

# ==============================================================================
# 1. AUTENTICACIÓN E INICIALIZACIÓN
# ==============================================================================
ee.Authenticate()
ee.Initialize(project='precipitaciones-459216')
# ==============================================================================
# 2. ÁREA DE INTERÉS (COLOMBIA)
# ==============================================================================
col_fc = (
    ee.FeatureCollection("FAO/GAUL/2015/level0")
      .filter(ee.Filter.eq('ADM0_NAME', 'Colombia'))
)
# Obtener la geometría del área de interés
geometry = col_fc.geometry().bounds()
print(f"🌍 Área de interés definida: Colombia.")

# ==============================================================================
# 3. PARÁMETROS DE PROCESAMIENTO
# ==============================================================================
# Rango temporal
start_year  = 1997
start_month = 8     # Agosto 2025
end_year    = 2026
end_month   = 4     # Marzo 2026

# Carpeta de salida para los archivos TIFF
output_dir = 'precipitacion_mensual_colombia_10km'
os.makedirs(output_dir, exist_ok=True)

# --- NORMALIZACIÓN DE RESOLUCIÓN ---
# Se define una única escala de 10km (10000 metros) para todas las exportaciones.
EXPORT_SCALE_METERS = 10000
print(f" resolution normalizada a: {EXPORT_SCALE_METERS} metros para todos los datos.")

# ==============================================================================
# 4. BUCLE PRINCIPAL DE PROCESAMIENTO Y DESCARGA
# ==============================================================================
print("\n🚀 Iniciando el proceso de descarga de datos de precipitación...")

for year in range(start_year, end_year + 1):
    # Define el mes inicial y final para cada año del bucle
    first_month = start_month if year == start_year else 1
    last_month  = end_month   if year == end_year   else 12

    for month in range(first_month, last_month + 1):
        
        # --- Preparación de fechas y variables del mes ---
        start_date = ee.Date.fromYMD(year, month, 1)
        end_date = start_date.advance(1, 'month')
        dias_mes = monthrange(year, month)[1]
        
        # --- Selección de la colección de imágenes según el año ---
        image_collection = None
        source_name = ""

        if year <= 2014:
            image_collection = ee.ImageCollection("TRMM/3B43V7").select('precipitation')
            source_name = "TRMM"
        else: # Para year >= 2015
            image_collection = ee.ImageCollection("NASA/GPM_L3/IMERG_MONTHLY_V07").select('precipitation')
            source_name = "GPM IMERG"
        
        # Filtrar la colección para el mes de interés
        coll_period = image_collection.filterDate(start_date, end_date)

        # Verificar si existen datos para ese mes
        if coll_period.size().getInfo() == 0:
            print(f"❌ No hay datos {source_name} para {year}-{month:02d}. Se omite.")
            continue
        
        print(f"⚙️  Procesando {source_name} para {year}-{month:02d}...")
        
        # --- NORMALIZACIÓN DE UNIDADES ---
        # 1. Obtener la imagen de tasa de precipitación (mm/hr)
        rate_image = coll_period.first()
        
        # 2. Calcular el total de horas en el mes
        horas_mes = dias_mes * 24
        
        # 3. Convertir la tasa (mm/hr) al total mensual (mm/mes)
        total_monthly_image = rate_image.multiply(horas_mes).rename('monthly_precipitation_mm')
        
        # --- EXPORTACIÓN ---
        fname = f"precip_mensual_{year}_{month:02d}_colombia_10km.tif"
        out_path = os.path.join(output_dir, fname)

        if os.path.exists(out_path):
            print(f"👍 El archivo {fname} ya existe. Se omite la descarga.")
            continue

        try:
            # Generar URL de descarga con la resolución normalizada
            url = total_monthly_image.getDownloadURL({
                'scale':  EXPORT_SCALE_METERS,
                'crs':    'EPSG:4326',
                'region': geometry.getInfo()['coordinates'],
                'format': 'GEO_TIFF'
            })

            # Descargar y guardar el archivo
            print(f"⬇️  Descargando {fname}...")
            resp = requests.get(url, stream=True)
            resp.raise_for_status() # Lanza un error si la descarga falla
            content = resp.content

            if zipfile.is_zipfile(io.BytesIO(content)):
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    tif_file_name = next((s for s in zf.namelist() if s.lower().endswith('.tif')), None)
                    if tif_file_name:
                        source = zf.open(tif_file_name)
                        target = open(out_path, "wb")
                        with source, target:
                            target.write(source.read())
            else:
                with open(out_path, 'wb') as f:
                    f.write(content)
            
            print(f"✔️  Guardado: {out_path}")

        except Exception as e:
          
            print(f"⛔ Error al procesar o descargar para {year}-{month:02d}: {e}")

print("\n✅ Proceso completado. Todos los archivos fueron exportados a 10 km de resolución.")