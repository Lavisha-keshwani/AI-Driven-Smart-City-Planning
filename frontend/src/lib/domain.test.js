import { describe, expect, it } from 'vitest';

import {
  FLOOD_RISK,
  LAYERS,
  SUITABILITY,
  VERDICT,
  decimal,
  featureColor,
  humanise,
  percent,
  rupees,
} from './domain';

/**
 * These guard the presentation contract: the map, legend and panels all read
 * class metadata from here, so a gap or a mismatch would let them disagree
 * about what a class means or which colour it uses.
 */

describe('class metadata', () => {
  it('covers every suitability class the backend can return', () => {
    expect(Object.keys(SUITABILITY).sort()).toEqual(['GREEN', 'RED', 'YELLOW']);
  });

  it('covers every flood risk band the backend can return', () => {
    expect(Object.keys(FLOOD_RISK).sort()).toEqual(['HIGH', 'LOW', 'MODERATE']);
  });

  it('covers every coordinator verdict the backend can return', () => {
    expect(Object.keys(VERDICT).sort()).toEqual([
      'discourage',
      'insufficient_evidence',
      'proceed',
      'proceed_with_conditions',
      'proceed_with_strong_mitigation',
    ]);
  });

  it('gives every class a colour, a label and plain-language wording', () => {
    for (const group of [SUITABILITY, FLOOD_RISK]) {
      for (const [key, meta] of Object.entries(group)) {
        expect(meta.color, key).toMatch(/^#[0-9A-Fa-f]{6}$/);
        expect(meta.label, key).toBeTruthy();
        expect(meta.plain, key).toBeTruthy();
        expect(meta.description, key).toBeTruthy();
      }
    }
  });

  it('uses a distinct colour per class within a layer', () => {
    for (const layer of Object.values(LAYERS)) {
      const colors = Object.values(layer.classes).map((c) => c.color);
      expect(new Set(colors).size, layer.id).toBe(colors.length);
    }
  });

  it('agrees between suitability and flood on shared semantics', () => {
    // Green must mean the same colour whether it is "suitable" or "low risk",
    // so a reader is not asked to learn two colour languages.
    expect(SUITABILITY.GREEN.color).toBe(FLOOD_RISK.LOW.color);
    expect(SUITABILITY.RED.color).toBe(FLOOD_RISK.HIGH.color);
    expect(SUITABILITY.YELLOW.color).toBe(FLOOD_RISK.MODERATE.color);
  });
});

describe('map layers', () => {
  it('defines the three model layers', () => {
    expect(Object.keys(LAYERS).sort()).toEqual(['flood', 'urban', 'water']);
  });

  it('names a class key and value key that match the API payload', () => {
    expect(LAYERS.urban.classKey).toBe('suitability_class');
    expect(LAYERS.urban.valueKey).toBe('suitability_score');
    expect(LAYERS.flood.classKey).toBe('risk_level');
    expect(LAYERS.flood.valueKey).toBe('flood_probability');
    expect(LAYERS.water.classKey).toBe('classification');
  });

  it('formats layer values for display', () => {
    expect(LAYERS.flood.formatValue(0.674)).toBe('67%');
    expect(LAYERS.urban.formatValue(0.8686)).toBe('0.87');
    expect(LAYERS.flood.formatValue(null)).toBe('—');
  });
});

describe('featureColor', () => {
  it('maps a class to its colour', () => {
    expect(featureColor('urban', { suitability_class: 'GREEN' })).toBe(SUITABILITY.GREEN.color);
    expect(featureColor('flood', { risk_level: 'HIGH' })).toBe(FLOOD_RISK.HIGH.color);
  });

  it('falls back to neutral for an unknown class rather than throwing', () => {
    expect(featureColor('urban', { suitability_class: 'PURPLE' })).toBe('#3A5250');
    expect(featureColor('urban', null)).toBe('#3A5250');
    expect(featureColor('nonexistent', { a: 1 })).toBe('#3A5250');
  });
});

describe('formatting', () => {
  it('renders percentages', () => {
    expect(percent(0.6746)).toBe('67%');
    expect(percent(0.6746, 1)).toBe('67.5%');
    expect(percent(1)).toBe('100%');
  });

  it('renders decimals', () => {
    expect(decimal(0.86861, 2)).toBe('0.87');
    expect(decimal(0.5)).toBe('0.500');
  });

  it('renders a dash for a missing value rather than NaN or zero', () => {
    // Showing 0% for "unavailable" would be a fabricated measurement.
    for (const fn of [percent, decimal]) {
      expect(fn(null)).toBe('—');
      expect(fn(undefined)).toBe('—');
      expect(fn('abc')).toBe('—');
    }
  });

  it('keeps a real zero distinct from a missing value', () => {
    expect(percent(0)).toBe('0%');
    expect(decimal(0, 2)).toBe('0.00');
  });

  it('abbreviates rupees in Indian units', () => {
    expect(rupees(5_000_000)).toBe('₹50.00 lakh');
    expect(rupees(25_000_000)).toBe('₹2.50 crore');
    expect(rupees(4500)).toBe('₹4,500');
    expect(rupees(null)).toBe('—');
  });

  it('humanises field names', () => {
    expect(humanise('built_fraction_2020')).toBe('Built fraction 2020');
    expect(humanise('flood_probability')).toBe('Flood probability');
  });
});
