import { Building2, Droplets, Map, Satellite } from 'lucide-react';
import { NavLink } from 'react-router-dom';

import { getHealth } from '../../api/client';
import { useAsync } from '../../hooks/useAsync';
import { useCallback } from 'react';

const NAV_ITEMS = [
  { to: '/', label: 'City Planner', hint: 'Where to grow', icon: Map },
  { to: '/water', label: 'Water & Microplastics', hint: 'Water quality', icon: Droplets },
  { to: '/building', label: 'Building Planner', hint: 'Build sustainably', icon: Building2 },
];

/** Live backend readiness, so a degraded system is visible rather than puzzling. */
function BackendStatus() {
  const health = useAsync(useCallback((signal) => getHealth({ signal }), []), []);

  if (health.loading) {
    return <p className="text-[11px] text-mist-faint font-mono">checking backend…</p>;
  }
  if (health.error) {
    return (
      <div className="flex items-start gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-alert mt-1.5 shrink-0" />
        <p className="text-[11px] text-alert-light font-mono leading-relaxed">
          backend unreachable
        </p>
      </div>
    );
  }

  const { status, models_loaded: models, llm } = health.data;
  const healthy = status === 'healthy';

  return (
    <div className="space-y-1.5">
      <div className="flex items-center gap-2">
        <span
          className={`w-1.5 h-1.5 rounded-full shrink-0 ${healthy ? 'bg-suitable' : 'bg-conditional'}`}
        />
        <p className="text-[11px] text-mist-muted font-mono">
          {models} models loaded
        </p>
      </div>
      <p className="text-[10px] text-mist-faint font-mono truncate" title={llm?.model}>
        {llm?.api_key_configured ? llm.model : 'LLM key not configured'}
      </p>
    </div>
  );
}

export default function Sidebar() {
  return (
    <aside className="w-60 shrink-0 bg-ink-light border-r border-white/5 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-6 border-b border-white/5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-md bg-water/15 flex items-center justify-center">
            <Satellite size={16} className="text-water" strokeWidth={2} />
          </div>
          <span className="font-display font-semibold text-lg tracking-tight text-mist">
            SmartCity<span className="text-water">AI</span>
          </span>
        </div>
        <p className="text-[11px] text-mist-muted mt-2 font-mono tracking-wide">
          MULTI-AGENT DECISION SYSTEM
        </p>
      </div>

      <nav className="flex-1 px-2.5 py-5 space-y-1">
        {NAV_ITEMS.map(({ to, label, hint, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-start gap-3 px-3 py-2.5 rounded-lg transition-colors ${
                isActive
                  ? 'bg-water/10 text-water'
                  : 'text-mist-muted hover:text-mist hover:bg-white/[0.03]'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={17} strokeWidth={1.75} className="shrink-0 mt-0.5" />
                <span className="min-w-0">
                  <span className={`block text-sm ${isActive ? 'font-medium' : ''}`}>{label}</span>
                  <span className="block text-[11px] text-mist-faint truncate">{hint}</span>
                </span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* Topographic contours, referencing the elevation data underlying the models */}
      <div className="relative h-24 overflow-hidden opacity-60" aria-hidden="true">
        <svg
          viewBox="0 0 256 128"
          className="absolute inset-0 w-full h-full"
          preserveAspectRatio="none"
        >
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <path
              key={i}
              d={`M0 ${128 - i * 18} Q 64 ${100 - i * 18} 128 ${128 - i * 18} T 256 ${128 - i * 18}`}
              fill="none"
              stroke={i % 2 === 0 ? '#4CC9C0' : '#C08B3F'}
              strokeOpacity={0.12 + i * 0.02}
              strokeWidth="1"
            />
          ))}
        </svg>
      </div>

      <div className="px-5 py-4 border-t border-white/5">
        <BackendStatus />
      </div>
    </aside>
  );
}
