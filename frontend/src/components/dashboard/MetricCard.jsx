export default function MetricCard({ label, value, unit, sublabel, tone = 'default' }) {
  const toneColor = {
    default: 'text-mist',
    water: 'text-water',
    earth: 'text-earth-light',
    alert: 'text-alert-light',
  }[tone];

  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-5">
      <p className="text-[11px] font-mono tracking-wide text-mist-muted uppercase mb-2">{label}</p>
      <p className={`font-display text-2xl font-semibold ${toneColor}`}>
        {value}
        {unit && <span className="text-sm text-mist-muted font-body ml-1">{unit}</span>}
      </p>
      {sublabel && <p className="text-xs text-mist-muted mt-1.5">{sublabel}</p>}
    </div>
  );
}
