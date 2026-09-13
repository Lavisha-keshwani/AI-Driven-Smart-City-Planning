import { AlertTriangle, Info, Loader2, ServerCrash } from 'lucide-react';
import { useId, useState } from 'react';

// ── Layout ─────────────────────────────────────────────────────────────────

export function Card({ children, className = '', padded = true }) {
  return (
    <div
      className={`bg-ink-light border border-white/5 rounded-2xl ${padded ? 'p-5' : ''} ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ children, hint, action }) {
  return (
    <div className="flex items-end justify-between gap-4 mb-3">
      <div>
        <h2 className="font-display text-base font-semibold text-mist">{children}</h2>
        {hint && <p className="text-xs text-mist-muted mt-0.5">{hint}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-mist">{title}</h1>
        {subtitle && <p className="text-sm text-mist-muted mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      <div className="flex items-center gap-2">{children}</div>
    </header>
  );
}

// ── Status ─────────────────────────────────────────────────────────────────

const BADGE_TONES = {
  green: 'bg-suitable/15 text-suitable border-suitable/30',
  yellow: 'bg-conditional/15 text-conditional border-conditional/30',
  red: 'bg-avoid/15 text-avoid border-avoid/30',
  water: 'bg-water/15 text-water border-water/30',
  earth: 'bg-earth/15 text-earth-light border-earth/30',
  neutral: 'bg-white/5 text-mist-muted border-white/10',
};

export function Badge({ tone = 'neutral', children, className = '' }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-mono uppercase tracking-wide ${BADGE_TONES[tone] || BADGE_TONES.neutral} ${className}`}
    >
      {children}
    </span>
  );
}

export function Spinner({ label = 'Loading', className = '' }) {
  return (
    <div className={`flex items-center gap-2.5 text-mist-muted text-sm ${className}`}>
      <Loader2 size={16} className="animate-spin text-water" />
      <span>{label}</span>
    </div>
  );
}

export function Loading({ label = 'Loading', className = '' }) {
  return (
    <div className={`flex items-center justify-center py-12 ${className}`}>
      <Spinner label={label} />
    </div>
  );
}

/**
 * Renders a backend failure honestly: the error code, the message the backend
 * gave, and any remedy it suggested. Never replaced with placeholder content.
 */
export function ErrorState({ error, onRetry, className = '' }) {
  if (!error) return null;
  const unavailable = error.isUnavailable;
  const remedy = error.detail?.remedy;
  const missing = error.detail?.expected_file;

  return (
    <div
      className={`rounded-2xl border border-alert/25 bg-alert/[0.06] p-5 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <ServerCrash size={18} className="text-alert-light shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <p className="font-display text-sm font-semibold text-alert-light">
            {unavailable ? 'This model is unavailable' : 'Something went wrong'}
          </p>
          <p className="text-sm text-mist mt-1">{error.message}</p>

          {(missing || remedy) && (
            <div className="mt-3 text-xs text-mist-muted font-mono space-y-1">
              {missing && <p>missing: {missing}</p>}
              {remedy && <p>{remedy}</p>}
            </div>
          )}

          <div className="flex items-center gap-3 mt-3">
            {error.code && (
              <span className="text-[11px] font-mono text-mist-faint">{error.code}</span>
            )}
            {onRetry && (
              <button
                onClick={onRetry}
                className="text-xs text-water hover:text-water-bright underline underline-offset-2"
              >
                Try again
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon = Info, title, children, className = '' }) {
  return (
    <div className={`text-center py-12 px-6 ${className}`}>
      <Icon size={22} className="text-mist-faint mx-auto mb-3" strokeWidth={1.5} />
      <p className="font-display text-sm text-mist-muted">{title}</p>
      {children && <p className="text-xs text-mist-faint mt-1.5 max-w-sm mx-auto">{children}</p>}
    </div>
  );
}

/** A scope or safety caveat. Always visible — never behind a disclosure. */
export function Disclaimer({ children, tone = 'earth' }) {
  const colors =
    tone === 'alert'
      ? 'border-alert/25 bg-alert/[0.06] text-alert-light'
      : 'border-earth/25 bg-earth/[0.06] text-earth-light';
  return (
    <div className={`rounded-xl border ${colors} px-4 py-3 flex items-start gap-2.5`}>
      <AlertTriangle size={15} className="shrink-0 mt-0.5" />
      <p className="text-xs leading-relaxed">{children}</p>
    </div>
  );
}

// ── Disclosure ─────────────────────────────────────────────────────────────

/**
 * Collapsible section. Used for the technical-details panels, which evaluators
 * need and citizens should not have pushed at them.
 */
export function Disclosure({ title, subtitle, defaultOpen = false, children, icon: Icon }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();

  return (
    <div className="border border-white/5 rounded-xl overflow-hidden bg-ink-light/60">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left hover:bg-white/[0.03] transition-colors"
      >
        <span className="flex items-center gap-2.5 min-w-0">
          {Icon && <Icon size={15} className="text-mist-muted shrink-0" />}
          <span className="min-w-0">
            <span className="block text-sm font-medium text-mist truncate">{title}</span>
            {subtitle && (
              <span className="block text-[11px] text-mist-faint truncate">{subtitle}</span>
            )}
          </span>
        </span>
        <span className={`text-mist-muted transition-transform ${open ? 'rotate-90' : ''}`}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
      </button>
      {open && (
        <div id={id} className="px-4 pb-4 pt-1 border-t border-white/5">
          {children}
        </div>
      )}
    </div>
  );
}

// ── Data display ───────────────────────────────────────────────────────────

export function KeyValue({ label, value, mono = true, className = '' }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1 ${className}`}>
      <span className="text-xs text-mist-muted shrink-0">{label}</span>
      <span
        className={`text-xs text-mist text-right ${mono ? 'font-mono' : ''} break-words min-w-0`}
      >
        {value ?? <span className="text-mist-faint">not available</span>}
      </span>
    </div>
  );
}

