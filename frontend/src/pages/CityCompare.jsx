import { useEffect, useState } from 'react';
import { fetchCities, fetchCityMetrics } from '../api/client';
import SustainabilityScore from '../components/dashboard/SustainabilityScore';

export default function CityCompare() {
  const [cities, setCities] = useState([]);
  const [metricsByCity, setMetricsByCity] = useState({});

  useEffect(() => {
    fetchCities().then(async (c) => {
      setCities(c);
      const entries = await Promise.all(
        c.map(async (city) => [city.id, await fetchCityMetrics(city.id)])
      );
      setMetricsByCity(Object.fromEntries(entries));
    });
  }, []);

  return (
    <div className="flex-1 p-8 max-w-[1400px]">
      <header className="mb-8">
        <h1 className="font-display text-2xl font-semibold text-mist">Compare Cities</h1>
        <p className="text-sm text-mist-muted mt-1">Sustainability posture across all four supported cities</p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
        {cities.map((city) => {
          const m = metricsByCity[city.id];
          if (!m) return null;
          return (
            <div key={city.id}>
              <div className="flex items-baseline justify-between mb-3">
                <h2 className="font-display font-semibold text-mist">{city.name}</h2>
                <span className="text-xs text-mist-muted font-mono">{city.state}</span>
              </div>
              <SustainabilityScore score={m.sustainabilityScore} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
