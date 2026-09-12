# SmartCityAI — Frontend

React + Vite + Tailwind dashboard for the Multi-Agent AI Framework for
Sustainable Urban Growth and Water Resource Planning.

## Setup

```bash
cd frontend
npm install
npm run dev
```

Opens at `http://localhost:5173`.

## Structure

- `src/pages/` — Dashboard, What-if Analysis, Compare Cities
- `src/components/dashboard/` — chart panels (water demand, groundwater,
  lake monitoring), sustainability score gauge, recommendation feed
- `src/components/whatif/` — scenario control sliders
- `src/data/mockData.js` — placeholder data shaped exactly like the future
  API response, per city
- `src/api/client.js` — single file to swap mock data for real backend
  calls. Set `USE_MOCK = false` and point `VITE_API_BASE_URL` at your
  FastAPI server once `backend/api/main.py` is live. No component code
  needs to change — every page already calls through this client.

## Design system

- Colors, fonts, and spacing live in `tailwind.config.js`
  (`ink` = background, `water` = teal accent, `earth` = ochre accent,
  `alert` = coral for risk states)
- Fonts: Space Grotesk (display), Inter (body), IBM Plex Mono (data/labels)
- Signature element: the sustainability score renders as a water-tank fill
  gauge rather than a generic progress ring, and the sidebar footer uses a
  topographic contour-line motif — both tie back to the GIS/water-scarcity
  subject matter instead of being decorative defaults.

## Connecting to the real backend

1. Build `backend/api/main.py` (FastAPI) with routes matching
   `src/api/client.js`: `/api/cities`, `/api/predictions/{cityId}`,
   `/api/recommendations/{cityId}`, `/api/whatif/{cityId}`.
2. In `client.js`, flip `USE_MOCK` to `false`.
3. Set `VITE_API_BASE_URL` in a `.env` file if the backend isn't on
   `localhost:8000`.
