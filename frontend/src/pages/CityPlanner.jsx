import { MapPin, MousePointerClick, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useMemo, useState } from 'react';

import CoordinatorPanel, { AgentNarrative } from '../components/ai/CoordinatorPanel';
import { FloodCard, UrbanCard, WaterCard } from '../components/cell/CellSummary';
import GridMap from '../components/map/GridMap';
import { LayerPicker, MapLegend } from '../components/map/MapControls';
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  Loading,
  PageHeader,
  SectionTitle,
  Spinner,
} from '../components/ui';
import CitySelector from '../components/city/CitySelector';
import { getCities, getCityLayer, getMetrics, runCoordinator } from '../api/client';
import { useAction, useAsync } from '../hooks/useAsync';

// The whole city grid is rendered. An earlier version capped this at 1,200 cells,
// which silently showed only PART OF EACH CITY: the source file is ordered
// south to north, so taking the first N rows cut the grid along a latitude line
// and left a half-disc sitting below the city centre. Every one of the 45 cities
// was affected. A cap is only safe if it samples evenly, and at ~2,400 cells per
// city (2,956 at most) there is no need for one.

export default function CityPlanner() {
  const [city, setCity] = useState(null);
  const [activeLayer, setActiveLayer] = useState('urban');
  const [selectedGridId, setSelectedGridId] = useState(null);

  // ── Cities ──────────────────────────────────────────────────────────────
  const cities = useAsync(useCallback((signal) => getCities({ signal }), []), []);

  useEffect(() => {
    if (!city && cities.data?.cities?.length) setCity(cities.data.cities[0]);
  }, [cities.data, city]);

  // ── All three layers, fetched together so switching is instant ──────────
  const cityName = city?.city;
  const layers = useAsync(
    useCallback(
      async (signal) => {
        const [urban, flood, water] = await Promise.all([
          getCityLayer('urban', cityName, { signal }),
          getCityLayer('flood', cityName, { signal }),
          getCityLayer('water', cityName, { signal }),
        ]);
        return { urban, flood, water };
      },
      [cityName],
    ),
    [cityName],
    { enabled: Boolean(cityName) },
  );

  // Clear the selection when the city changes — a cell id belongs to one city.
  useEffect(() => {
    setSelectedGridId(null);
  }, [cityName]);

  const geojson = layers.data?.[activeLayer];
  const counts = useMemo(
    () =>
      layers.data
        ? {
            urban: layers.data.urban?.features?.length,
            flood: layers.data.flood?.features?.length,
            water: layers.data.water?.features?.length,
          }
        : undefined,
    [layers.data],
  );

  // ── The multi-agent pipeline for the selected cell ──────────────────────
  const pipeline = useAction(
    useCallback((gridId) => runCoordinator({ grid_id: gridId, include_attribution: true }), []),
  );

  const handleSelectCell = useCallback(
    (gridId) => {
      setSelectedGridId(gridId);
      pipeline.run(gridId);
    },
    [pipeline],
  );

  // ── Validation metrics, loaded once, for the technical panels ───────────
  const urbanMetrics = useAsync(useCallback((signal) => getMetrics('urban', { signal }), []), []);
  const floodMetrics = useAsync(useCallback((signal) => getMetrics('flood', { signal }), []), []);
  const waterMetrics = useAsync(useCallback((signal) => getMetrics('water', { signal }), []), []);

  const domains = pipeline.data?.domains;

  return (
    <main className="flex-1 min-w-0 px-6 lg:px-8 py-7 overflow-y-auto scrollbar-thin">
      <PageHeader
        title="City Planner"
        subtitle="Where a city can grow, where flooding is likely, and where the water is — on a one-square-kilometre grid, reconciled into a single recommendation."
      >
        {cities.data?.cities && city && (
          <CitySelector
            cities={cities.data.cities.map((c) => ({ ...c, id: c.city, name: c.city }))}
            selectedCity={{ ...city, id: city.city, name: city.city }}
            onSelect={setCity}
          />
        )}
      </PageHeader>

      {cities.loading && <Loading label="Loading cities…" />}
      {cities.error && <ErrorState error={cities.error} onRetry={cities.refresh} />}

      {city && (
        <div className="grid xl:grid-cols-[17rem_1fr] gap-5">
          {/* ── Controls ─────────────────────────────────────────────────
              Ordered after the map below xl: on a narrow screen the map is what
              the user came for, and three control panels above it would push it
              off the first screenful. */}
          <aside className="order-2 xl:order-1 space-y-4 xl:sticky xl:top-7 xl:self-start">
            <Card>
              <LayerPicker active={activeLayer} onChange={setActiveLayer} counts={counts} />
            </Card>
            <Card>
              <MapLegend activeLayer={activeLayer} geojson={geojson} />
            </Card>
            <Card>
              <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-2">
                {city.city}
              </p>
              <dl className="space-y-1.5 text-xs">
                <div className="flex justify-between gap-2">
                  <dt className="text-mist-muted">State</dt>
                  <dd className="text-mist">{city.state}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-mist-muted">Analysed squares</dt>
                  <dd className="text-mist font-mono">{city.grid_cells?.toLocaleString()}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-mist-muted">Shown on map</dt>
                  <dd className="text-mist font-mono">
                    {geojson?.features?.length?.toLocaleString() ?? '—'}
                  </dd>
                </div>
              </dl>
              <p className="text-[10px] text-mist-faint mt-2.5 leading-relaxed">
                Each city is analysed as a 25 km radius around its centre, which is why
                the grid is circular.
              </p>
            </Card>
          </aside>

          {/* ── Map and results ──────────────────────────────────────── */}
          <div className="order-1 xl:order-2 min-w-0 space-y-5">
            {layers.error ? (
              <ErrorState error={layers.error} onRetry={layers.refresh} />
            ) : (
              <div className="relative">
                <GridMap
                  geojson={geojson}
                  activeLayer={activeLayer}
                  selectedGridId={selectedGridId}
                  onSelectCell={handleSelectCell}
                  className="h-[26rem] lg:h-[34rem]"
                />
                {layers.loading && (
                  <div className="absolute inset-0 bg-ink/70 backdrop-blur-sm flex items-center justify-center rounded-2xl">
                    <Spinner label={`Loading ${city.city}…`} />
                  </div>
                )}
                {!layers.loading && !selectedGridId && geojson?.features?.length > 0 && (
                  <div className="absolute bottom-4 left-1/2 -translate-x-1/2 pointer-events-none">
                    <p className="flex items-center gap-2 px-3.5 py-2 rounded-full bg-ink/90 border border-white/10 text-xs text-mist-muted backdrop-blur-sm">
                      <MousePointerClick size={13} className="text-water" />
                      Click a square to assess it
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* ── Selected cell ──────────────────────────────────────── */}
            {!selectedGridId ? (
              <Card>
                <EmptyState icon={MapPin} title="No square selected">
                  Pick a square on the map. All three models run for it, then five AI agents
                  interpret the results and reconcile them into one recommendation.
                </EmptyState>
              </Card>
            ) : (
              <>
                <SectionTitle
                  hint={`Grid square ${selectedGridId}`}
                  action={
                    <Button
                      variant="ghost"
                      icon={RefreshCw}
                      onClick={() => pipeline.run(selectedGridId)}
                      loading={pipeline.loading}
                    >
                      Re-run
                    </Button>
                  }
                >
                  Assessment
                </SectionTitle>

                <CoordinatorPanel
                  result={pipeline.data}
                  loading={pipeline.loading}
                  error={pipeline.error}
                  onRetry={() => pipeline.run(selectedGridId)}
                />

                {domains && (
                  <>
                    <SectionTitle hint="Each model's finding, with the evidence behind it">
                      What each model found
                    </SectionTitle>
                    <div className="grid lg:grid-cols-2 gap-4 items-start">
                      <FloodCard
                        prediction={domains.flood?.model_output}
                        metrics={floodMetrics.data}
                        metricsLoading={floodMetrics.loading}
                        metricsError={floodMetrics.error}
                      />
                      <UrbanCard
                        prediction={domains.urban?.model_output}
                        metrics={urbanMetrics.data}
                        metricsLoading={urbanMetrics.loading}
                        metricsError={urbanMetrics.error}
                      />
                      <WaterCard
                        prediction={domains.water?.model_output}
                        metrics={waterMetrics.data}
                        metricsLoading={waterMetrics.loading}
                        metricsError={waterMetrics.error}
                      />
                    </div>

                    <SectionTitle hint="How each agent read its model's output">
                      Agent reasoning
                    </SectionTitle>
                    <div className="space-y-2">
                      {['water', 'urban', 'flood'].map((domain) => (
                        <AgentNarrative
                          key={domain}
                          domain={domain}
                          analysis={domains[domain]?.analysis}
                        />
                      ))}
                    </div>

                    {pipeline.data?.trace?.length > 0 && (
                      <Card>
                        <p className="text-[11px] font-mono uppercase tracking-wide text-mist-muted mb-2">
                          Pipeline trace
                        </p>
                        <ol className="space-y-1">
                          {pipeline.data.trace.map((step, i) => (
                            <li
                              key={i}
                              className="text-[11px] font-mono text-mist-faint flex gap-2.5"
                            >
                              <span className="text-water/60">{String(i + 1).padStart(2, '0')}</span>
                              <span>{step}</span>
                            </li>
                          ))}
                        </ol>
                      </Card>
                    )}
                  </>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
