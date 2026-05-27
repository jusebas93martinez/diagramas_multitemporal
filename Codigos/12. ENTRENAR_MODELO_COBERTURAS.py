"""
ENTRENAMIENTO DE MODELO RANDOM FOREST — COBERTURAS SENTINEL-2
==============================================================
Clases objetivo:
  1 → 3.1.1  Bosque denso
  2 → 1.1.2  Tejido urbano discontinuo
  3 → 5.1.1  Ríos y corrientes de agua
  4 → 4.1.1  Humedales
  5 → 3.3.2  Zonas desnudas o degradadas

════════════════════════════════════════════════════════════════
PASO PREVIO — CREAR EL SHAPEFILE DE MUESTRAS EN QGIS
════════════════════════════════════════════════════════════════
  1. Abre la imagen Sentinel-2 en QGIS (la cruda de 6 bandas).
  2. Activa composición RGB: Banda 4 (Red) | Banda 3 (Green) | Banda 1 (Blue).
  3. Crea una capa vectorial nueva: Capa > Nueva > Shapefile → tipo Polígono.
     Agrega un campo: "Clase"  (tipo Entero).
  4. Digitaliza polígonos por clase:
       - Dibuja MUCHOS polígonos pequeños por clase (ver TIPs abajo).
       - Asigna el valor de "Clase" correspondiente (1-7).
  5. Para las NUBES (clase 7):
       - Digitaliza nubes gruesas (blancas brillantes).
       - Digitaliza también nubes delgadas / semitransparentes por separado.
       - NO digitalices sombras de nubes aquí (pueden confundirse con agua).
  6. Guarda el shapefile.

════════════════════════════════════════════════════════════════
TIPS PARA UN MODELO BIEN ENTRENADO
════════════════════════════════════════════════════════════════
  ✔ CANTIDAD      : mínimo 150 píxeles de entrenamiento por clase.
                   Ideal 500–1000 píxeles por clase.
  ✔ DISTRIBUCIÓN  : distribuye los polígonos por TODA la imagen,
                   no solo en un sector. El modelo debe ver
                   variabilidad espectral real de cada clase.
  ✔ EVITA BORDES  : no digitalices en la transición entre clases.
                   Los píxeles mixtos contaminan el entrenamiento.
  ✔ CLASES RARAS  : si una clase tiene pocos píxeles (ej. urbano),
                   usa más polígonos aunque sean pequeños.
                   El script usa class_weight='balanced' para compensar.
  ✔ NUBES         : incluye nubes gruesas, nubes delgadas y bordes
                   de nubes. Evita confundir sombra de nube (oscura)
                   con ríos o suelo húmedo.
  ✔ AGUA vs NUBES : ambas tienen MNDWI alto. Diferéncialas con B2
                   (Blue): nubes tienen B2 muy alto (~0.25–0.50),
                   agua tiene B2 bajo (~0.02–0.10).
  ✔ BALANCEO      : el script aplica class_weight='balanced' y
                   StratifiedKFold. Aun así, si una clase tiene
                   < 50 píxeles, agrega más muestras.
  ✔ VALIDACIÓN    : revisa la matriz de confusión. Si hay mucha
                   confusión entre dos clases, agrega muestras
                   más "puras" de esas dos clases.
"""

# Forzar PROJ de Python (evita conflicto con PostgreSQL/PostGIS)
import os
import pyproj as _pyproj
os.environ['PROJ_DATA']    = _pyproj.datadir.get_data_dir()
os.environ['PROJ_NETWORK'] = 'OFF'

import numpy as np
import rasterio
from rasterio.features import rasterize
import geopandas as gpd
import joblib
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, cross_val_score, GridSearchCV
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, ConfusionMatrixDisplay)
from sklearn.preprocessing import LabelEncoder

# =============================================================================
# CONFIGURACIÓN — Editar solo esta sección
# =============================================================================

