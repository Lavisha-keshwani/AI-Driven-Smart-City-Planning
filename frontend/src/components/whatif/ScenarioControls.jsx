import { Play } from 'lucide-react';

export default function ScenarioControls({ scenario, onChange, onRun, loading }) {
  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6">
      <h3 className="font-display font-semibold text-mist mb-1">Scenario Inputs</h3>
      <p className="text-xs text-mist-muted mb-6">Adjust the levers, then run the model</p>

      <div className="space-y-6">
        <label className="flex items-center justify-between cursor-pointer">
          <span className="text-sm text-mist">New industry approved</span>
          <input
            type="checkbox"
            checked={scenario.newIndustry}
            onChange={(e) => onChange({ ...scenario, newIndustry: e.target.checked })}
            className="w-4 h-4 accent-water"
          />
        </label>

        <label className="flex items-center justify-between cursor-pointer">
          <span className="text-sm text-mist">Rainwater harvesting mandate</span>
          <input
            type="checkbox"
            checked={scenario.rainwaterHarvesting}
            onChange={(e) => onChange({ ...scenario, rainwaterHarvesting: e.target.checked })}
            className="w-4 h-4 accent-water"
          />
        </label>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-mist">Population growth</span>
            <span className="text-sm font-mono text-water">+{scenario.populationGrowth}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="40"
            value={scenario.populationGrowth}
            onChange={(e) => onChange({ ...scenario, populationGrowth: Number(e.target.value) })}
            className="w-full accent-water"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm text-mist">Green cover increase</span>
            <span className="text-sm font-mono text-water">+{scenario.greenCoverIncrease}%</span>
          </div>
          <input
            type="range"
            min="0"
            max="30"
            value={scenario.greenCoverIncrease}
            onChange={(e) => onChange({ ...scenario, greenCoverIncrease: Number(e.target.value) })}
            className="w-full accent-water"
          />
        </div>

        <button
          onClick={onRun}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 bg-water text-ink font-medium text-sm py-2.5 rounded-lg hover:bg-water-bright transition-colors disabled:opacity-50"
        >
          <Play size={14} fill="currentColor" />
          {loading ? 'Running model…' : 'Run scenario'}
        </button>
      </div>
    </div>
  );
}
