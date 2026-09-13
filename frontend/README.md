# SmartCityAI — Frontend

React interface for the SmartCityAI backend. Three sections: **City Planner**,
**Water & Microplastics**, and the **Sustainable Building Planner**.

See the [project README](../README.md) for the full setup and API reference.

## Quick start

```bash
npm install
npm run dev          # http://localhost:5173
```

The backend must be running at `http://localhost:8000`. Override with
`VITE_API_BASE_URL` in a `.env.local` file if it lives elsewhere.

## Scripts

| Command | Purpose |
|---|---|
| `npm run dev` | Development server |
| `npm run build` | Production build |
| `npm test` | 65 unit and component tests (vitest + Testing Library) |
| `npm run test:e2e` | 23 browser checks in Chrome against a live backend |
| `npm run lint` | oxlint |

`npm run test:e2e` needs both servers running and Chrome installed. It drives the
real UI: the map must draw real grid polygons, a cell click must run the full
agent pipeline, the microplastic screening must agree with the HMPD ground-truth
label, and the building planner must produce recommendations from live NASA POWER
data. Screenshots land in `e2e/screenshots/`. Set `CHROME_PATH` if Chrome is not
at the default Windows location.

## Structure

```
src/
├── App.jsx                     router and shell
├── api/client.js               the only place that talks to the backend
├── hooks/useAsync.js           request state, with abort on change/unmount
├── lib/domain.js               class -> colour/label/wording, one source of truth
├── components/
│   ├── ui/                     Card, Badge, Meter, Disclosure, ErrorState, form controls
│   ├── map/                    GridMap (Leaflet), LayerPicker, MapLegend
│   ├── cell/CellSummary.jsx    per-model result cards
│   ├── ai/CoordinatorPanel.jsx verdict, trade-offs, agent narratives
│   ├── technical/              SHAP, metrics, per-city performance, raw payload
│   ├── microplastic/           three-channel upload
│   ├── city/CitySelector.jsx
│   └── layout/Sidebar.jsx      nav and live backend status
└── pages/
    ├── CityPlanner.jsx
    ├── WaterMicroplastics.jsx
    └── BuildingPlanner.jsx
```

## Design decisions worth knowing

**Plain language first, technical detail one click away.** Every result leads with
what it means — "High flood risk", "Good place to grow" — and the probability in
words. Model name, SHAP attributions, validation metrics, per-city performance and
the raw API payload sit behind `Disclosure` panels, so a citizen is not made to
read them and an evaluator can always get to them.

**Uncertainty is shown, not hidden.** A LOW flood result carries the note that the
model misses roughly half of flood-prone squares, so low means *no evidence of
exposure*, not *safe*. A GREEN suitability score says it measures development
pressure, not whether growing there is a good idea.

**Measured and predicted stay separate.** Satellite observations are labelled as
measurements wherever they appear alongside model output.

**LLM involvement is always visible.** Every AI narrative states whether Groq wrote
it and which model, or whether it was generated deterministically because the LLM
was unavailable — with the reason.

**Missing data is never filled in.** `KeyValue` renders "not available" rather than
a zero, and `ErrorState` shows the backend's own error code, message and suggested
remedy instead of a generic failure.

**Colour is never the only signal.** Every map class is also named in text in the
legend and in each cell's tooltip, and the three classes differ in lightness as
well as hue.

## Map

Leaflet with `react-leaflet`, rendering GeoJSON straight from the backend — one
polygon per analysed 1 km cell, filled by the active layer's class. Not an image:
pan, zoom, hover and click all work against real model output.

Basemap tiles come from OpenStreetMap, which needs no API key, darkened with a CSS
filter to match the palette. For production traffic, host your own tiles or use a
keyed provider — the public OSM tile service is intended for low volume.

One layer renders at a time. Overlapping semi-transparent grids over the same cells
would make every colour a blend of three, which no legend could explain. All three
layers are fetched up front, so switching is instant.

The whole city grid is rendered — around 2,400 cells, 2,956 at most. An earlier
version capped this at 1,200, which silently showed only part of each city: the
source file is ordered south to north, so truncating it cut the grid along a
latitude line and left a half-disc below the city centre. A cap is only safe if it
samples evenly, and at this size none is needed. The browser smoke test now asserts
that the rendered cell count matches the city's analysed total.