# Cada entrada es un par (imagen_sentinel2, shapefile_de_muestras).
# Para reentrenar con una nueva zona: agrega otro par a la lista.
# Todas las imágenes deben ser Sentinel-2 de 6 bandas (misma configuración).
FUENTES_ENTRENAMIENTO = [
    (
        r"C:\Users\sebas\OneDrive\Documentos\ANT\2026-01\20260413\MULTIBANDA\multibanda_S2_2026_2026_SIN_NODATA_SR.tif",
        r"C:\Users\sebas\OneDrive\Documentos\ANT\MULTITEMPORAL\CODIGO_MULTITEMPORAL\CODIGOS_FULL\shp_entrenamiento\Muestras_Entrenamiento_PROJ.shp",
    ),
    # Agrega más pares aquí cuando tengas nueva zona/imagen:
    # (
    #     r"C:\ruta\nueva_imagen.tif",
    #     r"C:\ruta\nuevas_muestras.shp",
    # ),
]

OUTPUT_DIR    = r"C:\Users\sebas\OneDrive\Documentos\ANT\MULTITEMPORAL\CODIGO_MULTITEMPORAL\CODIGOS_FULL\MODELOS"
CLASS_FIELD   = "Clase"

# Si el shapefile tiene el CRS mal etiquetado (pasa con ArcGIS + Project tool).
# Opciones: None (comportamiento normal) | "EPSG:32618" | "EPSG:4326" | etc.
FORCE_SHP_CRS = "EPSG:32618"

# Parámetros
SCALE_FACTOR   = 0.0001    # Reflectancia S2: 0–10000 → 0.0–1.0
TEST_SIZE      = 0.25      # 25% para prueba final
N_FOLDS        = 5         # Folds de validación cruzada
RANDOM_STATE   = 42

# =============================================================================
# NOMENCLATURA — 7 clases (modelo actualizado)
# =============================================================================

CLC_MAPPING = {
    1: "3.1.1 Bosque denso",
    2: "1.1.2 Tejido urbano discontinuo",
    3: "5.1.1 Ríos y corrientes de agua",
    4: "4.1.1 Humedales",
    5: "3.3.2 Zonas desnudas o degradadas"
}

BAND_NAMES = ['B2', 'B3', 'B4', 'B8', 'B11', 'B12', 'NDVI', 'MNDWI', 'NDBI']

# =============================================================================
# UTILIDADES
# =============================================================================

def safe_div(a, b):
    with np.errstate(divide='ignore', invalid='ignore'):
        out = np.full_like(a, np.nan, dtype=np.float32)
        ok  = (b != 0) & ~np.isnan(a) & ~np.isnan(b)
        out[ok] = a[ok] / b[ok]
    return out


# =============================================================================
# PASO 1 — Calcular índices y armar imagen de 9 bandas en memoria
# =============================================================================

def cargar_imagen_con_indices(image_path: str):
    """
    Carga la imagen Sentinel-2 de 6 bandas, aplica escala de reflectancia
    y calcula NDVI, MNDWI, NDBI. Devuelve array (9, H, W) y metadata.
    """
    print("[1/4] Cargando imagen y calculando índices...")

    with rasterio.open(image_path) as src:
        meta      = src.meta.copy()
        transform = src.transform
        crs       = src.crs
        nodata    = src.nodata
        raw       = src.read().astype(np.float32)  # (6, H, W)

    bands = raw * SCALE_FACTOR  # escala reflectancia
    B2, B3, B4, B8, B11, B12 = bands

    NDVI  = safe_div(B8 - B4,  B8 + B4)
    MNDWI = safe_div(B3 - B11, B3 + B11)
    NDBI  = safe_div(B11 - B8, B11 + B8)

    # Máscara nodata
    invalid = np.zeros(B2.shape, dtype=bool)
    if nodata is not None:
        for b in bands:
            invalid |= (b / SCALE_FACTOR == nodata)
    invalid |= np.all(bands == 0, axis=0)

    for arr in [B2, B3, B4, B8, B11, B12, NDVI, MNDWI, NDBI]:
        arr[invalid] = np.nan

    image_9b = np.stack([B2, B3, B4, B8, B11, B12, NDVI, MNDWI, NDBI], axis=0)

    print(f"    Imagen cargada: {image_9b.shape[1]}×{image_9b.shape[2]} px, 9 bandas")
    print(f"    Píxeles inválidos (nodata/borde): {invalid.sum():,}")
    return image_9b, meta, transform, crs


