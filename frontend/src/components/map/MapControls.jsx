import { Layers } from 'lucide-react';

import { LAYERS } from '../../lib/domain';

/**
 * Layer picker and legend.
 *
 * One layer renders at a time: overlapping semi-transparent grids over the same
 * cells would make every colour a blend of three, which no legend could explain.
 * Switching is instant because all three layers are fetched up front.
 */
export function LayerPicker({ active, onChange, counts }) {
  return (
    <div className="flex flex-col gap-1">
      <p className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1">
        <Layers size={13} />
        Map layer
      </p>
      {Object.values(LAYERS).map((layer) => {
        const isActive = layer.id === active;
        return (
          <button
            key={layer.id}
            onClick={() => onChange(layer.id)}
            aria-pressed={isActive}
            className={`text-left px-3 py-2 rounded-lg transition-colors ${
              isActive
                ? 'bg-water/10 border border-water/25'
                : 'border border-transparent hover:bg-white/[0.03]'
            }`}
          >
            <span
              className={`block text-sm font-medium ${isActive ? 'text-water' : 'text-mist-muted'}`}
            >
              {layer.plain}
            </span>
            <span className="block text-[11px] text-mist-faint mt-0.5">
              {layer.label}
              {counts?.[layer.id] != null && ` · ${counts[layer.id].toLocaleString()} cells`}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** Legend for the active layer, with a count per class. */
export function MapLegend({ activeLayer, geojson }) {
  const layer = LAYERS[activeLayer];
  if (!layer) return null;

  const counts = {};
  for (const feature of geojson?.features ?? []) {
    const key = feature.properties?.[layer.classKey];
    if (key) counts[key] = (counts[key] || 0) + 1;
  }
  const total = Object.values(counts).reduce((sum, n) => sum + n, 0);

  return (
    <div>
      <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-2">
        Legend
      </p>
      <ul className="space-y-1.5">
        {Object.entries(layer.classes).map(([key, meta]) => {
          const count = counts[key] || 0;
          const share = total ? (count / total) * 100 : 0;
          return (
            <li key={key} className="flex items-center gap-2.5">
              <span
                className="w-3 h-3 rounded-sm shrink-0 border border-black/30"
                style={{ backgroundColor: meta.color }}
                aria-hidden="true"
              />
              <span className="flex-1 min-w-0">
                <span className="block text-xs text-mist truncate">{meta.label}</span>
                <span className="block text-[10px] text-mist-faint truncate">{meta.plain}</span>
              </span>
              <span className="text-[11px] font-mono text-mist-muted shrink-0">
                {count.toLocaleString()}
                <span className="text-mist-faint"> · {share.toFixed(0)}%</span>
              </span>
            </li>
          );
        })}
      </ul>
      <p className="text-[10px] text-mist-faint mt-3 leading-relaxed">
        Each square is one square kilometre of real analysis. Click a square for its full
        assessment.
      </p>
    </div>
  );
}
