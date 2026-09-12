// Mock data shaped to match what /api/predictions and /api/recommendations
// will eventually return from the FastAPI backend. Replace with real fetches
// via src/api/client.js once the model pipeline is live.

export const CITIES = [
  { id: 'chennai', name: 'Chennai', state: 'Tamil Nadu', lat: 13.08, lon: 80.27 },
  { id: 'bengaluru', name: 'Bengaluru', state: 'Karnataka', lat: 12.97, lon: 77.59 },
  { id: 'mumbai', name: 'Mumbai', state: 'Maharashtra', lat: 19.08, lon: 72.88 },
  { id: 'delhi', name: 'Delhi', state: 'NCT', lat: 28.61, lon: 77.21 },
];

export const CITY_METRICS = {
  chennai: {
    sustainabilityScore: 58,
    population: { current: 11.6, projected2030: 13.2, unit: 'million' },
    waterDemand: [
      { year: 2020, residential: 620, industrial: 210 },
      { year: 2021, residential: 645, industrial: 225 },
      { year: 2022, residential: 668, industrial: 238 },
      { year: 2023, residential: 690, industrial: 252 },
      { year: 2024, residential: 715, industrial: 268 },
      { year: 2025, residential: 742, industrial: 281 },
    ],
    groundwater: [
      { year: 2020, level: -8 },
      { year: 2021, level: -11 },
      { year: 2022, level: -14 },
      { year: 2023, level: -19 },
      { year: 2024, level: -22 },
      { year: 2025, level: -26 },
    ],
    lakeArea: [
      { year: 2020, sqkm: 4.8 },
      { year: 2021, sqkm: 4.6 },
      { year: 2022, sqkm: 4.3 },
      { year: 2023, sqkm: 3.9 },
      { year: 2024, sqkm: 3.7 },
      { year: 2025, sqkm: 3.4 },
    ],
    floodRisk: 'Moderate',
    droughtRisk: 'High',
    riskZones: 6,
  },
  bengaluru: {
    sustainabilityScore: 47,
    population: { current: 13.6, projected2030: 15.9, unit: 'million' },
    waterDemand: [
      { year: 2020, residential: 780, industrial: 340 },
      { year: 2021, residential: 812, industrial: 360 },
      { year: 2022, residential: 845, industrial: 385 },
      { year: 2023, residential: 880, industrial: 410 },
      { year: 2024, residential: 918, industrial: 438 },
      { year: 2025, residential: 960, industrial: 465 },
    ],
    groundwater: [
      { year: 2020, level: -18 },
      { year: 2021, level: -24 },
      { year: 2022, level: -31 },
      { year: 2023, level: -38 },
      { year: 2024, level: -44 },
      { year: 2025, level: -52 },
    ],
    lakeArea: [
      { year: 2020, sqkm: 2.1 },
      { year: 2021, sqkm: 1.9 },
      { year: 2022, sqkm: 1.7 },
      { year: 2023, sqkm: 1.5 },
      { year: 2024, sqkm: 1.3 },
      { year: 2025, sqkm: 1.1 },
    ],
    floodRisk: 'Low',
    droughtRisk: 'Severe',
    riskZones: 11,
  },
  mumbai: {
    sustainabilityScore: 64,
    population: { current: 20.7, projected2030: 22.8, unit: 'million' },
    waterDemand: [
      { year: 2020, residential: 1450, industrial: 520 },
      { year: 2021, residential: 1480, industrial: 535 },
      { year: 2022, residential: 1510, industrial: 552 },
      { year: 2023, residential: 1545, industrial: 570 },
      { year: 2024, residential: 1582, industrial: 590 },
      { year: 2025, residential: 1620, industrial: 612 },
    ],
    groundwater: [
      { year: 2020, level: -4 },
      { year: 2021, level: -5 },
      { year: 2022, level: -6 },
      { year: 2023, level: -7 },
      { year: 2024, level: -8 },
      { year: 2025, level: -9 },
    ],
    lakeArea: [
      { year: 2020, sqkm: 8.2 },
      { year: 2021, sqkm: 8.1 },
      { year: 2022, sqkm: 7.9 },
      { year: 2023, sqkm: 7.8 },
      { year: 2024, sqkm: 7.6 },
      { year: 2025, sqkm: 7.4 },
    ],
    floodRisk: 'Severe',
    droughtRisk: 'Low',
    riskZones: 14,
  },
  delhi: {
    sustainabilityScore: 41,
    population: { current: 32.9, projected2030: 37.1, unit: 'million' },
    waterDemand: [
      { year: 2020, residential: 1890, industrial: 610 },
      { year: 2021, residential: 1945, industrial: 635 },
      { year: 2022, residential: 2005, industrial: 662 },
      { year: 2023, residential: 2068, industrial: 690 },
      { year: 2024, residential: 2135, industrial: 720 },
      { year: 2025, residential: 2205, industrial: 752 },
    ],
    groundwater: [
      { year: 2020, level: -22 },
      { year: 2021, level: -29 },
      { year: 2022, level: -37 },
      { year: 2023, level: -45 },
      { year: 2024, level: -53 },
      { year: 2025, level: -61 },
    ],
    lakeArea: [
      { year: 2020, sqkm: 1.4 },
      { year: 2021, sqkm: 1.2 },
      { year: 2022, sqkm: 1.0 },
      { year: 2023, sqkm: 0.8 },
      { year: 2024, sqkm: 0.7 },
      { year: 2025, sqkm: 0.5 },
    ],
    floodRisk: 'Moderate',
    droughtRisk: 'Severe',
    riskZones: 19,
  },
};