# =============================================================================
# PASO 2 — Extraer píxeles de entrenamiento desde shapefile
# =============================================================================

def extraer_muestras(image_9b: np.ndarray, transform, crs,
                     shp_path: str) -> tuple:
    """
    Rasteriza los polígonos de entrenamiento y extrae los valores
    de píxeles válidos para cada clase.

    Retorna: X (n_samples, 9), y (n_samples,)
    """
    print("[2/4] Extrayendo muestras de entrenamiento del shapefile...")

    gdf = gpd.read_file(shp_path)

    print(f"    CRS raster    : {crs}")
    print(f"    CRS shapefile : {gdf.crs}")

    if gdf.crs is None:
        raise ValueError("El shapefile no tiene CRS definido. Asígnalo en ArcGIS antes de exportar.")

    if FORCE_SHP_CRS:
        # Fuerza el CRS sin reproyectar (coordenadas correctas, etiqueta CRS incorrecta)
        gdf = gdf.set_crs(FORCE_SHP_CRS, allow_override=True)
        print(f"    CRS forzado a {FORCE_SHP_CRS} (sin reproyectar coordenadas)")

    if gdf.crs != crs:
        gdf = gdf.to_crs(crs)
        print(f"    Shapefile reproyectado a CRS del raster.")

    # Diagnóstico de extensiones — deben solapar
    from rasterio.transform import array_bounds
    r_bounds = array_bounds(h := image_9b.shape[1], w := image_9b.shape[2], transform)
    s_bounds = gdf.total_bounds  # (minx, miny, maxx, maxy)
    print(f"    Extensión raster    : {r_bounds}")
    print(f"    Extensión shapefile : {s_bounds}")

    overlap_x = r_bounds[0] < s_bounds[2] and s_bounds[0] < r_bounds[2]
    overlap_y = r_bounds[1] < s_bounds[3] and s_bounds[1] < r_bounds[3]
    if not (overlap_x and overlap_y):
        raise ValueError(
            "El shapefile NO solapa con el raster después de reproyectar.\n"
            "Verifica que en ArcGIS el shapefile esté guardado con el CRS correcto."
        )

    if CLASS_FIELD not in gdf.columns:
        raise ValueError(f"El shapefile no tiene el campo '{CLASS_FIELD}'. "
                         f"Campos disponibles: {list(gdf.columns)}")

    h, w = image_9b.shape[1], image_9b.shape[2]
    X_list, y_list = [], []

    for clase_id, grupo in gdf.groupby(CLASS_FIELD):
        # Rasterizar polígonos de esta clase directamente sobre la grilla del raster
        shapes_iter = (
            (geom, 1)
            for geom in grupo.geometry
            if geom is not None and not geom.is_empty
        )
        burned = rasterize(
            shapes_iter,
            out_shape=(h, w),
            transform=transform,
            fill=0,
            dtype=np.uint8,
            all_touched=False,
        )

        pixel_mask = burned == 1

        if not np.any(pixel_mask):
            print(f"    AVISO: clase {clase_id} no intersecta el raster "
                  f"(¿CRS incorrecto en el shapefile?).")
            continue

        # Extraer valores de las 9 bandas en los píxeles quemados
        pixels = image_9b[:, pixel_mask].T  # (n_px, 9)

        # Filtrar píxeles con NaN (nodata)
        valid = ~np.any(np.isnan(pixels), axis=1)
        pixels = pixels[valid]

        if len(pixels) == 0:
            print(f"    AVISO: clase {clase_id} tiene píxeles pero todos son nodata.")
            continue

        X_list.append(pixels)
        y_list.append(np.full(len(pixels), clase_id, dtype=np.int32))

        clase_nombre = CLC_MAPPING.get(int(clase_id), str(clase_id))
        print(f"    Clase {clase_id} ({clase_nombre}): {len(pixels):,} píxeles")

    X = np.vstack(X_list)
    y = np.concatenate(y_list)

    # Estadísticas de balance
    print(f"\n    Total muestras: {len(y):,}")
    print("    Balance de clases:")
    unique, counts = np.unique(y, return_counts=True)
    for u, c in zip(unique, counts):
        pct = c / len(y) * 100
        barra = "█" * int(pct / 2)
        print(f"      Clase {u}: {c:5,} px  {barra} {pct:.1f}%")

    # CONSEJO: si alguna clase tiene < 150 px, agrega más muestras
    clase_minima = counts.min()
    if clase_minima < 150:
        clase_critica = unique[counts.argmin()]
        print(f"\n    ⚠ AVISO: clase {clase_critica} tiene solo {clase_minima} px.")
        print(f"      Recomendado: agregar más polígonos de clase {clase_critica} al shapefile.")

    return X, y


