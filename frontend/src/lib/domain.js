// Single source of truth for how model classes are presented.
//
// The map fill, the legend, the badges and the detail panels all read from here,
// so they can never disagree about what GREEN means or which colour HIGH flood
// risk uses. Hex values mirror the Tailwind palette because Leaflet styles
// SVG paths directly and cannot use Tailwind classes.

export const SUITABILITY = {
  GREEN: {
    label: 'Suitable',
    plain: 'Good place to grow',
    tone: 'green',
    color: '#3FBF7F',
    description: 'Preferred direction for growth, subject to the flood and water findings.',
  },
  YELLOW: {
    label: 'Conditional',
    plain: 'Possible, with checks',
    tone: 'yellow',
    color: '#E3A93C',
    description: 'Development needs further consideration before it proceeds.',
  },
  RED: {
    label: 'Avoid',
    plain: 'Not a good place to grow',
    tone: 'red',
    color: '#E2583E',
    description: 'Unsuitable or high-risk for expansion.',
  },
};

export const FLOOD_RISK = {
  HIGH: {
    label: 'High',
    plain: 'High flood risk',
    tone: 'red',
    color: '#E2583E',
    description: 'Development should be restricted or heavily mitigated.',
  },
  MODERATE: {
    label: 'Moderate',
    plain: 'Some flood risk',
    tone: 'yellow',
    color: '#E3A93C',
    description: 'Resilience measures are required.',
  },
  LOW: {
    label: 'Low',
    plain: 'Low flood risk',
    tone: 'green',
    color: '#3FBF7F',
    description: 'Standard drainage design is expected to suffice.',
  },
};

export const WATER_CLASS = {
  water_body: {
    label: 'Water body',
    plain: 'Contains surface water',
    tone: 'water',
    color: '#4CC9C0',
  },
  non_water_body: {
    label: 'No water body',
    plain: 'No surface water detected',
    tone: 'neutral',
    color: '#3A5250',
  },
};

export const PRIORITY = {
  HIGH: { label: 'Do first', tone: 'red' },
  MEDIUM: { label: 'Worth doing', tone: 'yellow' },
  LOW: { label: 'Nice to have', tone: 'green' },
};

/** Coordinator verdicts, in plain language a non-specialist can act on. */
export const VERDICT = {
  proceed: {
    label: 'Go ahead',
    tone: 'green',
    color: '#3FBF7F',
    summary: 'The evidence supports development here.',
  },
  proceed_with_conditions: {
    label: 'Go ahead with conditions',
    tone: 'yellow',
    color: '#E3A93C',
    summary: 'Development is acceptable once the conditions below are met.',
  },
  proceed_with_strong_mitigation: {
    label: 'Only with strong protection',
    tone: 'yellow',
    color: '#E3A93C',
    summary:
      'Growth pressure is high here, but so is the hazard. Development needs substantial protective measures.',
  },
  discourage: {
    label: 'Not recommended',
    tone: 'red',
    color: '#E2583E',
    summary: 'The evidence does not support development at this location.',
  },
  insufficient_evidence: {
    label: 'Not enough evidence',
    tone: 'neutral',
    color: '#8FA8A6',
    summary: 'Too few models produced a result to reach a conclusion.',
  },
};

export const DOMAIN_META = {
  water: { label: 'Water & Environment', model: 'Model 1 — Surface Water' },
  urban: { label: 'Urban Planning', model: 'Model 2 — Urban Expansion' },
  flood: { label: 'Flood & Resilience', model: 'Model 3 — Flood Risk' },
  building: { label: 'Building Sustainability', model: 'Building Planner rules' },
};

// ── Layer definitions for the map ──────────────────────────────────────────

export const LAYERS = {
  urban: {
    id: 'urban',
    label: 'Expansion suitability',
    plain: 'Where the city could grow',
    tone: 'green',
    /** Property on a GeoJSON feature that carries the class. */
    classKey: 'suitability_class',
    classes: SUITABILITY,
    /** Numeric property shown in the tooltip. */
    valueKey: 'suitability_score',
    valueLabel: 'Suitability score',
    formatValue: (v) => (v == null ? '—' : v.toFixed(2)),
  },
  flood: {
    id: 'flood',
    label: 'Flood risk',
    plain: 'Where flooding is likely',
    tone: 'red',
    classKey: 'risk_level',
    classes: FLOOD_RISK,
    valueKey: 'flood_probability',
    valueLabel: 'Flood probability',
    formatValue: (v) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`),
  },
  water: {
    id: 'water',
    label: 'Surface water',
    plain: 'Where water bodies are',
    tone: 'water',
    classKey: 'classification',
    classes: WATER_CLASS,
    valueKey: 'water_body_probability',
    valueLabel: 'Water-body probability',
    formatValue: (v) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`),
  },
};

/** Colour for a feature in a given layer, falling back to a neutral grey. */
export function featureColor(layerId, properties) {
  const layer = LAYERS[layerId];
  if (!layer || !properties) return '#3A5250';
  return layer.classes[properties[layer.classKey]]?.color ?? '#3A5250';
}

// ── Formatting ─────────────────────────────────────────────────────────────

export const percent = (value, digits = 0) =>
  value == null || Number.isNaN(Number(value)) ? '—' : `${(Number(value) * 100).toFixed(digits)}%`;

export const decimal = (value, digits = 3) =>
  value == null || Number.isNaN(Number(value)) ? '—' : Number(value).toFixed(digits);

export function number(value, digits = 0) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** Indian-format currency, abbreviated to lakh and crore. */
export function rupees(value) {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(2)} crore`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(2)} lakh`;
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
}

/** "built_fraction_2020" -> "Built fraction 2020" */
export const humanise = (key) =>
  String(key).replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
