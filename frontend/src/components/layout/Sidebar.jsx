import { LayoutGrid, Sliders, GitCompare, Satellite } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: LayoutGrid },
  { to: '/whatif', label: 'What-if Analysis', icon: Sliders },
  { to: '/compare', label: 'Compare Cities', icon: GitCompare },
];

export default function Sidebar() {
  return (
    <aside className="w-64 shrink-0 bg-ink-light border-r border-white/5 flex flex-col h-screen sticky top-0">
      <div className="px-6 py-7 border-b border-white/5">
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

      <nav className="flex-1 px-3 py-6 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-water/10 text-water font-medium'
                  : 'text-mist-muted hover:text-mist hover:bg-white/[0.03]'
              }`
            }
          >
            <Icon size={17} strokeWidth={1.75} />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Signature element: topographic contour lines, referencing the GIS/
          elevation data this whole system is built on */}
      <div className="relative h-32 overflow-hidden opacity-70">
        <svg viewBox="0 0 256 128" className="absolute inset-0 w-full h-full" preserveAspectRatio="none">
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

      <div className="px-6 py-4 border-t border-white/5">
        <p className="text-[11px] text-mist-faint font-mono">
          v0.1 · data through 2025
        </p>
      </div>
    </aside>
  );
}