# =============================================================================
# PASO 3 — Entrenar modelo con validación cruzada y búsqueda de hiperparámetros
# =============================================================================

def entrenar_modelo(X: np.ndarray, y: np.ndarray, output_dir: str):
    """
    Entrena un Random Forest con:
      - StratifiedKFold (N_FOLDS pliegues)
      - class_weight='balanced' para compensar desbalance
      - GridSearchCV sobre hiperparámetros clave
      - Evaluación con matriz de confusión y reporte por clase

    Retorna: modelo entrenado sobre TODOS los datos.
    """
    from sklearn.model_selection import train_test_split

    print(f"\n[3/4] Entrenando modelo Random Forest ({N_FOLDS}-fold CV)...")

    # Split final para evaluación imparcial
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_STATE
    )
    print(f"    Train: {len(X_train):,} | Test: {len(X_test):,}")

    # ── Búsqueda de hiperparámetros ──────────────────────────────────────
    # Espacio reducido pero eficaz para imágenes de teledetección
    param_grid = {
        'n_estimators':  [200, 400],
        'max_depth':     [None, 30],
        'max_features':  ['sqrt', 0.5],       # sqrt = clásico RF; 0.5 = más informativo con 9 bandas
        'min_samples_leaf': [1, 3],
    }

    rf_base = RandomForestClassifier(
        class_weight='balanced',   # fundamental para clases desbalanceadas
        oob_score=True,            # estimación rápida sin CV
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )

    cv = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=RANDOM_STATE)

    print("    Buscando mejores hiperparámetros (GridSearchCV)...")
    grid_search = GridSearchCV(
        rf_base, param_grid,
        cv=cv,
        scoring='balanced_accuracy',   # mejor métrica para clases desbalanceadas
        n_jobs=-1,
        verbose=1,
        refit=True,
    )
    grid_search.fit(X_train, y_train)

    best_params = grid_search.best_params_
    best_cv     = grid_search.best_score_
    print(f"\n    Mejores parámetros : {best_params}")
    print(f"    Balanced accuracy CV: {best_cv:.4f} ({best_cv*100:.1f}%)")

    # ── Evaluación en test set ────────────────────────────────────────────
    best_model = grid_search.best_estimator_
    y_pred     = best_model.predict(X_test)

    acc     = accuracy_score(y_test, y_pred)
    oob_est = best_model.oob_score_

    print(f"    Accuracy test set   : {acc:.4f} ({acc*100:.1f}%)")
    print(f"    OOB score estimado  : {oob_est:.4f} ({oob_est*100:.1f}%)")

    # Reporte por clase
    clases_presentes = sorted(np.unique(y))
    nombres_clases   = [CLC_MAPPING.get(c, str(c)) for c in clases_presentes]
    print("\n" + classification_report(y_test, y_pred,
                                       labels=clases_presentes,
                                       target_names=nombres_clases))

    # ── Gráficas ──────────────────────────────────────────────────────────
    _graficar_confusion(y_test, y_pred, clases_presentes, nombres_clases, output_dir)
    _graficar_importancia(best_model, output_dir)

    # ── Reentrenar sobre TODOS los datos con los mejores parámetros ───────
    print("    Reentrenando sobre el 100% de los datos...")
    modelo_final = RandomForestClassifier(
        **best_params,
        class_weight='balanced',
        oob_score=True,
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    modelo_final.fit(X, y)
    print(f"    OOB score final (100% datos): {modelo_final.oob_score_:.4f}")

    return modelo_final, best_params, best_cv


def _graficar_confusion(y_test, y_pred, clases, nombres, output_dir):
    cm = confusion_matrix(y_test, y_pred, labels=clases, normalize='true')

    fig, ax = plt.subplots(figsize=(10, 8))
    sns.heatmap(cm, annot=True, fmt='.2f', cmap='Blues',
                xticklabels=nombres, yticklabels=nombres, ax=ax,
                linewidths=0.5, linecolor='gray')
    ax.set_xlabel("Predicho", fontsize=12)
    ax.set_ylabel("Real",     fontsize=12)
    ax.set_title("Matriz de Confusión (normalizada por fila)", fontsize=13, fontweight='bold')
    plt.xticks(rotation=35, ha='right', fontsize=9)
    plt.yticks(rotation=0,  fontsize=9)
    plt.tight_layout()

    out = os.path.join(output_dir, "Confusion_Matrix.png")
    plt.savefig(out, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"    Matriz de confusión: {out}")


def _graficar_importancia(model, output_dir):
    importancias = model.feature_importances_
    idx          = np.argsort(importancias)[::-1]

    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(np.array(BAND_NAMES)[idx], importancias[idx],
                  color='steelblue', edgecolor='white')
    ax.set_title("Importancia de Variables (Mean Decrease Impurity)",
                 fontsize=13, fontweight='bold')
    ax.set_ylabel("Importancia relativa")
    ax.set_xlabel("Banda / Índice")

    for bar, val in zip(bars, importancias[idx]):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.002,
                f"{val:.3f}", ha='center', va='bottom', fontsize=9)

    plt.tight_layout()
    out = os.path.join(output_dir, "Feature_Importance.png")
    plt.savefig(out, dpi=200, bbox_inches='tight')
    plt.close()
    print(f"    Importancia bandas : {out}")


