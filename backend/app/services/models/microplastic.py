"""
Microplastic Screening — deep-learning image classifier.

The trained artifact is a ResNet18 (timm, ImageNet-pretrained, so transfer
learning) fine-tuned on the HMPD dataset. HMPD ships image-level labels rather
than bounding boxes or masks, so the task implemented here is binary
CLASSIFICATION — what the annotations actually support. Detection and segmentation
heads are not offered, because they would need box or mask annotations this
dataset does not contain.

INPUT CONSTRUCTION — this matters, and was verified empirically.
HMPD images each particle three times under polarisation microscopy:

    R — reflectance
    A — angle of polarisation
    P — degree of polarisation

The three greyscale measurements are stacked into the network's three input
channels at 96x96. Feeding only the reflectance channel replicated across RGB
was measured against HMPD ground truth at 45.0% accuracy (chance, recall 0.008),
while the correct R/A/P stack scored 97.8% on the same particles, against the
92.8% cross-validation mean the training run reported. The API therefore requires
all three channels, and says so rather than silently scoring a single image.

SCIENTIFIC SCOPE — carried in every response payload:
this is image-based screening for the visual signature of candidate microplastic
particles. It does not identify polymer type, does not determine chemical
composition, and does not measure absolute concentration. Those require
spectroscopy (FTIR or Raman) on a prepared sample.
"""

from __future__ import annotations

import io
import logging

import numpy as np

from app.core import config
from app.core.errors import InferenceError, InvalidInputError
from app.services.models import registry

logger = logging.getLogger(__name__)

MODEL_KEY = "model4_microplastic"
MODEL_NAME = "Microplastic Screening"

DISCLAIMER = (
    "Image-based screening only; does not determine chemical composition, polymer "
    "type, or absolute concentration. Confirmation requires FTIR or Raman "
    "spectroscopy on a prepared sample."
)

CHANNEL_NAMES = ("R", "A", "P")
CHANNEL_MEANING = {
    "R": "reflectance",
    "A": "angle of polarisation",
    "P": "degree of polarisation",
}

CLASS_NAMES = {0: "no_microplastic_detected", 1: "microplastic_candidate"}

_IMAGENET_MEAN = np.float32([0.485, 0.456, 0.406])
_IMAGENET_STD = np.float32([0.229, 0.224, 0.225])


def image_size() -> int:
    return int(registry.model4_config().get("img_size", 96))


def _validate_upload(image_bytes: bytes, filename: str | None, label: str) -> None:
    if not image_bytes:
        raise InvalidInputError(f"The uploaded {label} image is empty.")
    if len(image_bytes) > config.MAX_UPLOAD_BYTES:
        raise InvalidInputError(
            f"The {label} image is {len(image_bytes) / 1_048_576:.1f} MB, above the "
            f"{config.MAX_UPLOAD_BYTES / 1_048_576:.0f} MB limit.",
            detail={"max_bytes": config.MAX_UPLOAD_BYTES, "channel": label},
        )
    if filename:
        # Compare only the extension; the client filename is never used as a path.
        suffix = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
        if suffix not in config.ALLOWED_IMAGE_SUFFIXES:
            raise InvalidInputError(
                f"Unsupported image type '{suffix or filename}' for the {label} channel.",
                detail={"allowed": sorted(config.ALLOWED_IMAGE_SUFFIXES), "channel": label},
            )


def _open(image_bytes: bytes, label: str):
    from PIL import Image, UnidentifiedImageError

    try:
        image = Image.open(io.BytesIO(image_bytes))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidInputError(
            f"The uploaded {label} file could not be decoded as an image.",
            detail={"reason": str(exc), "channel": label},
        ) from exc
    return image


def _to_plane(image, size: int) -> np.ndarray:
    """One greyscale measurement plane, resized and scaled to [0, 1]."""
    from PIL import Image as PILImage

    grey = image.convert("L").resize((size, size), PILImage.BILINEAR)
    return np.asarray(grey, dtype=np.float32) / 255.0


def _normalise(planes: np.ndarray):
    """Apply the training normalisation to a (3, H, W) stack."""
    import torch

    stack = (planes - _IMAGENET_MEAN[:, None, None]) / _IMAGENET_STD[:, None, None]
    return torch.from_numpy(stack[None, ...])


def _infer(tensor) -> np.ndarray:
    import torch

    model = registry.microplastic_model()
    try:
        with torch.no_grad():
            return torch.softmax(model(tensor), dim=1).squeeze(0).numpy()
    except Exception as exc:  # noqa: BLE001
        raise InferenceError(
            "Microplastic screening inference failed.", detail={"reason": str(exc)}
        ) from exc


def _build_result(
    probabilities: np.ndarray, input_info: dict, warnings: list[str]
) -> dict:
    predicted = int(np.argmax(probabilities))
    confidence = float(probabilities[predicted])
    detected = predicted == 1

    # HMPD is labelled per image, so a positive result localises to the whole field
    # of view. Never report a particle count the model cannot actually see.
    detections = (
        [{
            "label": CLASS_NAMES[1],
            "confidence": round(confidence, 4),
            "region": "whole_image",
            "note": (
                "HMPD carries image-level labels only, so the detection covers the "
                "whole field of view; no per-particle localisation is available."
            ),
        }]
        if detected else []
    )

    result = {
        "model": MODEL_NAME,
        "model_key": MODEL_KEY,
        "architecture": registry.model4_config().get("architecture", "resnet18"),
        "task": "binary image classification (screening)",
        "detections": detections,
        "count": len(detections),
        "confidence": round(confidence, 4),
        "classification": CLASS_NAMES[predicted],
        "microplastic_detected": detected,
        "class_probabilities": {
            CLASS_NAMES[i]: round(float(p), 4) for i, p in enumerate(probabilities)
        },
        "input": input_info,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }
    logger.info(
        "Model 4: %s (confidence %.4f, mode=%s)",
        result["classification"], confidence, input_info.get("mode"),
    )
    return result


