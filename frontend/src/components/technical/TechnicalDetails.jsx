import { BarChart3, FlaskConical, Info, Sigma } from 'lucide-react';

import { Disclosure, KeyValue, Meter } from '../ui';
import { decimal, humanise, percent } from '../../lib/domain';

/**
 * Technical detail panels, collapsed by default.
 *
 * A citizen sees the plain-language result; an evaluator opens these for the
 * model name, prediction, feature attributions, validation metrics and stated
 * limitations. Everything shown comes from the API — nothing is recomputed here.
 */

/** Top SHAP contributions for one prediction. */
export function FeatureAttribution({ attribution, positiveLabel, negativeLabel }) {
  if (attribution === null) {
    return (
      <p className="text-xs text-mist-faint">
        Feature attributions are unavailable — SHAP is not installed on the backend. No
        approximation is shown in its place.
      </p>
    );
  }
  if (!attribution?.length) {
    return <p className="text-xs text-mist-faint">No attribution was returned.</p>;
  }

  return (
    <div className="space-y-2.5">
      <p className="text-[11px] text-mist-faint leading-relaxed">
        SHAP values for this single prediction. Bars show each feature&apos;s share of the
        total attribution; the arrow shows which way it pushed the result.
      </p>
      {attribution.map((item) => (
        <div key={item.feature}>
          <div className="flex items-baseline justify-between gap-2 mb-1">
            <span className="text-xs text-mist truncate">{humanise(item.feature)}</span>
            <span className="text-[11px] font-mono shrink-0 flex items-center gap-1.5">
              <span
                className={item.direction === 'positive' ? 'text-avoid-light' : 'text-suitable-light'}
                title={item.direction === 'positive' ? positiveLabel : negativeLabel}
              >
                {item.direction === 'positive' ? '▲' : item.direction === 'negative' ? '▼' : '—'}
              </span>
              <span className="text-mist-muted">{percent(item.importance, 1)}</span>
            </span>
          </div>
          <Meter
            value={item.importance}
            tone={item.direction === 'positive' ? 'red' : 'green'}
            showPercent={false}
          />
        </div>
      ))}
      <p className="text-[10px] text-mist-faint pt-1">
        <span className="text-avoid-light">▲</span> {positiveLabel} ·{' '}
        <span className="text-suitable-light">▼</span> {negativeLabel}
      </p>
    </div>
  );
}

