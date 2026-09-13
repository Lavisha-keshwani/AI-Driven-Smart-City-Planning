"""
Centralised configuration.

Every filesystem path, API key and model identifier is resolved here, from
environment variables where available and from repository-relative defaults
otherwise. Nothing else in the codebase may hard-code an absolute path.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# ── Repository layout ────────────────────────────────────────────────────────
_THIS_DIR = Path(__file__).resolve().parent          # backend/app/core/
APP_DIR = _THIS_DIR.parent                           # backend/app/
BACKEND_DIR = APP_DIR.parent                         # backend/
PROJECT_ROOT = BACKEND_DIR.parent                    # repository root

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(BACKEND_DIR / ".env", override=False)


def _path(env_var: str, default: Path) -> Path:
    """Read a path from the environment, falling back to a repo-relative default."""
    raw = os.getenv(env_var)
    return Path(raw).expanduser().resolve() if raw else default


def _flag(env_var: str, default: bool) -> bool:
    raw = os.getenv(env_var)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# ── Roots ────────────────────────────────────────────────────────────────────
MODELS_ROOT = _path("MODELS_ROOT", PROJECT_ROOT / "models")
DATA_ROOT = _path("DATA_ROOT", MODELS_ROOT)

# ── Model 1 — Surface Water Monitoring ───────────────────────────────────────
M1_ROOT = _path("MODEL1_ROOT", MODELS_ROOT / "model1" / "smart-model1-surface-water")
SURFACE_WATER_MODEL_PATH = _path(
    "SURFACE_WATER_MODEL_PATH",
    M1_ROOT / "outputs" / "models" / "BEST_MODEL_xgboost.joblib",
)
M1_METRICS_DIR = _path("MODEL1_METRICS_DIR", M1_ROOT / "outputs" / "metrics")
M1_DATASET = _path("MODEL1_DATASET", M1_ROOT / "model1" / "final_grid_dataset_water.csv")
M1_ALGORITHM = os.getenv("MODEL1_ALGORITHM", "xgboost")

# ── Model 2 — Urban Expansion Suitability ────────────────────────────────────
M2_ROOT = _path("MODEL2_ROOT", MODELS_ROOT / "model2" / "model2_urban_expansion")
URBAN_MODEL_PATH = _path("URBAN_MODEL_PATH", M2_ROOT / "best_model_model2.pkl")
M2_FEATURES_JSON = _path("MODEL2_FEATURES_JSON", M2_ROOT / "feature_list.json")
M2_METRICS_CSV = _path("MODEL2_METRICS_CSV", M2_ROOT / "metrics_comparison.csv")

# ── Model 3 — Urban Flood Risk ───────────────────────────────────────────────
M3_ROOT = _path("MODEL3_ROOT", MODELS_ROOT / "model3" / "smart-model3-flood-risk")
FLOOD_MODEL_PATH = _path(
    "FLOOD_MODEL_PATH",
    M3_ROOT / "outputs" / "models" / "BEST_MODEL_random_forest.joblib",
)
M3_METRICS_DIR = _path("MODEL3_METRICS_DIR", M3_ROOT / "outputs" / "metrics")
M3_DATASET = _path("MODEL3_DATASET", M3_ROOT / "model3" / "final_grid_dataset.csv")
M3_ALGORITHM = os.getenv("MODEL3_ALGORITHM", "random_forest")

# ── Model 4 — Microplastic Screening ─────────────────────────────────────────
M4_ROOT = _path(
    "MODEL4_ROOT",
    MODELS_ROOT / "microplastic" / "Smart-city-microplastic" / "models"
    / "model4_microplastic_screening",
)
MICROPLASTIC_MODEL_PATH = _path("MICROPLASTIC_MODEL_PATH", M4_ROOT / "final_model_resnet18.pt")
M4_CONFIG_JSON = _path("MODEL4_CONFIG_JSON", M4_ROOT / "config.json")
M4_CV_RESULTS_CSV = _path("MODEL4_CV_RESULTS_CSV", M4_ROOT / "cv_results.csv")

# ── Shared geospatial source layers (Model 2 feature assembly) ───────────────
# Model 2 ships no pre-merged dataset, so its feature table is rebuilt from the
# same source layers the training pipeline consumed. Those layers live inside
# the Model 3 data bundle; both models share the same 1 km analysis grid.
_M3_DATA = M3_ROOT / "model3"
GRID_METADATA_CSV = _path(
    "GRID_METADATA_CSV",
    _M3_DATA / "SmartCityAI_city_boundaries" / "city_grid_1km_metadata.csv",
)
GHSL_DIR = _path("GHSL_DIR", _M3_DATA / "SmartCityAI_GHSL_FIXED" / "SmartCityAI_GHSL_FIXED")
OPEN_BUILDINGS_DIR = _path("OPEN_BUILDINGS_DIR", _M3_DATA / "smart_city_ai-OpenBuildings")
SRTM_CSV = _path(
    "SRTM_CSV",
    _M3_DATA / "smart_city_ai-SRTM_DEM" / "smart_city_ai-SRTM_DEM" / "srtm_dem_features.csv",
)
CHIRPS_DIR = _path("CHIRPS_DIR", _M3_DATA / "smart_city_ai-CHIRPS" / "smart_city_ai-CHIRPS")
SURFACE_WATER_LAYER_CSV = _path(
    "SURFACE_WATER_LAYER_CSV",
    _M3_DATA / "SmartCityAI_SurfaceWater_FIXED" / "SmartCityAI_SurfaceWater_FIXED"
    / "surfacewater_features_1km_GSW_FIXED_v3.csv",
)

# Model 2 forward-validation epochs, mirroring its feature_list.json.
M2_T0_YEAR = int(os.getenv("MODEL2_T0_YEAR", "2000"))
M2_T1_YEAR = int(os.getenv("MODEL2_T1_YEAR", "2020"))
M2_RAINFALL_YEAR = int(os.getenv("MODEL2_RAINFALL_YEAR", "2020"))

# ── Common spatial framework ─────────────────────────────────────────────────
GRID_CELL_SIZE_M = int(os.getenv("GRID_CELL_SIZE_M", "1000"))
GRID_CRS = os.getenv("GRID_CRS", "EPSG:4326")

# ── Classification thresholds (documented in docs/model_cards/) ───────────────
# Flood-risk bands sit on top of the tuned operating threshold that the training
# run selected by maximising its composite validation score.
FLOOD_RISK_MODERATE_THRESHOLD = float(os.getenv("FLOOD_RISK_MODERATE_THRESHOLD", "0.30"))
FLOOD_RISK_HIGH_THRESHOLD = float(os.getenv("FLOOD_RISK_HIGH_THRESHOLD", "0.60"))

# Urban suitability: Model 2 is a 3-class classifier, so the continuous score is
# the expected class value P(Yellow)*0.5 + P(Green)*1.0, which is monotone in
# development favourability and bounded to [0, 1]. The GREEN/YELLOW/RED label
# comes from argmax of the class probabilities by default (the decision rule the
# model was validated under); URBAN_CLASS_FROM_SCORE=true switches the label to
# score thresholds instead.
URBAN_CLASS_FROM_SCORE = _flag("URBAN_CLASS_FROM_SCORE", False)
URBAN_SCORE_GREEN_THRESHOLD = float(os.getenv("URBAN_SCORE_GREEN_THRESHOLD", "0.66"))
URBAN_SCORE_YELLOW_THRESHOLD = float(os.getenv("URBAN_SCORE_YELLOW_THRESHOLD", "0.33"))

# Surface-water occurrence percentage that defined the Model 1 training target.
WATER_OCCURRENCE_THRESHOLD_PCT = float(os.getenv("WATER_OCCURRENCE_THRESHOLD_PCT", "25"))

# ── Groq LLM ─────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL: str = (
    os.getenv("GROQ_MODEL") or os.getenv("GROQ_PRIMARY_MODEL") or "openai/gpt-oss-120b"
)
GROQ_FALLBACK_MODEL: str = os.getenv("GROQ_FALLBACK_MODEL", "")
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.3"))
LLM_TIMEOUT: int = int(os.getenv("LLM_TIMEOUT", "60"))
LLM_ENABLED: bool = _flag("LLM_ENABLED", True)

# ── NASA POWER ───────────────────────────────────────────────────────────────
NASA_POWER_DAILY_URL = os.getenv(
    "NASA_POWER_DAILY_URL", "https://power.larc.nasa.gov/api/temporal/daily/point"
)
NASA_POWER_CLIMATOLOGY_URL = os.getenv(
    "NASA_POWER_CLIMATOLOGY_URL", "https://power.larc.nasa.gov/api/temporal/climatology/point"
)
NASA_POWER_TIMEOUT = int(os.getenv("NASA_POWER_TIMEOUT", "30"))
NASA_POWER_CACHE_SIZE = int(os.getenv("NASA_POWER_CACHE_SIZE", "256"))

# ── Uploads ──────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024)))
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

# ── Server ───────────────────────────────────────────────────────────────────
CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
