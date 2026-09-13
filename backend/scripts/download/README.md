# Source layer acquisition

The feature tables this project consumes were exported from Google Earth Engine onto
a common 1 km grid covering 45 Indian cities. They ship inside `models/`, so no
download is needed to run, test or evaluate the system.

This file records provenance, so the work can be extended to new cities.

| Layer | Earth Engine collection | Fields used | Consumed by |
|---|---|---|---|
| City grid | project-defined 1 km fishnet | `grid_id, city, state, lat, lon, is_core` | every model |
| Global Surface Water | `JRC/GSW1_4/GlobalSurfaceWater` | occurrence, seasonality, recurrence, max extent | Models 1, 3 |
| SRTM DEM | `USGS/SRTMGL1_003` | `elevation_m, slope_deg, depression_index_m` | Models 1, 2, 3 |
| CHIRPS | `UCSB-CHG/CHIRPS/DAILY` | annual and monthly rainfall, per year | Models 1, 2, 3 |
| GHSL built-up | `JRC/GHSL/P2023A/GHS_BUILT_S` | `built_fraction` at 1975/1990/2000/2015/2020 | Models 2, 3 |
| Open Buildings | `GOOGLE/Research/open-buildings-temporal/v1` | count, mean height, mean presence | Models 2, 3 |
| Dynamic World | `GOOGLE/DYNAMICWORLD/V1` | `built, trees` land-cover fractions | Model 1 |
| Global Flood Database | `GLOBAL_FLOOD_DB/MODIS_EVENTS/V1` | observed inundation -> `flood_label` | Model 3 |
| Sentinel-2 | `COPERNICUS/S2_SR_HARMONIZED` | `ndvi, ndbi` spectral indices | Model 1 |
| OpenStreetMap | Overpass extracts | road density | **excluded** — see below |

## Road density

Road density was deliberately excluded from Model 2. OpenStreetMap road coverage was
complete for only 3 of the 45 cities, so the feature could not be constructed
consistently and would have encoded data availability rather than accessibility. The
exclusion is recorded in the model's own `feature_list.json` and in its model card.

## Extending to new cities

1. Generate the 1 km grid for the new city and append it to the grid registry.
2. Export each layer above for the new cells, preserving the column names in the table.
3. Point the matching `*_DIR` / `*_CSV` variables in `.env` at the new exports.
4. Rebuild the feature tables and re-run evaluation:

   ```bash
   python -m scripts.features.build_urban_expansion_features --out build/
   python -m scripts.evaluation.evaluate_models --model all
   ```

Retraining is required before predictions for a new state should be trusted: `state`
is a model input for Models 1 and 3, so an unseen state carries no learned prior.
