import { Droplets, Building2, Waves } from 'lucide-react';

import { Badge, Card, Meter } from '../ui';
import TechnicalDetails, { UncertaintyNote } from '../technical/TechnicalDetails';
import { FLOOD_RISK, SUITABILITY, WATER_CLASS, decimal, percent } from '../../lib/domain';

/**
 * Per-model result cards for a selected grid cell.
 *
 * Each card leads with the plain-language answer and the evidence behind it, then
 * offers the technical detail behind a disclosure. The pattern the spec asks for:
 * not "XGBoost probability = 0.81" up front, but "High flood risk — 81% — because
 * the ground is low and rain is heavy", with the model internals one click away.
 */

function ResultCard({ icon: Icon, domain, headline, tone, probability, probabilityLabel, children }) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <span className="w-8 h-8 rounded-lg bg-white/[0.05] flex items-center justify-center shrink-0">
            <Icon size={15} className="text-mist-muted" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted">
              {domain}
            </p>
            <h3 className="font-display text-base font-semibold text-mist mt-0.5">{headline}</h3>
          </div>
        </div>
        <Badge tone={tone}>{probabilityLabel}</Badge>
      </div>

      {probability != null && (
        <div className="mb-3">
          <Meter value={probability} tone={tone} label={probabilityLabel} />
        </div>
      )}

      {children}
    </Card>
  );
}

/** Measured drivers or constraints — always cite the number that triggered them. */
function EvidenceList({ title, items, emptyText }) {
  if (!items?.length) {
    return emptyText ? <p className="text-xs text-mist-faint">{emptyText}</p> : null;
  }
  return (
    <div>
      <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
        {title}
      </p>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="text-xs text-mist-muted leading-relaxed flex gap-2">
            <span className="text-water shrink-0">·</span>
            <span>{item.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function FloodCard({ prediction, metrics, metricsLoading, metricsError }) {
  if (!prediction) return null;
  const meta = FLOOD_RISK[prediction.risk_level] ?? {};

  return (
    <ResultCard
      icon={Waves}
      domain="Flood risk"
      headline={meta.plain ?? prediction.risk_level}
      tone={meta.tone ?? 'neutral'}
      probability={prediction.flood_probability}
      probabilityLabel={`${percent(prediction.flood_probability)} chance`}
    >
      <p className="text-xs text-mist-muted leading-relaxed mb-3">{meta.description}</p>

      <EvidenceList
        title="Why"
        items={prediction.risk_drivers}
        emptyText="No specific flood drivers were flagged for this square."
      />

      {prediction.risk_level === 'LOW' && (
        <div className="mt-3">
          <UncertaintyNote>
            Low risk means the model found no evidence of flood exposure — not proof that
            this square is safe. The model misses roughly half of flood-prone squares in
            cities it has not seen.
          </UncertaintyNote>
        </div>
      )}

      <div className="mt-4">
        <TechnicalDetails
          prediction={prediction}
          metrics={metrics}
          metricsLoading={metricsLoading}
          metricsError={metricsError}
          positiveLabel="raised the flood probability"
          negativeLabel="lowered the flood probability"
        />
      </div>
    </ResultCard>
  );
}

export function UrbanCard({ prediction, metrics, metricsLoading, metricsError }) {
  if (!prediction) return null;
  const meta = SUITABILITY[prediction.suitability_class] ?? {};

  return (
    <ResultCard
      icon={Building2}
      domain="Room to grow"
      headline={meta.plain ?? prediction.suitability_class}
      tone={meta.tone ?? 'neutral'}
      probability={prediction.suitability_score}
      probabilityLabel={`Score ${decimal(prediction.suitability_score, 2)}`}
    >
      <p className="text-xs text-mist-muted leading-relaxed mb-3">{meta.description}</p>

      {prediction.observed?.built_growth_t0_t1 != null && (
        <p className="text-xs text-mist-muted leading-relaxed mb-3">
          Between {prediction.observed.t0_year} and {prediction.observed.t1_year}, built-up
          land here went from {percent(prediction.observed.built_fraction_t0, 1)} to{' '}
          {percent(prediction.observed.built_fraction_t1, 1)} of the square.
        </p>
      )}

      <EvidenceList
        title="Things to watch"
        items={prediction.constraints}
        emptyText="No site constraints were flagged for this square."
      />

      <div className="mt-3">
        <UncertaintyNote>
          This score reflects where growth actually happened between{' '}
          {prediction.observed?.t0_year} and {prediction.observed?.t1_year}. It measures
          development pressure, not whether growing here is a good idea — that is what the
          flood and water findings are for.
        </UncertaintyNote>
      </div>

      <div className="mt-4">
        <TechnicalDetails
          prediction={prediction}
          metrics={metrics}
          metricsLoading={metricsLoading}
          metricsError={metricsError}
          positiveLabel="pushed towards the predicted class"
          negativeLabel="pushed away from the predicted class"
        />
      </div>
    </ResultCard>
  );
}

export function WaterCard({ prediction, metrics, metricsLoading, metricsError }) {
  if (!prediction) return null;
  const meta = WATER_CLASS[prediction.classification] ?? {};
  const status = prediction.water_body_status ?? {};

  const statusText = {
    permanent: 'Water is here all year round.',
    seasonal: 'Water is here for part of each year.',
    ephemeral: 'Water appears here only occasionally.',
    none: 'No surface water was detected here.',
    unknown: 'The surface-water record for this square is incomplete.',
  }[status.status];

  return (
    <ResultCard
      icon={Droplets}
      domain="Surface water"
      headline={meta.plain ?? prediction.classification}
      tone={meta.tone ?? 'neutral'}
      probability={prediction.water_body_probability}
      probabilityLabel={`${percent(prediction.water_body_probability)} likely`}
    >
      {statusText && <p className="text-xs text-mist-muted leading-relaxed mb-3">{statusText}</p>}

      <div className="grid grid-cols-2 gap-3 text-xs">
        <div>
          <p className="text-mist-faint text-[11px]">Water present</p>
          <p className="text-mist font-mono mt-0.5">
            {status.occurrence_pct != null ? `${decimal(status.occurrence_pct, 1)}% of the time` : '—'}
          </p>
        </div>
        <div>
          <p className="text-mist-faint text-[11px]">Year-to-year reliability</p>
          <p className="text-mist font-mono mt-0.5 capitalize">
            {status.inter_annual_reliability ?? '—'}
          </p>
        </div>
      </div>

      <p className="text-[10px] text-mist-faint mt-3 leading-relaxed">
        These figures are satellite measurements from the Global Surface Water record, not
        model predictions.
      </p>

      <div className="mt-4">
        <TechnicalDetails
          prediction={prediction}
          metrics={metrics}
          metricsLoading={metricsLoading}
          metricsError={metricsError}
          positiveLabel="raised the water-body probability"
          negativeLabel="lowered the water-body probability"
        />
      </div>
    </ResultCard>
  );
}