def analyze_polarimetric(
    r_bytes: bytes,
    a_bytes: bytes,
    p_bytes: bytes,
    *,
    filenames: dict[str, str | None] | None = None,
) -> dict:
    """Screen a particle from its three polarimetric channels.

    This is the input construction the model was trained on and the only one that
    reproduces its reported accuracy.
    """
    names = filenames or {}
    payloads = {"R": r_bytes, "A": a_bytes, "P": p_bytes}
    for channel, data in payloads.items():
        _validate_upload(data, names.get(channel), channel)

    size = image_size()
    images = {c: _open(data, c) for c, data in payloads.items()}

    sizes = {c: img.size for c, img in images.items()}
    warnings = []
    if len(set(sizes.values())) > 1:
        warnings.append(
            "The three channel images have different pixel dimensions "
            f"({sizes}); they were each resized to {size}x{size}, but they may not "
            "be co-registered views of the same particle."
        )

    planes = np.stack([_to_plane(images[c], size) for c in CHANNEL_NAMES], axis=0)
    probabilities = _infer(_normalise(planes))

    return _build_result(
        probabilities,
        {
            "mode": "polarimetric_triplet",
            "channels": {c: CHANNEL_MEANING[c] for c in CHANNEL_NAMES},
            "model_input_size": size,
            "received_sizes": {c: list(s) for c, s in sizes.items()},
        },
        warnings,
    )


def analyze_composite(image_bytes: bytes, *, filename: str | None = None) -> dict:
    """Screen an already-composited 3-channel image.

    For callers who have stacked R/A/P into a single RGB file themselves. The
    channel order is assumed to be R, A, P, and that assumption is reported. A
    single-channel upload is rejected rather than replicated, because replicating
    reflectance across all three channels scores at chance.
    """
    _validate_upload(image_bytes, filename, "composite")
    image = _open(image_bytes, "composite")

    if image.mode in {"L", "1", "I", "F"}:
        raise InvalidInputError(
            "This is a single-channel image. The model needs three polarimetric "
            "channels (reflectance, angle of polarisation, degree of polarisation). "
            "Replicating one channel across all three scores at chance level, so the "
            "request was rejected rather than returning a meaningless result.",
            detail={
                "received_mode": image.mode,
                "remedy": (
                    "Upload the R, A and P images to POST /api/microplastics/analyze, "
                    "or composite them into one 3-channel image in that order."
                ),
            },
        )

    from PIL import Image as PILImage

    size = image_size()
    rgb = image.convert("RGB").resize((size, size), PILImage.BILINEAR)
    planes = np.transpose(np.asarray(rgb, dtype=np.float32) / 255.0, (2, 0, 1))
    probabilities = _infer(_normalise(planes))

    return _build_result(
        probabilities,
        {
            "mode": "composite_3_channel",
            "assumed_channel_order": list(CHANNEL_NAMES),
            "model_input_size": size,
            "received_mode": image.mode,
            "received_size": list(image.size),
        },
        [
            "Channel order was assumed to be R, A, P. If the composite was stacked in "
            "a different order, the result is unreliable."
        ],
    )


def metrics() -> dict:
    """Validation evidence for the microplastic screening model."""
    cfg = registry.model4_config()
    cv = registry.model4_cv_results()

    return {
        "model": MODEL_NAME,
        "architecture": cfg.get("architecture"),
        "task": "binary image classification (screening)",
        "transfer_learning": "ImageNet-pretrained ResNet18 backbone, fine-tuned on HMPD",
        "training_data": cfg.get("train_data"),
        "input_channels": cfg.get("channels"),
        "input_size": cfg.get("img_size"),
        "validation_strategy": (
            "Stratified cross-validation over the balanced HMPD training split. "
            "Reported figures are the cross-validation means with their spread."
        ),
        "cross_validation": {
            "mean_accuracy": cfg.get("cv_mean_accuracy"),
            "std_accuracy": cfg.get("cv_std_accuracy"),
            "mean_f1": cfg.get("cv_mean_f1"),
            "mean_roc_auc": cfg.get("cv_mean_roc_auc"),
        },
        "per_fold": (
            cv.replace({np.nan: None}).to_dict(orient="records") if cv is not None else None
        ),
        "metrics_source": "training run config.json and cv_results.csv",
        "disclaimer": DISCLAIMER,
        "limitations": [
            "Screening only: the model flags a visual signature. It cannot identify "
            "polymer type or chemical composition, which require FTIR or Raman.",
            "It reports no concentration. Particles per litre depends on sample volume "
            "and preparation protocol, neither of which is visible in an image.",
            "HMPD provides image-level labels, so no per-particle localisation or count "
            "is possible; detection and segmentation heads were not built for this reason.",
            "Inputs must be polarimetric triplets (R/A/P) from polarisation microscopy. "
            "Ordinary photographs lack that signal; a single-channel upload is rejected.",
            "Cross-validation accuracy is measured within HMPD; performance on microscopy "
            "from a different instrument or preparation protocol is unvalidated.",
        ],
    }
