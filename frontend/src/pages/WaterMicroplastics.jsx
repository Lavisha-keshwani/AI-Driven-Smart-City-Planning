import { Beaker, Droplets, Microscope, ScanSearch, Waves } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

import ChannelUpload from '../components/microplastic/ChannelUpload';
import { ModelMetrics } from '../components/technical/TechnicalDetails';
import {
  Badge,
  Button,
  Card,
  Disclaimer,
  Disclosure,
  EmptyState,
  ErrorState,
  KeyValue,
  Loading,
  Meter,
  PageHeader,
  SectionTitle,
} from '../components/ui';
import CitySelector from '../components/city/CitySelector';
import {
  analyzeMicroplastic,
  getCities,
  getCityLayer,
  getMetrics,
  getWaterMonitoring,
} from '../api/client';
import { useAction, useAsync } from '../hooks/useAsync';
import { decimal, percent } from '../lib/domain';

const CHANNELS = [
  { key: 'r', channel: 'R', description: 'reflectance' },
  { key: 'a', channel: 'A', description: 'angle of polarisation' },
  { key: 'p', channel: 'P', description: 'degree of polarisation' },
];

export default function WaterMicroplastics() {
  return (
    <main className="flex-1 min-w-0 px-6 lg:px-8 py-7 overflow-y-auto scrollbar-thin">
      <PageHeader
        title="Water & Microplastics"
        subtitle="Surface-water monitoring across a city's one-kilometre grid, and microscopy screening for candidate microplastic particles."
      />
      <div className="grid xl:grid-cols-2 gap-6 items-start">
        <SurfaceWaterSection />
        <MicroplasticSection />
      </div>
    </main>
  );
}

// ── Surface water ──────────────────────────────────────────────────────────

function SurfaceWaterSection() {
  const [city, setCity] = useState(null);

  const cities = useAsync(useCallback((signal) => getCities({ signal }), []), []);
  useEffect(() => {
    if (!city && cities.data?.cities?.length) setCity(cities.data.cities[0]);
  }, [cities.data, city]);

  const cityName = city?.city;

  const monitoring = useAsync(
    useCallback((signal) => getWaterMonitoring(cityName, { signal }), [cityName]),
    [cityName],
    { enabled: Boolean(cityName) },
  );

  const layer = useAsync(
    useCallback(
      (signal) => getCityLayer('water', cityName, { limit: 2000, signal }),
      [cityName],
    ),
    [cityName],
    { enabled: Boolean(cityName) },
  );

  const metrics = useAsync(useCallback((signal) => getMetrics('water', { signal }), []), []);

  const features = layer.data?.features ?? [];
  const waterCells = features.filter((f) => f.properties?.is_water_body).length;
  const summary = monitoring.data?.summary?.[0];

  return (
    <section className="space-y-4">
      <SectionTitle
        hint="Measured from the Global Surface Water satellite record"
        action={
          cities.data?.cities &&
          city && (
            <CitySelector
              cities={cities.data.cities.map((c) => ({ ...c, id: c.city, name: c.city }))}
              selectedCity={{ ...city, id: city.city, name: city.city }}
              onSelect={setCity}
            />
          )
        }
      >
        Surface water monitoring
      </SectionTitle>

      {cities.error && <ErrorState error={cities.error} onRetry={cities.refresh} />}
      {layer.error && <ErrorState error={layer.error} onRetry={layer.refresh} />}

      {(layer.loading || monitoring.loading) && <Loading label="Loading water data…" />}

      {!layer.loading && features.length > 0 && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <StatTile
              icon={Droplets}
              label="Water-body squares"
              value={waterCells.toLocaleString()}
              sublabel={`of ${features.length.toLocaleString()} analysed`}
              tone="water"
            />
            <StatTile
              icon={Waves}
              label="Share of the city"
              value={percent(waterCells / Math.max(features.length, 1), 1)}
              sublabel="classified as water body"
              tone="water"
            />
          </div>

          {summary && (
            <Card>
              <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-3">
                Multi-year water-body record · {summary.city}
              </p>
              <div className="space-y-3">
                <Meter
                  value={summary.pct_permanent}
                  tone="water"
                  label="Present all year round"
                />
                <Meter value={summary.pct_stable} tone="green" label="Stable extent" />
                <div className="grid grid-cols-2 gap-3 pt-1">
                  <KeyValue
                    label="Water squares found"
                    value={summary.n_water_cells?.toLocaleString()}
                  />
                  <KeyValue
                    label="Mean water presence"
                    value={`${decimal(summary.mean_occurrence_pct, 1)}%`}
                  />
                </div>
              </div>
              <p className="text-[10px] text-mist-faint mt-3 leading-relaxed">
                {monitoring.data.basis}
              </p>
            </Card>
          )}

          {monitoring.data && !summary && (
            <Card>
              <p className="text-xs text-mist-muted">
                {monitoring.data.note ??
                  'No multi-year monitoring summary is available for this city.'}
              </p>
            </Card>
          )}

          <Disclosure
            title="Model performance and limitations"
            subtitle="Surface Water Monitoring (Model 1)"
            icon={ScanSearch}
          >
            <ModelMetrics
              metrics={metrics.data}
              loading={metrics.loading}
              error={metrics.error}
            />
          </Disclosure>
        </>
      )}
    </section>
  );
}

function StatTile({ icon: Icon, label, value, sublabel, tone = 'water' }) {
  const color = { water: 'text-water', green: 'text-suitable-light', earth: 'text-earth-light' }[
    tone
  ];
  return (
    <Card>
      <div className="flex items-center gap-2 mb-2">
        <Icon size={14} className={color} />
        <p className="text-[11px] font-mono tracking-wide text-mist-muted uppercase">{label}</p>
      </div>
      <p className={`font-display text-2xl font-semibold ${color}`}>{value}</p>
      {sublabel && <p className="text-xs text-mist-muted mt-1">{sublabel}</p>}
    </Card>
  );
}

