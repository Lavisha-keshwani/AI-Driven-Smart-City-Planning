# Model Card — Microplastic Screening

## Purpose

Screen a polarisation-microscopy image for the **visual signature of a candidate
microplastic particle**.

## Scientific scope — read this first

> **Image-based screening only. This model does not determine chemical composition,
> polymer type, or absolute concentration. Confirmation requires FTIR or Raman
> spectroscopy on a prepared sample.**

This disclaimer is returned in **every** API response, not only in documentation.

What the model cannot do, and why:

| Claim | Why it is impossible here |
|---|---|
| Polymer identification (PE, PP, PET…) | Requires vibrational spectroscopy; polymers are not visually separable |
| Chemical composition | Not recoverable from an image at any resolution |
| Particles per litre | Depends on sample volume and preparation protocol, neither visible in an image |
| Particle count | HMPD labels are per-image, so no per-particle localisation exists |
| Analysis of an ordinary photograph | The model needs polarimetric channels an RGB camera does not capture |

## What this model is

**ResNet18** from `timm`, ImageNet-pretrained and fine-tuned on HMPD — transfer learning,
as the small dataset requires.

The task is **binary classification**, because that is what the annotations support. HMPD
ships image-level labels (`gt.csv`: `patchids`, `classes`), not bounding boxes or masks.
Detection and segmentation heads were therefore **not** built: doing so would have
required inventing annotations the dataset does not contain.

## Input — three polarimetric channels

HMPD images each particle three times under polarisation microscopy:

| Channel | Measurement |
|---|---|
| **R** | reflectance |
| **A** | angle of polarisation |
| **P** | degree of polarisation |

The three greyscale measurements are stacked into the network's three input channels at
**96 × 96**, then normalised with ImageNet statistics.

### This was verified empirically, and it matters

Scoring 231 labelled HMPD particles that have all three channels present:

| Input construction | Accuracy | Precision | Recall |
|---|---|---|---|
| **R/A/P stacked** (correct) | **0.978** | 0.984 | 0.977 |
| R only, replicated across RGB | 0.450 | 1.000 | **0.008** |

Feeding only the reflectance channel scores at **chance** — it detects essentially
nothing (recall 0.008) while appearing confident. The API therefore **requires all three
channels**, and a single-channel upload is **rejected** rather than scored:

```json
{
  "error": "invalid_input",
  "message": "This is a single-channel image. The model needs three polarimetric channels
              ... Replicating one channel across all three scores at chance level, so the
              request was rejected rather than returning a meaningless result.",
  "detail": {"remedy": "Upload the R, A and P images to POST /api/microplastics/analyze"}
}
```

## Output

```json
{
  "task": "binary image classification (screening)",
  "classification": "microplastic_candidate",
  "microplastic_detected": true,
  "confidence": 0.9976,
  "count": 1,
  "detections": [
    {
      "label": "microplastic_candidate",
      "confidence": 0.9976,
      "region": "whole_image",
      "note": "HMPD carries image-level labels only, so the detection covers the whole
               field of view; no per-particle localisation is available."
    }
  ],
  "class_probabilities": {
    "no_microplastic_detected": 0.0024,
    "microplastic_candidate": 0.9976
  },
  "input": {"mode": "polarimetric_triplet", "model_input_size": 96},
  "disclaimer": "Image-based screening only; does not determine chemical composition,
                 polymer type, or absolute concentration. ..."
}
```

`count` is 0 or 1 — the number of *images* flagged, never a particle count. `region` is
always `whole_image`, stated explicitly so the field is not mistaken for a bounding box.

## Training data

**HMPD** (Hyperspectral MicroPlastic Dataset), balanced split: **3,293 positive / 3,293
negative** particles, per the artifact's own `config.json`.

Potential future extension: MP-Set. Not integrated.

## Validation strategy

**5-fold stratified cross-validation** over the balanced HMPD training split.

## Metrics

| Metric | Mean | Std |
|---|---|---|
| Accuracy | **0.9283** | 0.0038 |
| F1 | **0.9294** | — |
| ROC-AUC | **0.9779** | — |

### Per fold

| Fold | Accuracy | Precision | Recall | F1 | ROC-AUC |
|---|---|---|---|---|---|
| 0 | 0.9287 | 0.9134 | 0.9490 | 0.9309 | 0.9767 |
| 1 | 0.9271 | 0.9172 | 0.9394 | 0.9281 | 0.9754 |
| 2 | 0.9226 | 0.9062 | 0.9374 | 0.9215 | 0.9799 |
| 3 | 0.9324 | 0.9115 | 0.9552 | 0.9328 | 0.9775 |
| 4 | 0.9309 | 0.9262 | 0.9412 | 0.9336 | 0.9799 |

Fold-to-fold variance is very low (accuracy std 0.0038), so the estimate is stable.
Recall consistently exceeds precision (~0.94 vs ~0.91), meaning the model errs towards
flagging — appropriate for a screening tool, where a missed particle costs more than one
sent for confirmation.

No detection metrics (mAP, IoU) are reported, because no detection model was built.

## Limitations

- **Screening only.** Flags a visual signature. No polymer identification, no chemical
  composition — those need FTIR or Raman.
- **No concentration.** Reports no particles-per-litre figure, because sample volume and
  preparation protocol are not visible in an image.
- **No localisation or count.** HMPD's image-level labels make per-particle detection
  impossible; a positive result covers the whole field of view.
- **Polarimetric input required.** Ordinary photographs and single-channel images lack
  the polarisation signal; such uploads are rejected, not scored.
- **Instrument specificity.** Cross-validation accuracy is measured *within* HMPD.
  Performance on microscopy from a different instrument, magnification, illumination or
  sample-preparation protocol is **unvalidated**.
- **No external test set.** All figures are cross-validation on the training split; there
  is no held-out set from an independent source.
- **Balanced training, unbalanced reality.** Trained on a 50/50 split, while real samples
  are usually dominated by non-plastic material, so the false-positive rate in field use
  will exceed the cross-validation figure.
- **Fixed 96 × 96 input.** Larger particle images are downsampled, losing fine
  morphological detail.
- **Two classes only.** No particle-type, size or shape classification.

## Known biases

The balanced training split means the model's operating point assumes a far higher
microplastic prevalence than a real water sample contains. Particles whose polarimetric
signature resembles the HMPD positives are favoured; unusual polymers, heavily weathered
fragments, or biofouled particles may be missed.

## Intended use

Triage of polarisation-microscopy imagery, to prioritise which particles go for
spectroscopic confirmation. **Not** suitable for regulatory water-quality reporting,
concentration measurement, polymer identification, or any published scientific claim
without spectroscopic confirmation.

## API

```
POST /api/microplastics/analyze            r_image + a_image + p_image  (required path)
POST /api/microplastics/analyze-composite  one pre-stacked 3-channel image
GET  /api/microplastics/metrics            cross-validation evidence and limitations
```

Uploads are validated for size (`MAX_UPLOAD_BYTES`, default 10 MB) and extension, and
must decode as an image. Client-supplied filenames are reduced to their basename and used
only for the extension check, never as a path.
