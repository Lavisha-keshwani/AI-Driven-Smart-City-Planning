// Thin API layer. Every function currently resolves from mock data with a
// simulated delay so the UI behaves like it's hitting a real network call.
// Once backend/api/main.py is live, swap the body of each function for a
// fetch() to the matching FastAPI route — component code does not change.

import { CITIES, CITY_METRICS, AGENT_RECOMMENDATIONS } from '../data/mockData';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const USE_MOCK = false; // flip to false once the backend is deployed

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchCities() {
  if (USE_MOCK) {
    await delay(150);
    return CITIES;
  }
  const res = await fetch(`${BASE_URL}/api/cities`);
  return res.json();
}

export async function fetchCityMetrics(cityId) {
  if (USE_MOCK) {
    await delay(250);
    return CITY_METRICS[cityId];
  }
  const res = await fetch(`${BASE_URL}/api/predictions/${cityId}`);
  return res.json();
}

export async function fetchRecommendations(cityId) {
  if (USE_MOCK) {
    await delay(300);
    return AGENT_RECOMMENDATIONS[cityId];
  }
  const res = await fetch(`${BASE_URL}/api/recommendations/${cityId}`);
  return res.json();
}

export async function runWhatIfScenario(cityId, scenario) {
  if (USE_MOCK) {
    await delay(600);
    // crude mock projection so the UI has something reactive to show
    const base = CITY_METRICS[cityId];
    const demandMultiplier = 1 + scenario.populationGrowth / 100;
    const greenReduction = scenario.greenCoverIncrease / 100;
    const harvestingOffset = scenario.rainwaterHarvesting ? 0.15 : 0;
    const industryBump = scenario.newIndustry ? 1.2 : 1;

    return {
      projectedWaterDemand: Math.round(
        (base.waterDemand.at(-1).residential * demandMultiplier +
          base.waterDemand.at(-1).industrial * industryBump) *
          (1 - harvestingOffset)
      ),
      projectedGroundwaterChange: Math.round(
        base.groundwater.at(-1).level * demandMultiplier * (1 - harvestingOffset - greenReduction * 0.3)
      ),
      sustainabilityScoreDelta: Math.round(
        greenReduction * 20 + harvestingOffset * 30 - (demandMultiplier - 1) * 25 - (industryBump - 1) * 15
      ),
    };
  }
  const res = await fetch(`${BASE_URL}/api/whatif/${cityId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(scenario),
  });
  return res.json();
}
