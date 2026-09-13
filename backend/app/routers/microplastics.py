"""
Microplastic screening endpoints.

The primary endpoint takes the three polarimetric channels the model was trained
on. That is not a convenience choice: feeding a single reflectance image instead
was measured at chance accuracy against HMPD ground truth, so accepting one image
silently would produce confident nonsense.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, UploadFile

from app.core import config
from app.core.errors import InvalidInputError
from app.schemas.responses import MetricsResponse, MicroplasticResponse
from app.services.models import microplastic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/microplastics", tags=["microplastics"])


# Content types that are definitely not images. A declared type is client-controlled
# and often absent or generic (curl sends .bmp as application/octet-stream), so it is
# only used to reject the obviously wrong. Authoritative validation is the file
# extension check plus an actual image decode, both in the service layer.
_REJECTED_CONTENT_PREFIXES = ("text/", "video/", "audio/", "application/json", "application/pdf")


async def _read(upload: UploadFile, label: str) -> bytes:
    """Read an upload, enforcing the size cap while streaming."""
    declared = (upload.content_type or "").lower()
    if declared.startswith(_REJECTED_CONTENT_PREFIXES):
        raise InvalidInputError(
            f"The {label} channel must be an image; received content type '{declared}'.",
            detail={"channel": label, "content_type": declared},
        )

    chunks, total = [], 0
    while chunk := await upload.read(64 * 1024):
        total += len(chunk)
        if total > config.MAX_UPLOAD_BYTES:
            raise InvalidInputError(
                f"The {label} image exceeds the "
                f"{config.MAX_UPLOAD_BYTES / 1_048_576:.0f} MB upload limit.",
                detail={"channel": label, "max_bytes": config.MAX_UPLOAD_BYTES},
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _safe_name(upload: UploadFile) -> str | None:
    """Take only the basename of a client-supplied filename.

    The name is used solely to check the extension; stripping any path component
    means a crafted filename cannot influence a path anywhere.
    """
    if not upload.filename:
        return None
    return upload.filename.replace("\\", "/").rsplit("/", 1)[-1]


@router.post("/analyze", response_model=MicroplasticResponse)
async def analyze(
    r_image: UploadFile = File(..., description="Reflectance (R) channel."),
    a_image: UploadFile = File(..., description="Angle-of-polarisation (A) channel."),
    p_image: UploadFile = File(..., description="Degree-of-polarisation (P) channel."),
):
    """Screen a particle from its three polarimetric microscopy channels.

    This is the input the model was trained on. The response carries the scientific
    scope disclaimer: screening only, no polymer identification, no concentration.
    """
    return microplastic.analyze_polarimetric(
        await _read(r_image, "R"),
        await _read(a_image, "A"),
        await _read(p_image, "P"),
        filenames={
            "R": _safe_name(r_image),
            "A": _safe_name(a_image),
            "P": _safe_name(p_image),
        },
    )


@router.post("/analyze-composite", response_model=MicroplasticResponse)
async def analyze_composite(
    image: UploadFile = File(..., description="A 3-channel image stacked in R, A, P order."),
):
    """Screen an already-composited 3-channel image.

    A single-channel upload is rejected: replicating one channel across three scores
    at chance level, so returning a result would be misleading.
    """
    return microplastic.analyze_composite(
        await _read(image, "composite"), filename=_safe_name(image)
    )


@router.get("/metrics", response_model=MetricsResponse)
def microplastic_metrics():
    """Cross-validation evidence, scope disclaimer and documented limitations."""
    return microplastic.metrics()
