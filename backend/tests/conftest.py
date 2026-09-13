"""
Shared test fixtures.

Two principles the suite holds to:

  * No test invents data. Grid ids, cities and images come from the real artifacts,
    discovered at collection time. If an artifact is missing, the tests that need it
    skip with a message naming what is absent, rather than passing against a stub.
  * No test needs Groq. The LLM is patched out by default, so the suite runs offline
    and deterministically. Tests that specifically exercise LLM handling patch
    `structured_call` themselves.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import config  # noqa: E402
from app.services.models import registry  # noqa: E402


# ── Artifact availability ────────────────────────────────────────────────────

def _models_ready() -> bool:
    status = registry.models_status()
    return status["all_models_loaded"] and status["all_datasets_present"]


requires_models = pytest.mark.skipif(
    not _models_ready(),
    reason=(
        "Trained model artifacts or feature datasets are unavailable. "
        "Check GET /api/models/status, or set the *_MODEL_PATH variables in .env."
    ),
)

requires_hmpd = pytest.mark.skipif(
    not (
        config.MODELS_ROOT / "microplastic" / "Smart-city-microplastic" / "HMPD-Gen"
        / "HMPD-Gen" / "images"
    ).is_dir(),
    reason="The HMPD image dataset is not present.",
)

requires_network = pytest.mark.skipif(
    __import__("os").environ.get("SMARTCITY_SKIP_NETWORK_TESTS") == "1",
    reason="Network tests disabled via SMARTCITY_SKIP_NETWORK_TESTS=1.",
)


# ── Real fixtures, discovered from the artifacts ─────────────────────────────

@pytest.fixture(scope="session")
def grid_cell() -> dict:
    """A real grid cell from the analysis grid."""
    from app.core.grid import grid_metadata

    row = grid_metadata().iloc[0]
    return {
        "grid_id": str(row["grid_id"]),
        "city": str(row["city"]),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
    }


@pytest.fixture(scope="session")
def sample_city(grid_cell) -> str:
    return grid_cell["city"]


@pytest.fixture(scope="session")
def hmpd_particles() -> dict[str, list[str]]:
    """Real HMPD particle ids that have all three polarimetric channels present.

    Returns `{"positive": [...], "negative": [...]}` using the dataset's own labels,
    so classification tests can check against ground truth.
    """
    import pandas as pd

    base = (
        config.MODELS_ROOT / "microplastic" / "Smart-city-microplastic"
        / "HMPD-Gen" / "HMPD-Gen"
    )
    gt = pd.read_csv(base / "gt.csv")
    available = {p.name for p in (base / "images").glob("*.bmp")}
    labels = dict(zip(gt["patchids"], gt["classes"]))

    complete = [
        pid for pid in gt["patchids"]
        if all(f"{pid}_{ch}.bmp" in available for ch in ("R", "A", "P"))
    ]
    return {
        "positive": [p for p in complete if labels[p] == 1][:5],
        "negative": [p for p in complete if labels[p] == 0][:5],
        "image_dir": base / "images",
    }


@pytest.fixture(scope="session")
def hmpd_image_dir(hmpd_particles) -> Path:
    return hmpd_particles["image_dir"]


# ── LLM isolation ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    """Disable the LLM for every test unless the test opts back in.

    The agents then take their deterministic fallback path, which is what makes the
    suite reproducible and runnable without a Groq key.
    """
    monkeypatch.setattr(config, "LLM_ENABLED", False)


@pytest.fixture
def stub_llm(monkeypatch):
    """Install a canned structured LLM response.

    Usage: `stub_llm(SchemaInstance)` makes every `structured_call` return it.
    """
    def install(result, *, model: str = "test-model"):
        def fake(prompt, schema, *, context):
            assert isinstance(result, schema), (
                f"stub_llm was given {type(result).__name__} but {context} "
                f"requested {schema.__name__}"
            )
            return result, {"source": "llm", "llm_model": model}

        from app.agents import llm

        monkeypatch.setattr(llm, "structured_call", fake)
        monkeypatch.setattr(config, "LLM_ENABLED", True)
        return fake

    return install


@pytest.fixture
def client():
    """A FastAPI test client with the app's exception handlers active."""
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
