function scoreColor(score) {
  if (score >= 65) return { fill: '#4CC9C0', label: 'Stable' };
  if (score >= 45) return { fill: '#C08B3F', label: 'Strained' };
  return { fill: '#E2583E', label: 'Critical' };
}

export default function SustainabilityScore({ score }) {
  const { fill, label } = scoreColor(score);
  const fillHeight = 148 * (score / 100);
  const waveY = 148 - fillHeight;

  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6 flex items-center gap-6">
      <div className="relative w-24 h-[148px] shrink-0">
        <svg viewBox="0 0 96 148" className="w-full h-full">
          <defs>
            <clipPath id="tankClip">
              <rect x="4" y="4" width="88" height="140" rx="14" />
            </clipPath>
            <linearGradient id="waterFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fill} stopOpacity="0.9" />
              <stop offset="100%" stopColor={fill} stopOpacity="0.55" />
            </linearGradient>
          </defs>

          {/* tank outline */}
          <rect x="4" y="4" width="88" height="140" rx="14" fill="none" stroke="#4A6260" strokeWidth="2" />

          {/* fill, clipped to tank shape */}
          <g clipPath="url(#tankClip)">
            <rect x="4" y={waveY} width="88" height={fillHeight + 20} fill="url(#waterFill)" />
            <path
              d={`M4 ${waveY} Q 26 ${waveY - 6} 48 ${waveY} T 92 ${waveY}`}
              fill="none"
              stroke={fill}
              strokeWidth="2"
              opacity="0.8"
            />
          </g>

          {/* gradient marks */}
          {[0.25, 0.5, 0.75].map((frac) => (
            <line
              key={frac}
              x1="4"
              x2="10"
              y1={4 + 140 * frac}
              y2={4 + 140 * frac}
              stroke="#4A6260"
              strokeWidth="1.5"
            />
          ))}
        </svg>
      </div>

      <div>
        <p className="text-[11px] font-mono tracking-wide text-mist-muted uppercase mb-1">Sustainability Score</p>
        <p className="font-display text-4xl font-semibold text-mist">
          {score}<span className="text-lg text-mist-muted font-body">/100</span>
        </p>
        <span
          className="inline-block mt-2 text-xs font-medium px-2.5 py-1 rounded-full"
          style={{ color: fill, backgroundColor: `${fill}1F` }}
        >
          {label}
        </span>
        <p className="text-xs text-mist-muted mt-3 max-w-[180px] leading-relaxed">
          Composite of water security, groundwater trend, and land-use balance.
        </p>
      </div>
    </div>
  );
}