# =============================================================================
# PASO 4 — Guardar modelo y metadatos
# =============================================================================

def guardar_modelo(modelo, best_params, best_cv, output_dir):
    model_path = os.path.join(output_dir, "Best_RandomForest_Model.pkl")
    joblib.dump(modelo, model_path)
    print(f"\n[4/4] Modelo guardado: {model_path}")

    # Guardar metadatos en CSV
    meta_path = os.path.join(output_dir, "Model_Metadata.csv")
    meta_df = pd.DataFrame([{
        "modelo":         "RandomForestClassifier",
        "clases":         list(CLC_MAPPING.keys()),
        "bandas":         BAND_NAMES,
        "cv_folds":       N_FOLDS,
        "balanced_acc_cv": round(best_cv, 4),
        "oob_score":      round(modelo.oob_score_, 4),
        **best_params,
    }])
    meta_df.to_csv(meta_path, index=False)
    print(f"    Metadatos guardados: {meta_path}")

    # Imprimir mapping de clases para referencia
    print("\n    Clases del modelo:")
    for k, v in CLC_MAPPING.items():
        print(f"      {k} → {v}")


# =============================================================================
# EJECUCIÓN PRINCIPAL
# =============================================================================

if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Paso 1+2: extraer muestras de cada par imagen+shapefile y combinarlas
    X_total, y_total = [], []

    for idx, (imagen, shp) in enumerate(FUENTES_ENTRENAMIENTO, start=1):
        print(f"\n--- Fuente {idx}/{len(FUENTES_ENTRENAMIENTO)}: {os.path.basename(imagen)} ---")
        image_9b, _, transform, crs = cargar_imagen_con_indices(imagen)
        X_i, y_i = extraer_muestras(image_9b, transform, crs, shp)
        X_total.append(X_i)
        y_total.append(y_i)

    X = np.vstack(X_total)
    y = np.concatenate(y_total)
    print(f"\nTotal combinado: {len(y):,} muestras de {len(FUENTES_ENTRENAMIENTO)} fuente(s)")

    # Paso 3: entrenar
    modelo, best_params, best_cv = entrenar_modelo(X, y, OUTPUT_DIR)

    # Paso 4: guardar
    guardar_modelo(modelo, best_params, best_cv, OUTPUT_DIR)

    print("\n" + "=" * 55)
    print("Entrenamiento completado.")
    print(f"Modelo listo para usar en: 10. COBERTURAS.py")
    print("=" * 55)
