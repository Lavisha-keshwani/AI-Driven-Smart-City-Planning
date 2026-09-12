import { useState, useRef, useEffect } from 'react';
import { ChevronDown, MapPin } from 'lucide-react';

export default function CitySelector({ cities, selectedCity, onSelect }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  if (!selectedCity) return null;

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2.5 pl-3 pr-2.5 py-2 rounded-lg bg-ink-lighter border border-white/10 hover:border-water/30 transition-colors"
      >
        <MapPin size={15} className="text-water" strokeWidth={2} />
        <span className="font-display font-medium text-sm text-mist">{selectedCity.name}</span>
        <span className="text-xs text-mist-muted font-mono">{selectedCity.state}</span>
        <ChevronDown size={14} className={`text-mist-muted transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-ink-lighter border border-white/10 rounded-lg shadow-xl shadow-black/30 overflow-hidden z-20">
          {cities.map((city) => (
            <button
              key={city.id}
              onClick={() => {
                onSelect(city);
                setOpen(false);
              }}
              className={`w-full text-left px-4 py-2.5 text-sm flex items-center justify-between transition-colors ${
                city.id === selectedCity.id
                  ? 'bg-water/10 text-water'
                  : 'text-mist-muted hover:bg-white/[0.04] hover:text-mist'
              }`}
            >
              <span className="font-medium">{city.name}</span>
              <span className="text-xs font-mono opacity-60">{city.state}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
