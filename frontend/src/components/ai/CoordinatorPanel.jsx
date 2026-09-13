import { Bot, GitMerge, ListChecks, ShieldAlert, Sparkles, TriangleAlert } from 'lucide-react';

import { Badge, Card, Disclosure, EmptyState, ErrorState, Loading } from '../ui';
import { DOMAIN_META, VERDICT } from '../../lib/domain';

/**
 * The Coordinator's synthesis.
 *
 * The verdict and the trade-offs come from the backend, where conflict detection
 * and the headline decision are deterministic and the LLM only narrates them.
 * This component shows which of the two produced the text on screen, so a reader
 * always knows whether an LLM was involved.
 */

function InterpretationSource({ source, model, note }) {
  const isLlm = source === 'llm';
  return (
    <div className="flex items-start gap-2 text-[11px] text-mist-faint">
      {isLlm ? (
        <Sparkles size={12} className="text-water shrink-0 mt-0.5" />
      ) : (
        <Bot size={12} className="shrink-0 mt-0.5" />
      )}
      <span className="leading-relaxed">
        {isLlm ? (
          <>
            Explanation written by <span className="font-mono text-mist-muted">{model}</span>,
            interpreting the model outputs. The numbers come from the models, not the
            language model.
          </>
        ) : (
          <>
            Written deterministically from the model outputs — no language model was used.
            {note && <span className="block mt-1 text-mist-faint/80">{note}</span>}
          </>
        )}
      </span>
    </div>
  );
}

