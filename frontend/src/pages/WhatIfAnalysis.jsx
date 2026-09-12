import { useEffect, useState } from 'react';
import { fetchCities, runWhatIfScenario } from '../api/client';
import { SCENARIO_DEFAULTS } from '../data/mockData';
import CitySelector from '../components/city/CitySelector';
import ScenarioControls from '../components/whatif/ScenarioControls';
import MetricCard from '../components/dashboard/MetricCard';
import { TrendingUp, Droplets, Gauge } from 'lucide-react';

export default function WhatIfAnalysis() {
  const [cities, setCities] = useState([]);
  const [selectedCity, setSelectedCity] = useState(null);
  const [scenario, setScenario] = useState(SCENARIO_DEFAULTS);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchCities().then((c) => {
      setCities(c);
      setSelectedCity(c[0]);
    });
  }, []);

  async function handleRun() {
    setLoading(true);
    const res = await runWhatIfScenario(selectedCity.id, scenario);
    setResult(res);
    setLoading(false);
  }

  if (!selectedCity) return null;

  return (
    <div className="flex-1 p-8 max-w-[1400px]">
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-2xl font-semibold text-mist">What-if Analysis</h1>
          <p className="text-sm text-mist-muted mt-1">Test a planning scenario before it becomes policy</p>
        </div>
        <CitySelector cities={cities} selectedCity={selectedCity} onSelect={setSelectedCity} />
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          <ScenarioControls scenario={scenario} onChange={setScenario} onRun={handleRun} loading={loading} />
        </div>

        <div className="lg:col-span-2">
          {!result ? (
            <div className="h-full min-h-[280px] bg-ink-light border border-white/5 border-dashed rounded-2xl flex flex-col items-center justify-center text-center px-8">
              <Gauge size={28} className="text-mist-faint mb-3" strokeWidth={1.5} />
              <p className="text-sm text-mist-muted max-w-xs">
                Set your scenario levers and run the model to see projected impact on {selectedCity.name}.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <MetricCard
                label="Projected Water Demand"
                value={result.projectedWaterDemand}
                unit="MLD"
                tone="water"
              />
              <MetricCard
                label="Groundwater Change"
                value={result.projectedGroundwaterChange}
                unit="cm"
                tone={result.projectedGroundwaterChange < -20 ? 'alert' : 'earth'}
              />
              <MetricCard
                label="Sustainability Score Δ"
                value={result.sustainabilityScoreDelta > 0 ? `+${result.sustainabilityScoreDelta}` : result.sustainabilityScoreDelta}
                tone={result.sustainabilityScoreDelta >= 0 ? 'water' : 'alert'}
              />

              <div className="sm:col-span-3 bg-ink-light border border-white/5 rounded-2xl p-6 flex items-start gap-3">
                <TrendingUp size={18} className="text-water mt-0.5 shrink-0" strokeWidth={1.75} />
                <p className="text-sm text-mist-muted leading-relaxed">
                  This is a mock projection driven by simple multipliers — once the FastAPI backend and
                  trained models are live, this panel calls <code className="text-water font-mono text-xs">/api/whatif/{selectedCity.id}</code>{' '}
                  and runs the full multi-agent + optimization pipeline against your scenario inputs.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
