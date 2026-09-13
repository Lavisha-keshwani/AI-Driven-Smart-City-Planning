import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { FloodCard, UrbanCard, WaterCard } from './CellSummary';

/**
 * These assert the honesty rules the project depends on:
 * a LOW result must not read as "safe", a GREEN score must not read as approval,
 * and measured observations must stay labelled as measurements.
 *
 * The fixtures mirror the real API payload shape.
 */

const FLOOD = {
  model: 'Urban Flood Risk',
  grid_id: 'Chennai_89281444',
  flood_probability: 0.6746,
  risk_level: 'HIGH',
  risk_meaning: 'High flood susceptibility',
  decision_threshold: 0.5718,
  risk_drivers: [
    {
      driver: 'low_elevation',
      reason: 'Elevation of 3 m leaves little gravity drainage head.',
      measured: { elevation_m: 3.07 },
    },
  ],
  observed: { elevation_m: 3.07 },
  feature_attribution: [
    { feature: 'elevation_m', importance: 0.31, direction: 'negative', shap_value: -0.12 },
  ],
};

const URBAN = {
  model: 'Urban Expansion Suitability',
  grid_id: 'Chennai_89281444',
  suitability_score: 0.975,
  suitability_class: 'GREEN',
  class_meaning: 'Suitable — preferred growth direction',
  confidence: 0.9,
  class_probabilities: { RED: 0.01, YELLOW: 0.04, GREEN: 0.95 },
  constraints: [],
  observed: {
    t0_year: 2000,
    t1_year: 2020,
    built_fraction_t0: 0.002,
    built_fraction_t1: 0.02,
    built_growth_t0_t1: 0.018,
  },
  feature_attribution: null,
};

const WATER = {
  model: 'Surface Water Monitoring',
  grid_id: 'Chennai_89281444',
  water_body_probability: 0.42,
  is_water_body: false,
  classification: 'non_water_body',
  decision_threshold: 0.5169,
  observed: { water_occurrence_pct: 6.2 },
  water_body_status: {
    status: 'ephemeral',
    occurrence_pct: 6.2,
    inter_annual_reliability: 'moderate',
  },
  feature_attribution: [],
};

describe('FloodCard', () => {
  it('leads with plain language, not the model probability', () => {
    render(<FloodCard prediction={FLOOD} />);
    expect(screen.getByRole('heading', { name: 'High flood risk' })).toBeInTheDocument();
  });

  it('still shows the probability for anyone who wants it', () => {
    render(<FloodCard prediction={FLOOD} />);
    expect(screen.getAllByText(/67% chance/).length).toBeGreaterThan(0);
  });

  it('cites the measured driver behind the result', () => {
    render(<FloodCard prediction={FLOOD} />);
    expect(screen.getByText(/Elevation of 3 m leaves little gravity drainage head/))
      .toBeInTheDocument();
  });

  it('warns that LOW means absence of evidence, not safety', () => {
    render(
      <FloodCard
        prediction={{ ...FLOOD, flood_probability: 0.1, risk_level: 'LOW', risk_drivers: [] }}
      />,
    );
    expect(screen.getByText(/not proof that this square is safe/i)).toBeInTheDocument();
  });

  it('does not show that warning for a HIGH result', () => {
    render(<FloodCard prediction={FLOOD} />);
    expect(screen.queryByText(/not proof that this square is safe/i)).not.toBeInTheDocument();
  });
});

describe('UrbanCard', () => {
  it('states that the score measures development pressure, not desirability', () => {
    render(<UrbanCard prediction={URBAN} />);
    expect(
      screen.getByText(/measures development pressure, not whether growing here is a good idea/i),
    ).toBeInTheDocument();
  });

  it('explains the forward-validation window in plain language', () => {
    render(<UrbanCard prediction={URBAN} />);
    expect(screen.getByText(/Between 2000 and 2020/)).toBeInTheDocument();
  });

  it('reports attribution as unavailable rather than inventing it', async () => {
    render(<UrbanCard prediction={URBAN} />);
    await userEvent.click(screen.getByRole('button', { name: /Why the model said this/ }));
    expect(screen.getByText(/SHAP is not installed/)).toBeInTheDocument();
    expect(screen.getByText(/No approximation is shown/)).toBeInTheDocument();
  });
});

describe('WaterCard', () => {
  it('labels the satellite figures as measurements, not predictions', () => {
    render(<WaterCard prediction={WATER} />);
    expect(
      screen.getByText(/satellite measurements from the Global Surface Water record/i),
    ).toBeInTheDocument();
  });

  it('describes an ephemeral water regime in plain words', () => {
    render(<WaterCard prediction={WATER} />);
    expect(screen.getByText(/Water appears here only occasionally/)).toBeInTheDocument();
  });
});

describe('technical detail is available but not forced', () => {
  it('keeps model internals collapsed until asked for', () => {
    render(<FloodCard prediction={FLOOD} />);
    expect(screen.queryByText(/SHAP values for this single prediction/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Why the model said this/ })).toBeInTheDocument();
  });

  it('reveals the SHAP attributions on request', async () => {
    render(<FloodCard prediction={FLOOD} />);
    await userEvent.click(screen.getByRole('button', { name: /Why the model said this/ }));
    expect(screen.getByText(/SHAP values for this single prediction/)).toBeInTheDocument();
    expect(screen.getByText('Elevation m')).toBeInTheDocument();
  });
});

describe('missing predictions', () => {
  it('renders nothing rather than a placeholder when a model produced no result', () => {
    for (const Card of [FloodCard, UrbanCard, WaterCard]) {
      const { container } = render(<Card prediction={null} />);
      expect(container).toBeEmptyDOMElement();
    }
  });
});