export default function CoordinatorPanel({ result, loading, error, onRetry }) {
  if (loading) {
    return (
      <Card>
        <Loading label="Running the five agents…" />
        <p className="text-center text-[11px] text-mist-faint -mt-6">
          Water, urban and flood agents run in parallel, then the Coordinator reconciles them.
        </p>
      </Card>
    );
  }
  if (error) return <ErrorState error={error} onRetry={onRetry} />;
  if (!result) {
    return (
      <Card>
        <EmptyState icon={GitMerge} title="No assessment yet">
          Select a grid square on the map to run the full multi-agent analysis.
        </EmptyState>
      </Card>
    );
  }

  const recommendation = result.recommendation;
  const verdict = VERDICT[recommendation?.overall_recommendation] ?? VERDICT.insufficient_evidence;

  return (
    <div className="space-y-3">
      {/* ── Headline verdict ────────────────────────────────────────────── */}
      <Card className="relative overflow-hidden">
        <div
          className="absolute inset-x-0 top-0 h-0.5"
          style={{ backgroundColor: verdict.color }}
          aria-hidden="true"
        />
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0">
            <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
              Overall recommendation
            </p>
            <h3
              className="font-display text-xl font-semibold leading-tight"
              style={{ color: verdict.color }}
            >
              {verdict.label}
            </h3>
          </div>
          <Badge tone={verdict.tone}>{recommendation.overall_recommendation}</Badge>
        </div>

        <p className="text-sm text-mist leading-relaxed">{recommendation.headline}</p>
        <p className="text-xs text-mist-muted mt-3 leading-relaxed">{recommendation.rationale}</p>

        <div className="mt-4 pt-3 border-t border-white/5">
          <InterpretationSource
            source={result.interpretation_source}
            model={result.llm_model}
            note={result.note}
          />
        </div>
      </Card>

      {/* ── Trade-offs ──────────────────────────────────────────────────── */}
      {recommendation.trade_offs?.length > 0 && (
        <Card>
          <p className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wide text-conditional-light mb-3">
            <TriangleAlert size={13} />
            Trade-offs ({recommendation.trade_offs.length})
          </p>
          <ul className="space-y-3">
            {recommendation.trade_offs.map((tradeOff, i) => (
              <li key={i} className="border-l-2 border-conditional/40 pl-3">
                <p className="flex flex-wrap items-center gap-1.5 mb-1.5">
                  {tradeOff.between.map((domain) => (
                    <Badge key={domain} tone="neutral">
                      {DOMAIN_META[domain]?.label ?? domain}
                    </Badge>
                  ))}
                </p>
                <p className="text-xs text-mist leading-relaxed">{tradeOff.tension}</p>
                <p className="text-xs text-mist-muted leading-relaxed mt-1.5">
                  <span className="text-conditional-light font-medium">Resolution: </span>
                  {tradeOff.resolution}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ── Conditions and actions ──────────────────────────────────────── */}
      {(recommendation.conditions?.length > 0 || recommendation.priority_actions?.length > 0) && (
        <Card>
          {recommendation.priority_actions?.length > 0 && (
            <div className="mb-4">
              <p className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wide text-water mb-2">
                <ListChecks size={13} />
                Do these first
              </p>
              <ol className="space-y-2">
                {recommendation.priority_actions.map((action, i) => (
                  <li key={i} className="flex gap-2.5 text-xs text-mist leading-relaxed">
                    <span className="font-mono text-water shrink-0">{i + 1}.</span>
                    <span>{action}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {recommendation.conditions?.length > 0 && (
            <div>
              <p className="flex items-center gap-2 text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-2">
                <ShieldAlert size={13} />
                Required conditions
              </p>
              <ul className="space-y-2">
                {recommendation.conditions.map((condition, i) => (
                  <li key={i} className="flex gap-2.5 text-xs text-mist-muted leading-relaxed">
                    <span className="text-earth shrink-0">·</span>
                    <span>{condition}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {/* ── Evidence gaps: what is NOT known ───────────────────────────── */}
      {recommendation.evidence_gaps?.length > 0 && (
        <Card>
          <p className="text-[11px] font-mono uppercase tracking-wide text-earth-light mb-2">
            What this assessment does not know
          </p>
          <ul className="space-y-1.5">
            {recommendation.evidence_gaps.map((gap, i) => (
              <li key={i} className="flex gap-2 text-xs text-mist-muted leading-relaxed">
                <span className="text-earth shrink-0">·</span>
                <span>{gap}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ── Detected conflicts: the deterministic layer ─────────────────── */}
      {result.detected_conflicts?.length > 0 && (
        <Disclosure
          title="Rule-detected conflicts"
          subtitle={`${result.detected_conflicts.length} found before the LLM ran`}
          icon={GitMerge}
        >
          <p className="text-[11px] text-mist-faint mb-3 leading-relaxed">
            These are found by deterministic rules, not by the language model, so a real
            conflict cannot be missed because the LLM overlooked it. Any conflict the LLM
            omits is appended to the trade-offs above.
          </p>
          <ul className="space-y-2.5">
            {result.detected_conflicts.map((conflict) => (
              <li key={conflict.type} className="border-l-2 border-white/10 pl-3">
                <p className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] font-mono text-mist-muted">{conflict.type}</span>
                  <Badge
                    tone={
                      conflict.severity === 'high'
                        ? 'red'
                        : conflict.severity === 'moderate'
                          ? 'yellow'
                          : 'neutral'
                    }
                  >
                    {conflict.severity}
                  </Badge>
                </p>
                <p className="text-xs text-mist-muted leading-relaxed">{conflict.description}</p>
                <p className="text-xs text-mist-faint leading-relaxed mt-1">
                  {conflict.implication}
                </p>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}
    </div>
  );
}

/** One domain agent's interpretation. */
export function AgentNarrative({ domain, analysis }) {
  if (!analysis) return null;
  const meta = DOMAIN_META[domain] ?? { label: domain, model: '' };
  const { result } = analysis;

  return (
    <Disclosure
      title={meta.label}
      subtitle={`${analysis.source === 'llm' ? 'AI interpretation' : 'Deterministic summary'} · ${meta.model}`}
      icon={analysis.source === 'llm' ? Sparkles : Bot}
    >
      <div className="space-y-3">
        <p className="text-xs text-mist leading-relaxed">{result.summary}</p>

        {result.findings?.length > 0 && (
          <NarrativeList title="What the evidence shows" items={result.findings} tone="text-water" />
        )}
        {result.risks?.length > 0 && (
          <NarrativeList title="Risks" items={result.risks} tone="text-conditional-light" />
        )}
        {result.recommendations?.length > 0 && (
          <NarrativeList
            title="Recommendations"
            items={result.recommendations}
            tone="text-suitable-light"
          />
        )}
        {result.uncertainty && (
          <div>
            <p className="text-[11px] font-mono uppercase tracking-wide text-earth-light mb-1">
              Uncertainty
            </p>
            <p className="text-xs text-mist-muted leading-relaxed">{result.uncertainty}</p>
          </div>
        )}

        <p className="text-[10px] text-mist-faint pt-2 border-t border-white/5">
          Interpretation confidence: {result.interpretation_confidence}. This is the
          agent&apos;s confidence in its own reading, not a model probability.
        </p>
      </div>
    </Disclosure>
  );
}

function NarrativeList({ title, items, tone }) {
  return (
    <div>
      <p className={`text-[11px] font-mono uppercase tracking-wide mb-1 ${tone}`}>{title}</p>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2 text-xs text-mist-muted leading-relaxed">
            <span className="text-mist-faint shrink-0">·</span>
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
