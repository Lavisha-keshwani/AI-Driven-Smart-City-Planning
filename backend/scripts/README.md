# Pipeline scripts

Reproducible scripts, so no step of the project depends on a hand-edited notebook.

```
scripts/
├── download/      acquisition of the source geospatial layers (Earth Engine exports)
├── preprocess/    cleaning and alignment onto the 1 km grid
├── features/      feature-table assembly per model
└── evaluation/    validation of the shipped model artifacts
```

Every script documents its `input -> preprocessing -> feature engineering -> output`
contract in its module docstring, resolves all paths through `app.core.config`, and
writes nothing outside its declared output directory.

## Running

From the `backend/` directory, with the virtualenv active:

```bash
# Verify the spatial framework before trusting any feature table
python -m scripts.preprocess.validate_grid_alignment --out build/

# Assemble the Model 2 feature table (it ships no pre-merged dataset)
python -m scripts.features.build_urban_expansion_features --out build/ --with-target

# Validate the shipped artifacts
python -m scripts.evaluation.evaluate_models --model all
python -m scripts.evaluation.evaluate_urban_expansion --out build/
```

### What each script guarantees

| Script | Guarantee |
|---|---|
| `preprocess/validate_grid_alignment.py` | Every layer covers the same `grid_id` set, with no duplicate keys, agreeing centroids, consistent CRS, plausible value ranges and correctly ordered forward-validation epochs. Exits non-zero on any failure. |
| `features/build_urban_expansion_features.py` | Reproducible Model 2 feature table plus a manifest of sources, row counts and per-feature completeness. Verifies the trained model can score the export. |
| `evaluation/evaluate_models.py` | Models 1 and 3 reproduce their training run's published unseen-city metrics. Exits non-zero on drift. |
| `evaluation/evaluate_urban_expansion.py` | Model 2's forward-validation target agreement and per-city spread; confirms the reconstructed categorical encoding matches training. |

## Data acquisition

The trained artifacts in `models/` ship with the processed feature tables they were
built from, so nothing needs downloading to run or evaluate this project. The
`download/` directory documents how those layers were produced, for anyone extending
the work to new cities — see `download/README.md`.

The scripts are configurable rather than hard-coded: point the `*_DIR` and `*_CSV`
variables in `.env` at new exports and the same pipelines rebuild against them.