/** A labelled 0–1 bar. `tone` picks the fill colour. */
export function Meter({ value, tone = 'water', label, showPercent = true }) {
  const pct = Math.max(0, Math.min(1, Number(value) || 0)) * 100;
  const fill = {
    water: 'bg-water',
    green: 'bg-suitable',
    yellow: 'bg-conditional',
    red: 'bg-avoid',
    earth: 'bg-earth',
  }[tone];

  return (
    <div>
      {(label || showPercent) && (
        <div className="flex items-baseline justify-between mb-1.5">
          {label && <span className="text-xs text-mist-muted">{label}</span>}
          {showPercent && (
            <span className="text-xs font-mono text-mist">{pct.toFixed(0)}%</span>
          )}
        </div>
      )}
      <div className="h-1.5 rounded-full bg-white/[0.07] overflow-hidden">
        <div
          className={`h-full rounded-full ${fill} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

// ── Form controls ──────────────────────────────────────────────────────────

export function Field({ label, hint, error, children, htmlFor }) {
  return (
    <div>
      <label htmlFor={htmlFor} className="block text-xs font-medium text-mist-muted mb-1.5">
        {label}
      </label>
      {children}
      {error ? (
        <p className="text-[11px] text-alert-light mt-1">{error}</p>
      ) : (
        hint && <p className="text-[11px] text-mist-faint mt-1">{hint}</p>
      )}
    </div>
  );
}

const CONTROL = `w-full bg-ink border border-white/10 rounded-lg px-3 py-2 text-sm text-mist
  placeholder:text-mist-faint focus:border-water/40 focus:outline-none focus:ring-1
  focus:ring-water/30 transition-colors`;

export function Input(props) {
  return <input {...props} className={`${CONTROL} ${props.className || ''}`} />;
}

export function Select({ children, ...props }) {
  return (
    <select {...props} className={`${CONTROL} ${props.className || ''}`}>
      {children}
    </select>
  );
}

export function Button({
  children,
  variant = 'primary',
  loading = false,
  icon: Icon,
  className = '',
  ...props
}) {
  const styles = {
    primary: 'bg-water text-ink hover:bg-water-bright disabled:bg-water/40',
    secondary:
      'bg-white/[0.06] text-mist hover:bg-white/10 border border-white/10 disabled:opacity-50',
    ghost: 'text-mist-muted hover:text-mist hover:bg-white/[0.04] disabled:opacity-50',
  }[variant];

  return (
    <button
      {...props}
      disabled={props.disabled || loading}
      className={`inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm
        font-medium transition-colors disabled:cursor-not-allowed ${styles} ${className}`}
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : Icon && <Icon size={15} />}
      {children}
    </button>
  );
}

export function Toggle({ checked, onChange, label, tone = 'water', count }) {
  const dot = {
    water: 'bg-water',
    green: 'bg-suitable',
    red: 'bg-avoid',
    earth: 'bg-earth',
  }[tone];

  return (
    <button
      onClick={() => onChange(!checked)}
      role="switch"
      aria-checked={checked}
      className={`w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-left text-sm
        transition-colors ${checked ? 'bg-white/[0.07] text-mist' : 'text-mist-muted hover:bg-white/[0.03]'}`}
    >
      <span
        className={`w-2 h-2 rounded-full shrink-0 ${checked ? dot : 'bg-white/20'}`}
        aria-hidden="true"
      />
      <span className="flex-1 min-w-0 truncate">{label}</span>
      {count != null && <span className="text-[11px] font-mono text-mist-faint">{count}</span>}
    </button>
  );
}
