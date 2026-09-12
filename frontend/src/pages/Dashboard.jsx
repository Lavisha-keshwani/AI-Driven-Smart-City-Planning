import { useEffect, useState } from 'react';
import { fetchCities, fetchCityMetrics, fetchRecommendations } from '../api/client';
import CitySelector from '../components/city/CitySelector';
import SustainabilityScore from '../components/dashboard/SustainabilityScore';
import MetricCard from '../components/dashboard/MetricCard';
import WaterDemandPanel from '../components/dashboard/WaterDemandPanel';
import GroundwaterPanel from '../components/dashboard/GroundwaterPanel';
import LakeMonitoringPanel from '../components/dashboard/LakeMonitoringPanel';
import RecommendationFeed from '../components/dashboard/RecommendationFeed';

export default function Dashboard() {
  const [cities, setCities] = useState([]);
  const [selectedCity, setSelectedCity] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCities().then((c) => {
      setCities(c);
      setSelectedCity(c[0]);
    });
  }, []);

  useEffect(() => {
    if (!selectedCity) return;
    setLoading(true);
    Promise.all([
      fetchCityMetrics(selectedCity.id),
      fetchRecommendations(selectedCity.id),
    ]).then(([m, r]) => {
      setMetrics(m);
      setRecommendations(r);
      setLoading(false);
    });
  }, [selectedCity]);

  if (!selectedCity || !metrics) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <p className="text-mist-muted text-sm font-mono">Loading city data…</p>
      </div>
    );
  }

  return (
    <div className="flex-1 p-8 max-w-[1400px]">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-2xl font-semibold text-mist">Urban & Water Planning Dashboard</h1>
          <p className="text-sm text-mist-muted mt-1">
            {selectedCity.name}, {selectedCity.state} · {selectedCity.lat.toFixed(2)}°N, {selectedCity.lon.toFixed(2)}°E
          </p>
        </div>
        <CitySelector cities={cities} selectedCity={selectedCity} onSelect={setSelectedCity} />
      </header>

      <div className={`grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
        <SustainabilityScore score={metrics.sustainabilityScore} />
        <MetricCard
          label="Population (2025 → 2030)"
          value={`${metrics.population.current}M`}
          sublabel={`Projected ${metrics.population.projected2030}M by 2030`}
          tone="water"
        />
        <MetricCard
          label="Groundwater Risk Zones"
          value={metrics.riskZones}
          sublabel={`Drought risk: ${metrics.droughtRisk}`}
          tone="alert"
        />
      </div>

      <div className={`grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
        <WaterDemandPanel data={metrics.waterDemand} />
        <GroundwaterPanel data={metrics.groundwater} riskZones={metrics.riskZones} />
      </div>

      <div className={`grid grid-cols-1 xl:grid-cols-2 gap-6 transition-opacity ${loading ? 'opacity-50' : ''}`}>
        <LakeMonitoringPanel data={metrics.lakeArea} floodRisk={metrics.floodRisk} droughtRisk={metrics.droughtRisk} />
        <RecommendationFeed recommendations={recommendations} />
      </div>
    </div>
  );
}
