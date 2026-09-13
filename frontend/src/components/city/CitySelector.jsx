import { ChevronDown, MapPin, Search } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

/**
 * City picker.
 *
 * Two things about the styling are deliberate:
 *
 * `z-30` on the root makes this a stacking context above the map. Leaflet puts
 * its panes at z-index 400 and its controls at 1000, so without this the open
 * menu is painted underneath the map — it only appeared above the header and
 * below the map's lower edge.
 *
 * The list is height-capped and scrollable because there are 45 cities; left
 * uncapped the menu ran ~1800px and off the bottom of the viewport. A filter is
 * provided for the same reason.
 */
export default function CitySelector({ cities, selectedCity, onSelect }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const rootRef = useRef(null);
  const searchRef = useRef(null);

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return undefined;

    const onPointerDown = (event) => {
      if (rootRef.current && !rootRef.current.contains(event.target)) setOpen(false);
    };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  // Focus the filter when the menu opens, and clear it when it closes.
  useEffect(() => {
    if (open) searchRef.current?.focus();
    else setQuery('');
  }, [open]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return cities;
    return cities.filter(
      (city) =>
        city.name.toLowerCase().includes(needle) ||
        String(city.state).toLowerCase().includes(needle),
    );
  }, [cities, query]);

  if (!selectedCity) return null;

  return (
    <div className="relative z-30" ref={rootRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        className="flex items-center gap-2.5 pl-3 pr-2.5 py-2 rounded-lg bg-ink-lighter
          border border-white/10 hover:border-water/30 transition-colors"
      >
        <MapPin size={15} className="text-water" strokeWidth={2} />
        <span className="font-display font-medium text-sm text-mist">{selectedCity.name}</span>
        <span className="text-xs text-mist-muted font-mono">{selectedCity.state}</span>
        <ChevronDown
          size={14}
          className={`text-mist-muted transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          className="absolute right-0 mt-2 w-64 bg-ink-lighter border border-white/10
            rounded-lg shadow-xl shadow-black/40 overflow-hidden z-50"
        >
          <div className="p-2 border-b border-white/5">
            <div className="relative">
              <Search
                size={13}
                className="absolute left-2.5 top-1/2 -translate-y-1/2 text-mist-faint"
              />
              <input
                ref={searchRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={`Search ${cities.length} cities…`}
                aria-label="Filter cities"
                className="w-full bg-ink border border-white/10 rounded-md pl-7 pr-2 py-1.5
                  text-xs text-mist placeholder:text-mist-faint focus:border-water/40
                  focus:outline-none focus:ring-1 focus:ring-water/30"
              />
            </div>
          </div>

          <ul className="max-h-72 overflow-y-auto scrollbar-thin" role="listbox">
            {filtered.length === 0 ? (
              <li className="px-4 py-3 text-xs text-mist-faint text-center">
                No city matches “{query}”.
              </li>
            ) : (
              filtered.map((city) => {
                const isSelected = city.id === selectedCity.id;
                return (
                  <li key={city.id}>
                    <button
                      role="option"
                      aria-selected={isSelected}
                      onClick={() => {
                        onSelect(city);
                        setOpen(false);
                      }}
                      className={`w-full text-left px-4 py-2.5 text-sm flex items-center
                        justify-between gap-3 transition-colors ${
                          isSelected
                            ? 'bg-water/10 text-water'
                            : 'text-mist-muted hover:bg-white/[0.04] hover:text-mist'
                        }`}
                    >
                      <span className="font-medium truncate">{city.name}</span>
                      <span className="text-xs font-mono opacity-60 shrink-0">{city.state}</span>
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