/** Validation metrics and limitations for a model. */
export function ModelMetrics({ metrics, loading, error }) {
  if (loading) return <p className="text-xs text-mist-muted">Loading metrics…</p>;
  if (error) return <p className="text-xs text-alert-light">Metrics unavailable: {error.message}</p>;
  if (!metrics) return null;

  const selected = metrics.selected_model_metrics;
  const cv = metrics.cross_validation;
  const split = metrics.city_split;

  return (
    <div className="space-y-4">
      <div>
        <KeyValue label="Model" value={metrics.model} mono={false} />
        <KeyValue label="Algorithm" value={metrics.algorithm} />
        <KeyValue label="Task" value={metrics.task} mono={false} />
        {metrics.target_definition && (
          <KeyValue label="Target" value={metrics.target_definition} mono={false} />
        )}
        {metrics.decision_threshold != null && (
          <KeyValue label="Decision threshold" value={decimal(metrics.decision_threshold, 4)} />
        )}
      </div>

      {metrics.validation_strategy && (
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
            Validation
          </p>
          <p className="text-xs text-mist-muted leading-relaxed">{metrics.validation_strategy}</p>
          {split && (
            <p className="text-[11px] font-mono text-mist-faint mt-2">
              {split.train_cities?.length} train · {split.val_cities?.length} validation ·{' '}
              {split.test_cities?.length} unseen test cities
            </p>
          )}
        </div>
      )}

      {selected && (
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
            Unseen-city test performance
          </p>
          <div className="grid grid-cols-2 gap-x-4">
            {['precision', 'recall', 'f1', 'roc_auc', 'pr_auc'].map(
              (key) =>
                selected[key] != null && (
                  <KeyValue key={key} label={humanise(key)} value={decimal(selected[key], 4)} />
                ),
            )}
          </div>
        </div>
      )}

      {cv && (
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
            Cross-validation
          </p>
          <div className="grid grid-cols-2 gap-x-4">
            <KeyValue label="Accuracy" value={decimal(cv.mean_accuracy, 4)} />
            <KeyValue label="F1" value={decimal(cv.mean_f1, 4)} />
            <KeyValue label="ROC-AUC" value={decimal(cv.mean_roc_auc, 4)} />
            <KeyValue label="Std (accuracy)" value={decimal(cv.std_accuracy, 4)} />
          </div>
        </div>
      )}

      {metrics.city_wise_performance?.length > 0 && (
        <CityPerformanceTable rows={metrics.city_wise_performance} />
      )}

      {metrics.metrics_source && (
        <p className="text-[10px] text-mist-faint leading-relaxed border-t border-white/5 pt-2.5">
          Source: {metrics.metrics_source}
        </p>
      )}

      {metrics.limitations?.length > 0 && (
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-earth-light mb-1.5">
            Limitations
          </p>
          <ul className="space-y-1.5">
            {metrics.limitations.map((limitation, i) => (
              <li key={i} className="text-xs text-mist-muted leading-relaxed flex gap-2">
                <span className="text-earth shrink-0">·</span>
                <span>{limitation}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/**
 * Per-city performance. This is the table that tells a user whether the model
 * actually works in their city, so it is shown rather than averaged away.
 */
function CityPerformanceTable({ rows }) {
  const sorted = [...rows].sort((a, b) => (b.f1 ?? 0) - (a.f1 ?? 0));

  return (
    <div>
      <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
        Performance by unseen city
      </p>
      <p className="text-[10px] text-mist-faint mb-2 leading-relaxed">
        Performance varies substantially between cities. Check the row for your city before
        relying on a result.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] font-mono">
          <thead>
            <tr className="text-mist-faint border-b border-white/5">
              <th className="text-left py-1.5 pr-3 font-normal">City</th>
              <th className="text-right py-1.5 px-2 font-normal">F1</th>
              <th className="text-right py-1.5 px-2 font-normal">Prec</th>
              <th className="text-right py-1.5 px-2 font-normal">Rec</th>
              <th className="text-right py-1.5 pl-2 font-normal">AUC</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <tr key={row.city} className="border-b border-white/[0.03] last:border-0">
                <td className="py-1.5 pr-3 text-mist truncate max-w-[9rem]">{row.city}</td>
                <td
                  className={`text-right py-1.5 px-2 ${
                    row.f1 >= 0.6
                      ? 'text-suitable-light'
                      : row.f1 >= 0.4
                        ? 'text-conditional-light'
                        : 'text-avoid-light'
                  }`}
                >
                  {decimal(row.f1, 3)}
                </td>
                <td className="text-right py-1.5 px-2 text-mist-muted">
                  {decimal(row.precision, 3)}
                </td>
                <td className="text-right py-1.5 px-2 text-mist-muted">{decimal(row.recall, 3)}</td>
                <td className="text-right py-1.5 pl-2 text-mist-muted">
                  {decimal(row.roc_auc, 3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Raw model output, for an evaluator who wants the exact payload. */
export function RawPrediction({ prediction }) {
  if (!prediction) return null;

  const skip = new Set(['feature_attribution', 'observed', 'risk_drivers', 'constraints']);
  const scalars = Object.entries(prediction).filter(
    ([key, value]) => !skip.has(key) && (value === null || typeof value !== 'object'),
  );

  return (
    <div className="space-y-3">
      <div className="grid sm:grid-cols-2 gap-x-5">
        {scalars.map(([key, value]) => (
          <KeyValue
            key={key}
            label={humanise(key)}
            value={typeof value === 'number' ? decimal(value, 4) : String(value)}
          />
        ))}
      </div>

      {prediction.observed && (
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-water mb-1.5">
            Measured observations
          </p>
          <p className="text-[10px] text-mist-faint mb-1.5">
            Satellite and terrain measurements, not model output.
          </p>
          <div className="grid sm:grid-cols-2 gap-x-5">
            {Object.entries(prediction.observed).map(([key, value]) => (
              <KeyValue
                key={key}
                label={humanise(key)}
                value={typeof value === 'number' ? decimal(value, 3) : (value ?? undefined)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** The full technical block for one model prediction. */
export default function TechnicalDetails({
  prediction,
  metrics,
  metricsLoading,
  metricsError,
  positiveLabel = 'increased the prediction',
  negativeLabel = 'decreased the prediction',
}) {
  return (
    <div className="space-y-2">
      <Disclosure
        title="Why the model said this"
        subtitle="Top contributing features (SHAP)"
        icon={Sigma}
      >
        <FeatureAttribution
          attribution={prediction?.feature_attribution}
          positiveLabel={positiveLabel}
          negativeLabel={negativeLabel}
        />
      </Disclosure>

      <Disclosure
        title="Model performance and limitations"
        subtitle="How well this model was validated"
        icon={BarChart3}
      >
        <ModelMetrics metrics={metrics} loading={metricsLoading} error={metricsError} />
      </Disclosure>

      <Disclosure title="Raw model output" subtitle="Exact API payload" icon={FlaskConical}>
        <RawPrediction prediction={prediction} />
      </Disclosure>
    </div>
  );
}

/** A compact note explaining what a probability does and does not mean. */
export function UncertaintyNote({ children }) {
  return (
    <p className="text-[11px] text-mist-faint leading-relaxed flex gap-2">
      <Info size={12} className="shrink-0 mt-0.5" />
      <span>{children}</span>
    </p>
  );
}