export const AGENT_RECOMMENDATIONS = {
  chennai: [
    { agent: 'Water Authority', tone: 'caution', text: 'Groundwater recharge in the southern zones is falling faster than rainfall can replenish it — prioritize rainwater harvesting mandates before new residential permits are issued.' },
    { agent: 'Urban Planner', tone: 'neutral', text: 'Proposed IT-corridor expansion aligns with existing road density, but sits directly over a moderate recharge zone.' },
    { agent: 'Environment', tone: 'caution', text: 'Pallikaranai wetland buffer has shrunk 8% in three years — recommend a hard no-build buffer of 500m.' },
    { agent: 'Citizen Welfare', tone: 'positive', text: 'Current supply still meets demand for 78% of wards, but that margin is closing.' },
    { agent: 'Coordinator', tone: 'decision', text: 'Approve IT-corridor phase 1 only with mandatory rainwater harvesting and a revised wetland buffer.' },
  ],
  bengaluru: [
    { agent: 'Water Authority', tone: 'alert', text: 'Groundwater decline has crossed the severe threshold in 4 of 8 zones — recommend an immediate borewell permit freeze.' },
    { agent: 'Urban Planner', tone: 'caution', text: 'Outer ring road industrial expansion would add 340 MLD demand with no matching supply plan.' },
    { agent: 'Environment', tone: 'alert', text: 'Lake area has nearly halved since 2020; encroachment is the leading driver, not just evaporation.' },
    { agent: 'Industry', tone: 'neutral', text: 'Tech-park proposals can proceed if water recycling is mandated at 60%+ reuse.' },
    { agent: 'Coordinator', tone: 'decision', text: 'Freeze new borewell permits city-wide; conditionally approve industrial expansion pending recycled-water commitments.' },
  ],
  mumbai: [
    { agent: 'Water Authority', tone: 'neutral', text: 'Groundwater is stable, but that stability depends on continued reservoir-fed supply, not local recharge.' },
    { agent: 'Urban Planner', tone: 'alert', text: 'Coastal expansion zones overlap with the highest flood-risk grid cells in the city.' },
    { agent: 'Environment', tone: 'caution', text: 'Mangrove-adjacent lake area is eroding faster than the citywide average.' },
    { agent: 'Citizen Welfare', tone: 'positive', text: 'Supply reliability remains high across most wards.' },
    { agent: 'Coordinator', tone: 'decision', text: 'Reroute coastal expansion inland by one grid tier; prioritize flood infrastructure before further coastal permits.' },
  ],
  delhi: [
    { agent: 'Water Authority', tone: 'alert', text: 'Groundwater decline is the steepest of all four cities — 61cm anomaly and accelerating.' },
    { agent: 'Urban Planner', tone: 'alert', text: 'Population growth to 2030 will outpace planned water infrastructure by a wide margin.' },
    { agent: 'Environment', tone: 'alert', text: 'Yamuna floodplain water bodies have lost over 60% of area since 2020.' },
    { agent: 'Citizen Welfare', tone: 'alert', text: '19 wards are already classified as high-risk for supply shortfall.' },
    { agent: 'Coordinator', tone: 'decision', text: 'Recommend an emergency water-security review before approving any further peripheral expansion.' },
  ],
};

export const SCENARIO_DEFAULTS = {
  newIndustry: false,
  populationGrowth: 15,
  rainwaterHarvesting: false,
  greenCoverIncrease: 10,
};
