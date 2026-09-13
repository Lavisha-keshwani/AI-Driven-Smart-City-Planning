// Leaflet's stylesheet is imported in index.css, ahead of our overrides, so
// the cascade order is guaranteed.
import { useEffect, useMemo, useRef } from 'react';
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet';

import { LAYERS, featureColor } from '../../lib/domain';

/**
 * Interactive 1 km grid map.
 *
 * Renders real GeoJSON returned by the backend: one polygon per analysed grid
 * cell, filled by the active layer's class. Clicking a cell selects it.
 *
 * This is a live map, not an image. Panning, zooming and cell selection all work
 * against the actual model output.
 */

/** Re-fit the viewport when the rendered cells change. */
function FitBounds({ geojson }) {
  const map = useMap();
  const lastKey = useRef(null);

  useEffect(() => {
    if (!geojson?.features?.length) return;

    // Only refit when the cell set actually changes, so toggling a layer or
    // selecting a cell does not yank the viewport away from the user.
    const key = `${geojson.features.length}:${geojson.features[0]?.id}`;
    if (key === lastKey.current) return;
    lastKey.current = key;

    let minLat = 90;
    let maxLat = -90;
    let minLon = 180;
    let maxLon = -180;
    for (const feature of geojson.features) {
      for (const [lon, lat] of feature.geometry.coordinates[0]) {
        if (lat < minLat) minLat = lat;
        if (lat > maxLat) maxLat = lat;
        if (lon < minLon) minLon = lon;
        if (lon > maxLon) maxLon = lon;
      }
    }
    map.fitBounds(
      [
        [minLat, minLon],
        [maxLat, maxLon],
      ],
      { padding: [24, 24] },
    );
  }, [geojson, map]);

  return null;
}

export default function GridMap({
  geojson,
  activeLayer,
  selectedGridId,
  onSelectCell,
  className = '',
}) {
  const layer = LAYERS[activeLayer];

  // Leaflet mutates DOM outside React, so the GeoJSON layer is keyed on the data
  // identity and the active layer: changing either replaces the layer wholesale
  // rather than trying to patch styles in place.
  const dataKey = useMemo(
    () => `${activeLayer}:${geojson?.features?.length ?? 0}:${geojson?.features?.[0]?.id ?? ''}`,
    [activeLayer, geojson],
  );

  const style = (feature) => {
    const selected = feature.id === selectedGridId;
    return {
      color: selected ? '#EAF4F2' : '#0D1B1E',
      weight: selected ? 2 : 0.4,
      opacity: selected ? 1 : 0.5,
      fillColor: featureColor(activeLayer, feature.properties),
      fillOpacity: selected ? 0.9 : 0.62,
    };
  };

  const onEachFeature = (feature, leafletLayer) => {
    const props = feature.properties || {};
    const className = props[layer.classKey];
    const meta = layer.classes[className];
    const value = layer.formatValue(props[layer.valueKey]);

    // Colour is never the only signal: the tooltip names the class in text too.
    leafletLayer.bindTooltip(
      `<div class="gm-tip">
         <strong>${meta?.label ?? 'Unknown'}</strong>
         <span>${layer.valueLabel}: ${value}</span>
         <span class="gm-tip-id">${feature.id ?? ''}</span>
       </div>`,
      { sticky: true, direction: 'top', className: 'gm-tooltip' },
    );

    leafletLayer.on({
      click: () => onSelectCell?.(feature.id, props),
      mouseover: (event) => event.target.setStyle({ weight: 1.5, opacity: 1 }),
      mouseout: (event) => event.target.setStyle(style(feature)),
    });
  };

  // `isolate` creates a stacking context around the map. Leaflet puts its panes at
  // z-index 400 and its controls at 1000; without this those values compete with
  // the rest of the page and paint over things like the open city dropdown.
  return (
    <div
      className={`relative isolate z-0 rounded-2xl overflow-hidden border border-white/5 ${className}`}
    >
      <MapContainer
        center={[20.5937, 78.9629]}
        zoom={5}
        scrollWheelZoom
        className="h-full w-full bg-ink"
        attributionControl
      >
        {/* Standard OpenStreetMap tiles: no API key, so the map works out of the
            box. They ship light-themed, so a CSS filter (see index.css) darkens
            them to match the palette. For production traffic, host your own tiles
            or use a keyed provider — the OSM tile service is for low volume. */}
        <TileLayer
          url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          maxZoom={19}
        />
        {geojson?.features?.length > 0 && (
          <>
            <GeoJSON key={dataKey} data={geojson} style={style} onEachFeature={onEachFeature} />
            <FitBounds geojson={geojson} />
          </>
        )}
      </MapContainer>
    </div>
  );
}
