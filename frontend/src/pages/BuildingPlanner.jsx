import {
  BookOpen,
  Building2,
  CloudRain,
  Hammer,
  Home,
  Info,
  Sparkles,
  Sun,
  Thermometer,
  Waves,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import {
  Badge,
  Button,
  Card,
  Disclaimer,
  Disclosure,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  PageHeader,
  SectionTitle,
  Select,
} from '../components/ui';
import { FLOOD_RISK, PRIORITY, decimal, humanise, number, percent } from '../lib/domain';
import { getCities, planBuilding } from '../api/client';
import { useAction, useAsync } from '../hooks/useAsync';

const BUILDING_TYPES = [
  { value: 'residential', label: 'Home' },
  { value: 'office', label: 'Office' },
  { value: 'commercial', label: 'Commercial' },
];

const CATEGORY_ICONS = {
  water: Waves,
  energy: Sun,
  thermal_comfort: Thermometer,
  flood_resilience: CloudRain,
  green_cover: Home,
  site_planning: Building2,
};

const INITIAL = {
  building_type: 'residential',
  plot_size_sqm: 250,
  floors: 2,
  occupants: 4,
  budget_inr: '',
  roof_area_sqm: '',
  requirements: '',
};

export default function BuildingPlanner() {
  const [form, setForm] = useState(INITIAL);
  const [city, setCity] = useState(null);
  const [coords, setCoords] = useState({ lat: '', lon: '' });
  const [errors, setErrors] = useState({});

  const cities = useAsync(useCallback((signal) => getCities({ signal }), []), []);

  // Default the location to the first city's centre, so the form is usable
  // immediately without the user hunting for coordinates.
  useEffect(() => {
    if (!city && cities.data?.cities?.length) {
      const first = cities.data.cities[0];
      setCity(first.city);
      setCoords({ lat: String(first.lat), lon: String(first.lon) });
    }
  }, [cities.data, city]);

  const plan = useAction(useCallback((payload) => planBuilding(payload), []));

  const update = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const onCityChange = (event) => {
    const next = cities.data.cities.find((c) => c.city === event.target.value);
    setCity(next.city);
    setCoords({ lat: String(next.lat), lon: String(next.lon) });
  };

  const validate = () => {
    const found = {};
    const lat = Number(coords.lat);
    const lon = Number(coords.lon);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90) found.lat = 'Must be between -90 and 90.';
    if (!Number.isFinite(lon) || lon < -180 || lon > 180)
      found.lon = 'Must be between -180 and 180.';
    if (!(Number(form.plot_size_sqm) > 0)) found.plot_size_sqm = 'Must be greater than zero.';
    if (!(Number(form.floors) >= 1)) found.floors = 'At least one floor.';
    if (!(Number(form.occupants) >= 1)) found.occupants = 'At least one occupant.';
    if (form.roof_area_sqm && Number(form.roof_area_sqm) > Number(form.plot_size_sqm))
      found.roof_area_sqm = 'Roof area cannot exceed the plot size.';
    setErrors(found);
    return Object.keys(found).length === 0;
  };

  const submit = (event) => {
    event.preventDefault();
    if (!validate()) return;
    plan.run({
      lat: Number(coords.lat),
      lon: Number(coords.lon),
      building_type: form.building_type,
      plot_size_sqm: Number(form.plot_size_sqm),
      floors: Number(form.floors),
      occupants: Number(form.occupants),
      budget_inr: form.budget_inr ? Number(form.budget_inr) : null,
      roof_area_sqm: form.roof_area_sqm ? Number(form.roof_area_sqm) : null,
      requirements: form.requirements
        ? form.requirements.split(',').map((s) => s.trim()).filter(Boolean)
        : [],
    });
  };

  return (
    <main className="flex-1 min-w-0 px-6 lg:px-8 py-7 overflow-y-auto scrollbar-thin">
      <PageHeader
        title="Sustainable Building Planner"
        subtitle="Tell us about your plot and we will use its real climate, flood and water conditions to suggest what to build in."
      />

      <div className="grid xl:grid-cols-[22rem_1fr] gap-6 items-start">
        {/* ── Form ───────────────────────────────────────────────────── */}
        <form onSubmit={submit} noValidate className="xl:sticky xl:top-7 space-y-4">
          <Card>
            <SectionTitle hint="Where you plan to build">Location</SectionTitle>
            <div className="space-y-3">
              <Field label="City" htmlFor="city">
                <Select id="city" value={city ?? ''} onChange={onCityChange}>
                  {(cities.data?.cities ?? []).map((c) => (
                    <option key={c.city} value={c.city}>
                      {c.city}, {c.state}
                    </option>
                  ))}
                </Select>
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Latitude" htmlFor="lat" error={errors.lat}>
                  <Input
                    id="lat"
                    type="number"
                    step="0.0001"
                    value={coords.lat}
                    onChange={(e) => setCoords((c) => ({ ...c, lat: e.target.value }))}
                  />
                </Field>
                <Field label="Longitude" htmlFor="lon" error={errors.lon}>
                  <Input
                    id="lon"
                    type="number"
                    step="0.0001"
                    value={coords.lon}
                    onChange={(e) => setCoords((c) => ({ ...c, lon: e.target.value }))}
                  />
                </Field>
              </div>
              <p className="text-[10px] text-mist-faint leading-relaxed">
                Selecting a city fills in its centre. Adjust the coordinates for your actual
                plot — the assessment uses the nearest analysed square.
              </p>
            </div>
          </Card>

          <Card>
            <SectionTitle hint="What you plan to build">Building</SectionTitle>
            <div className="space-y-3">
              <Field label="Type" htmlFor="building_type">
                <Select
                  id="building_type"
                  value={form.building_type}
                  onChange={update('building_type')}
                >
                  {BUILDING_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </Select>
              </Field>

              <div className="grid grid-cols-2 gap-3">
                <Field
                  label="Plot size (m²)"
                  htmlFor="plot_size_sqm"
                  error={errors.plot_size_sqm}
                >
                  <Input
                    id="plot_size_sqm"
                    type="number"
                    min="1"
                    value={form.plot_size_sqm}
                    onChange={update('plot_size_sqm')}
                  />
                </Field>
                <Field label="Floors" htmlFor="floors" error={errors.floors}>
                  <Input
                    id="floors"
                    type="number"
                    min="1"
                    value={form.floors}
                    onChange={update('floors')}
                  />
                </Field>
                <Field label="Occupants" htmlFor="occupants" error={errors.occupants}>
                  <Input
                    id="occupants"
                    type="number"
                    min="1"
                    value={form.occupants}
                    onChange={update('occupants')}
                  />
                </Field>
                <Field
                  label="Roof area (m²)"
                  htmlFor="roof_area_sqm"
                  hint="Optional"
                  error={errors.roof_area_sqm}
                >
                  <Input
                    id="roof_area_sqm"
                    type="number"
                    min="1"
                    placeholder="estimated"
                    value={form.roof_area_sqm}
                    onChange={update('roof_area_sqm')}
                  />
                </Field>
              </div>

              <Field label="Budget (₹)" htmlFor="budget_inr" hint="Optional">
                <Input
                  id="budget_inr"
                  type="number"
                  min="0"
                  placeholder="e.g. 4000000"
                  value={form.budget_inr}
                  onChange={update('budget_inr')}
                />
              </Field>

              <Field
                label="Requirements"
                htmlFor="requirements"
                hint="Optional, comma separated"
              >
                <Input
                  id="requirements"
                  placeholder="garden, low maintenance"
                  value={form.requirements}
                  onChange={update('requirements')}
                />
              </Field>
            </div>
          </Card>

          <Button type="submit" icon={Hammer} loading={plan.loading} className="w-full">
            Get recommendations
          </Button>
        </form>

        {/* ── Results ────────────────────────────────────────────────── */}
        <div className="min-w-0 space-y-5">
          {plan.error && <ErrorState error={plan.error} />}

          {!plan.data && !plan.error && (
            <Card>
              <EmptyState icon={Building2} title="Fill in your plot details">
                We will look up the real flood risk, water conditions, rainfall and sunshine
                at your location, then work out what is worth building in.
              </EmptyState>
            </Card>
          )}

          {plan.data && <PlanResult plan={plan.data} />}
        </div>
      </div>
    </main>
  );
}

// ── Results ────────────────────────────────────────────────────────────────

function PlanResult({ plan }) {
  const { site, recommendations, skipped_rules: skipped, priority_counts: counts } = plan;
  const climate = site.measured?.climate;
  const flood = site.model_predictions?.flood_risk;
  const derived = site.derived ?? {};

  return (
    <>
      <Disclaimer>{plan.disclaimer}</Disclaimer>

      {/* ── Site conditions ─────────────────────────────────────────── */}
      <SectionTitle hint={`Nearest analysed square: ${site.location.grid_id}`}>
        Your site
      </SectionTitle>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <Condition
          icon={CloudRain}
          label="Flood risk"
          value={FLOOD_RISK[flood?.risk_level]?.label ?? 'Unknown'}
          detail={flood ? `${percent(flood.flood_probability)} chance` : 'Model unavailable'}
          tone={FLOOD_RISK[flood?.risk_level]?.tone ?? 'neutral'}
        />
        <Condition
          icon={Sun}
          label="Sunshine"
          value={
            derived.solar_potential
              ? humanise(derived.solar_potential.classification)
              : 'Unknown'
          }
          detail={
            derived.solar_potential
              ? `${decimal(derived.solar_potential.irradiance_kwh_m2_day, 2)} kWh/m²/day`
              : 'NASA POWER unavailable'
          }
          tone="earth"
        />
        <Condition
          icon={Waves}
          label="Rainfall"
          value={
            derived.rainfall_regime ? `${number(derived.rainfall_regime.annual_mm)} mm` : 'Unknown'
          }
          detail={
            derived.rainfall_regime
              ? `${percent(derived.rainfall_regime.monsoon_concentration)} in the monsoon`
              : 'NASA POWER unavailable'
          }
          tone="water"
        />
        <Condition
          icon={Home}
          label="Surroundings"
          value={
            derived.green_cover ? humanise(derived.green_cover.classification) : 'Unknown'
          }
          detail={
            derived.green_cover
              ? `${percent(derived.green_cover.built_fraction)} built up`
              : 'Model unavailable'
          }
          tone="green"
        />
      </div>

      {climate && (
        <Card>
          <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-3">
            Measured climate at this location
          </p>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-x-6">
            <KeyValue label="Average temperature" value={`${decimal(climate.temperature_c, 1)} °C`} />
            <KeyValue label="Record high" value={`${decimal(climate.temperature_max_c, 1)} °C`} />
            <KeyValue label="Record low" value={`${decimal(climate.temperature_min_c, 1)} °C`} />
            <KeyValue label="Humidity" value={`${decimal(climate.humidity_pct, 0)}%`} />
            <KeyValue label="Wind speed" value={`${decimal(climate.wind_speed_m_s, 1)} m/s`} />
            <KeyValue label="Wettest month" value={climate.wettest_month} />
          </div>
          <p className="text-[10px] text-mist-faint mt-3">
            Source: NASA POWER long-term climatology. Record high and low are the most
            extreme temperatures observed at this location, not typical seasonal values.
          </p>
        </Card>
      )}

      {/* ── AI interpretation ───────────────────────────────────────── */}
      {plan.interpretation && <Interpretation interpretation={plan.interpretation} />}

      {/* ── Recommendations ─────────────────────────────────────────── */}
      <SectionTitle
        hint={`${counts.HIGH} to do first · ${counts.MEDIUM} worth doing · ${counts.LOW} nice to have`}
      >
        Recommendations for your plot
      </SectionTitle>

      <div className="space-y-3">
        {recommendations.map((rec, i) => (
          <RecommendationCard key={i} rec={rec} />
        ))}
      </div>

      {/* ── Rules that did not fire ─────────────────────────────────── */}
      {skipped?.length > 0 && (
        <Disclosure
          title="What we did not recommend, and why"
          subtitle={`${skipped.length} rule${skipped.length === 1 ? '' : 's'} did not apply`}
          icon={Info}
        >
          <p className="text-[11px] text-mist-faint mb-3 leading-relaxed">
            A measure is only suggested when the site conditions actually call for it. Where
            the evidence was missing, that is said plainly rather than guessed at.
          </p>
          <ul className="space-y-2.5">
            {skipped.map((rule, i) => (
              <li key={i} className="border-l-2 border-white/10 pl-3">
                <p className="text-xs font-medium text-mist">{rule.rule}</p>
                <p className="text-xs text-mist-muted leading-relaxed mt-0.5">{rule.reason}</p>
              </li>
            ))}
          </ul>
        </Disclosure>
      )}

      {/* ── Guidelines ──────────────────────────────────────────────── */}
      <GuidelinePanel guidelines={plan.guidelines_applied} />

      {/* ── Missing evidence ────────────────────────────────────────── */}
      {Object.keys(site.unavailable ?? {}).length > 0 && (
        <Card>
          <p className="text-[11px] font-mono uppercase tracking-wide text-earth-light mb-2">
            Evidence we could not retrieve
          </p>
          <ul className="space-y-1.5">
            {Object.entries(site.unavailable).map(([source, detail]) => (
              <li key={source} className="text-xs text-mist-muted leading-relaxed">
                <span className="font-mono text-mist">{humanise(source)}</span>: {detail.message}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function Condition({ icon: Icon, label, value, detail, tone }) {
  const color = {
    green: 'text-suitable-light',
    yellow: 'text-conditional-light',
    red: 'text-avoid-light',
    water: 'text-water',
    earth: 'text-earth-light',
    neutral: 'text-mist-muted',
  }[tone];

  return (
    <Card>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={color} />
        <p className="text-[11px] font-mono tracking-wide text-mist-muted uppercase">{label}</p>
      </div>
      <p className={`font-display text-lg font-semibold ${color}`}>{value}</p>
      <p className="text-xs text-mist-muted mt-0.5">{detail}</p>
    </Card>
  );
}

function Interpretation({ interpretation }) {
  const { result, source, llm_model: model } = interpretation;

  return (
    <Card>
      <div className="flex items-center gap-2 mb-3">
        <Sparkles size={14} className="text-water" />
        <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted">
          What this means for you
        </p>
      </div>
      <p className="text-sm text-mist leading-relaxed">{result.summary}</p>

      {result.recommendations?.length > 0 && (
        <ol className="space-y-2 mt-4">
          {result.recommendations.map((item, i) => (
            <li key={i} className="flex gap-2.5 text-xs text-mist-muted leading-relaxed">
              <span className="font-mono text-water shrink-0">{i + 1}.</span>
              <span>{item}</span>
            </li>
          ))}
        </ol>
      )}

      {result.uncertainty && (
        <p className="text-[11px] text-mist-faint leading-relaxed mt-4 pt-3 border-t border-white/5">
          {result.uncertainty}
        </p>
      )}

      <p className="text-[10px] text-mist-faint mt-3">
        {source === 'llm' ? (
          <>
            Written by <span className="font-mono">{model}</span>, explaining the
            rule-based recommendations. It cannot change any of them.
          </>
        ) : (
          'Written deterministically from the rules — no language model was used.'
        )}
      </p>
    </Card>
  );
}

function RecommendationCard({ rec }) {
  const Icon = CATEGORY_ICONS[rec.category] ?? Building2;
  const priority = PRIORITY[rec.priority] ?? { label: rec.priority, tone: 'neutral' };

  return (
    <Card>
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-start gap-2.5 min-w-0">
          <span className="w-8 h-8 rounded-lg bg-white/[0.05] flex items-center justify-center shrink-0">
            <Icon size={15} className="text-mist-muted" />
          </span>
          <div className="min-w-0">
            <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted">
              {humanise(rec.category)}
            </p>
            <h3 className="font-display text-sm font-semibold text-mist mt-0.5 leading-snug">
              {rec.recommendation}
            </h3>
          </div>
        </div>
        <Badge tone={priority.tone}>{priority.label}</Badge>
      </div>

      <p className="text-xs text-mist-muted leading-relaxed mt-3">{rec.reason}</p>

      <div className="mt-3 space-y-2">
        <Disclosure title="How we worked this out" subtitle="Inputs and calculations">
          <div className="space-y-3">
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wide text-water mb-1.5">
                What triggered this
              </p>
              <div className="grid sm:grid-cols-2 gap-x-5">
                {Object.entries(rec.triggering_data).map(([key, value]) => (
                  <KeyValue
                    key={key}
                    label={humanise(key)}
                    value={
                      value == null
                        ? undefined
                        : Array.isArray(value)
                          ? value.join(', ') || '—'
                          : typeof value === 'number'
                            ? decimal(value, 3)
                            : String(value)
                    }
                  />
                ))}
              </div>
            </div>

            <div>
              <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
                Calculations
              </p>
              <div className="grid sm:grid-cols-2 gap-x-5">
                {Object.entries(rec.calculations)
                  .filter(([key]) => key !== 'formula')
                  .map(([key, value]) => (
                    <KeyValue
                      key={key}
                      label={humanise(key)}
                      value={typeof value === 'number' ? number(value, 2) : String(value)}
                    />
                  ))}
              </div>
              {rec.calculations.formula && (
                <p className="text-[10px] font-mono text-mist-faint mt-2 bg-ink rounded-lg px-3 py-2 overflow-x-auto">
                  {rec.calculations.formula}
                </p>
              )}
            </div>

            {rec.guideline_basis?.length > 0 && (
              <div>
                <p className="text-[11px] font-mono uppercase tracking-wide text-earth-light mb-1.5">
                  Guidelines used
                </p>
                <ul className="space-y-2">
                  {rec.guideline_basis.map((basis) => (
                    <li key={basis.parameter} className="text-[11px] leading-relaxed">
                      <span className="font-mono text-mist">
                        {basis.parameter} = {basis.value} {basis.unit}
                      </span>
                      <Badge
                        tone={basis.origin === 'guideline' ? 'water' : 'neutral'}
                        className="ml-2"
                      >
                        {basis.origin === 'guideline' ? 'published' : 'assumption'}
                      </Badge>
                      {basis.source_title && (
                        <span className="block text-mist-faint mt-0.5">
                          {basis.source_title}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </Disclosure>
      </div>
    </Card>
  );
}

function GuidelinePanel({ guidelines }) {
  if (!guidelines) return null;

  return (
    <Disclosure
      title="Guidelines and standards referenced"
      subtitle="Sources, and what they do and do not certify"
      icon={BookOpen}
    >
      <div className="space-y-4">
        <p className="text-xs text-mist-muted leading-relaxed">{guidelines.regulatory_status}</p>

        <div className="space-y-2.5">
          {Object.entries(guidelines.sources).map(([key, source]) => (
            <div key={key} className="border-l-2 border-earth/30 pl-3">
              <p className="text-xs font-medium text-mist">{source.title}</p>
              <p className="text-[11px] text-mist-muted mt-0.5">{source.publisher}</p>
              <p className="text-[11px] text-mist-faint mt-1 leading-relaxed">{source.scope}</p>
            </div>
          ))}
        </div>
      </div>
    </Disclosure>
  );
}
