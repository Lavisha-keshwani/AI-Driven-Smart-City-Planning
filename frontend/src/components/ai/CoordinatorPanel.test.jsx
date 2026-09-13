import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import CoordinatorPanel, { AgentNarrative } from './CoordinatorPanel';

/**
 * The Coordinator panel must always make two things visible: the verdict in words
 * a non-specialist can act on, and whether an LLM wrote the explanation.
 */

const RESULT = {
  location: { grid_id: 'Chennai_89281444', city: 'Chennai' },
  recommendation: {
    overall_recommendation: 'proceed_with_strong_mitigation',
    headline: 'Proceed only with strong flood mitigation.',
    rationale: 'Growth pressure is high but so is flood exposure.',
    trade_offs: [
      {
        between: ['urban', 'flood'],
        tension: 'GREEN suitability coincides with HIGH flood risk.',
        resolution: 'Allow development only with comprehensive flood mitigation.',
      },
    ],
    conditions: ['Complete a site-specific hydraulic study.'],
    priority_actions: ['Commission a flood study.'],
    evidence_gaps: ['No building assessment was provided.'],
  },
  detected_conflicts: [
    {
      type: 'growth_pressure_vs_flood_exposure',
      severity: 'high',
      between: ['urban', 'flood'],
      description: 'Growth pressure meets flood exposure.',
      implication: 'Expansion should not proceed unrestricted.',
    },
  ],
  domain_signals: {},
  interpretation_source: 'llm',
  llm_model: 'openai/gpt-oss-120b',
  note: null,
};

describe('CoordinatorPanel', () => {
  it('renders the verdict in plain language', () => {
    render(<CoordinatorPanel result={RESULT} />);
    expect(screen.getByRole('heading', { name: 'Only with strong protection' })).toBeInTheDocument();
    expect(screen.getByText('Proceed only with strong flood mitigation.')).toBeInTheDocument();
  });

  it('keeps the machine-readable verdict visible for evaluators', () => {
    render(<CoordinatorPanel result={RESULT} />);
    expect(screen.getByText('proceed_with_strong_mitigation')).toBeInTheDocument();
  });

  it('names the LLM and states that the numbers are not its own', () => {
    render(<CoordinatorPanel result={RESULT} />);
    expect(screen.getByText('openai/gpt-oss-120b')).toBeInTheDocument();
    expect(
      screen.getByText(/numbers come from the models, not the language model/i),
    ).toBeInTheDocument();
  });

  it('says clearly when no LLM was involved', () => {
    render(
      <CoordinatorPanel
        result={{
          ...RESULT,
          interpretation_source: 'deterministic_fallback',
          llm_model: null,
          note: 'Groq rate limit reached.',
        }}
      />,
    );
    expect(screen.getByText(/no language model was used/i)).toBeInTheDocument();
    expect(screen.getByText(/Groq rate limit reached/)).toBeInTheDocument();
  });

  it('shows the trade-offs and how to resolve them', () => {
    render(<CoordinatorPanel result={RESULT} />);
    expect(screen.getByText('GREEN suitability coincides with HIGH flood risk.')).toBeInTheDocument();
    expect(
      screen.getByText(/Allow development only with comprehensive flood mitigation/),
    ).toBeInTheDocument();
  });

  it('shows what the assessment does not know', () => {
    render(<CoordinatorPanel result={RESULT} />);
    expect(screen.getByText('What this assessment does not know')).toBeInTheDocument();
    expect(screen.getByText('No building assessment was provided.')).toBeInTheDocument();
  });

  it('explains that conflict detection is deterministic, not the LLM', async () => {
    render(<CoordinatorPanel result={RESULT} />);
    await userEvent.click(screen.getByRole('button', { name: /Rule-detected conflicts/ }));
    expect(
      screen.getByText(/found by deterministic rules, not by the language model/i),
    ).toBeInTheDocument();
  });

  it('renders each verdict type with its own wording', () => {
    const cases = {
      proceed: 'Go ahead',
      proceed_with_conditions: 'Go ahead with conditions',
      discourage: 'Not recommended',
      insufficient_evidence: 'Not enough evidence',
    };
    for (const [verdict, label] of Object.entries(cases)) {
      const { unmount } = render(
        <CoordinatorPanel
          result={{
            ...RESULT,
            recommendation: { ...RESULT.recommendation, overall_recommendation: verdict },
          }}
        />,
      );
      expect(screen.getByRole('heading', { name: label })).toBeInTheDocument();
      unmount();
    }
  });

  it('prompts for a selection instead of showing an empty assessment', () => {
    render(<CoordinatorPanel result={null} />);
    expect(screen.getByText('No assessment yet')).toBeInTheDocument();
  });

  it('explains the parallel agents while loading', () => {
    render(<CoordinatorPanel loading />);
    expect(screen.getByText(/Running the five agents/)).toBeInTheDocument();
  });
});

describe('AgentNarrative', () => {
  const ANALYSIS = {
    domain: 'flood',
    agent: 'Flood / Resilience Agent',
    source: 'llm',
    result: {
      summary: 'The cell has high flood susceptibility.',
      findings: ['Model 3 predicts 67%.'],
      risks: ['Unmitigated development carries risk.'],
      recommendations: ['Require raised plinths.'],
      uncertainty: 'Labels end in 2018.',
      interpretation_confidence: 'high',
    },
  };

  it('shows the agent summary once opened', async () => {
    render(<AgentNarrative domain="flood" analysis={ANALYSIS} />);
    await userEvent.click(screen.getByRole('button', { name: /Flood & Resilience/ }));
    expect(screen.getByText('The cell has high flood susceptibility.')).toBeInTheDocument();
    expect(screen.getByText('Labels end in 2018.')).toBeInTheDocument();
  });

  it('distinguishes interpretation confidence from a model probability', async () => {
    render(<AgentNarrative domain="flood" analysis={ANALYSIS} />);
    await userEvent.click(screen.getByRole('button', { name: /Flood & Resilience/ }));
    expect(screen.getByText(/not a model probability/i)).toBeInTheDocument();
  });

  it('renders nothing without an analysis', () => {
    const { container } = render(<AgentNarrative domain="flood" analysis={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