// ── Microplastic screening ─────────────────────────────────────────────────

function MicroplasticSection() {
  const [files, setFiles] = useState({ r: null, a: null, p: null });
  const metrics = useAsync(
    useCallback((signal) => getMetrics('microplastics', { signal }), []),
    [],
  );

  const screening = useAction(
    useCallback((payload) => analyzeMicroplastic(payload), []),
  );

  const ready = Boolean(files.r && files.a && files.p);

  const setChannel = (key) => (file) => {
    setFiles((prev) => ({ ...prev, [key]: file }));
    screening.reset();
  };

  return (
    <section className="space-y-4">
      <SectionTitle hint="Upload the three polarimetric channels for one particle">
        Microplastic screening
      </SectionTitle>

      <Disclaimer>
        Image-based screening only. This does not determine chemical composition, polymer
        type, or concentration — confirming a particle is plastic requires FTIR or Raman
        spectroscopy on a prepared sample.
      </Disclaimer>

      <Card>
        <p className="text-xs text-mist-muted leading-relaxed mb-4">
          The model was trained on polarisation microscopy, where each particle is imaged
          three times. All three channels are required: a single reflectance image scores no
          better than chance, so the backend rejects it rather than returning a confident
          but meaningless answer.
        </p>

        <div className="grid grid-cols-3 gap-3">
          {CHANNELS.map(({ key, channel, description }) => (
            <ChannelUpload
              key={key}
              channel={channel}
              description={description}
              file={files[key]}
              onChange={setChannel(key)}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-3 mt-5">
          <p className="text-[11px] text-mist-faint">
            {ready
              ? 'All three channels ready.'
              : `${Object.values(files).filter(Boolean).length} of 3 channels selected.`}
          </p>
          <div className="flex items-center gap-2">
            {(files.r || files.a || files.p) && (
              <Button
                variant="ghost"
                onClick={() => {
                  setFiles({ r: null, a: null, p: null });
                  screening.reset();
                }}
              >
                Reset
              </Button>
            )}
            <Button
              icon={Microscope}
              disabled={!ready}
              loading={screening.loading}
              onClick={() => screening.run(files)}
            >
              Screen particle
            </Button>
          </div>
        </div>
      </Card>

      {screening.error && <ErrorState error={screening.error} />}
      {screening.data && <ScreeningResult result={screening.data} />}

      {!screening.data && !screening.error && !screening.loading && (
        <Card>
          <EmptyState icon={Beaker} title="No particle screened yet">
            Upload the R, A and P images for one particle to run the screening model.
          </EmptyState>
        </Card>
      )}

      <Disclosure
        title="Model performance and limitations"
        subtitle="Microplastic Screening (ResNet18 on HMPD)"
        icon={ScanSearch}
      >
        <ModelMetrics metrics={metrics.data} loading={metrics.loading} error={metrics.error} />
      </Disclosure>
    </section>
  );
}

function ScreeningResult({ result }) {
  const detected = result.microplastic_detected;

  return (
    <Card className="relative overflow-hidden">
      <div
        className={`absolute inset-x-0 top-0 h-0.5 ${detected ? 'bg-conditional' : 'bg-suitable'}`}
        aria-hidden="true"
      />
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1">
            Screening result
          </p>
          <h3
            className={`font-display text-lg font-semibold ${
              detected ? 'text-conditional-light' : 'text-suitable-light'
            }`}
          >
            {detected ? 'Possible microplastic' : 'No microplastic signature'}
          </h3>
        </div>
        <Badge tone={detected ? 'yellow' : 'green'}>
          {percent(result.confidence, 1)} confident
        </Badge>
      </div>

      <div className="space-y-2.5 mb-4">
        {Object.entries(result.class_probabilities).map(([label, value]) => (
          <Meter
            key={label}
            value={value}
            tone={label === 'microplastic_candidate' ? 'yellow' : 'green'}
            label={label === 'microplastic_candidate' ? 'Microplastic candidate' : 'No microplastic'}
          />
        ))}
      </div>

      {result.warnings?.length > 0 && (
        <div className="mb-4 space-y-2">
          {result.warnings.map((warning, i) => (
            <Disclaimer key={i} tone="alert">
              {warning}
            </Disclaimer>
          ))}
        </div>
      )}

      {detected && result.detections?.[0] && (
        <p className="text-xs text-mist-muted leading-relaxed mb-4">
          {result.detections[0].note}
        </p>
      )}

      <Disclosure title="Technical detail" subtitle="Model, input and raw output">
        <div className="space-y-3">
          <div className="grid sm:grid-cols-2 gap-x-5">
            <KeyValue label="Model" value={result.model} mono={false} />
            <KeyValue label="Architecture" value={result.architecture} />
            <KeyValue label="Task" value={result.task} mono={false} />
            <KeyValue label="Detections" value={result.count} />
            <KeyValue label="Input mode" value={result.input?.mode} />
            <KeyValue label="Model input size" value={`${result.input?.model_input_size} px`} />
          </div>
          {result.input?.received_sizes && (
            <div>
              <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-1.5">
                Channels received
              </p>
              <div className="grid grid-cols-3 gap-x-4">
                {Object.entries(result.input.received_sizes).map(([channel, size]) => (
                  <KeyValue key={channel} label={channel} value={size.join(' × ')} />
                ))}
              </div>
            </div>
          )}
        </div>
      </Disclosure>

      <p className="text-[10px] text-mist-faint mt-4 leading-relaxed border-t border-white/5 pt-3">
        {result.disclaimer}
      </p>
    </Card>
  );
}
