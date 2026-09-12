import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-ink-lighter border border-white/10 rounded-lg px-3 py-2 text-xs font-mono">
      <p className="text-mist-muted mb-1">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} style={{ color: p.color }}>
          {p.name}: {p.value} MLD
        </p>
      ))}
    </div>
  );
}

export default function WaterDemandPanel({ data }) {
  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-display font-semibold text-mist">Water Demand Forecast</h3>
          <p className="text-xs text-mist-muted mt-0.5">Residential + industrial, million litres/day</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <AreaChart data={data} margin={{ left: -20, right: 10, top: 5 }}>
          <defs>
            <linearGradient id="residentialFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#4CC9C0" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#4CC9C0" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="industrialFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#C08B3F" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#C08B3F" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="#1B383C" vertical={false} />
          <XAxis dataKey="year" stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip content={<CustomTooltip />} />
          <Area type="monotone" dataKey="residential" name="Residential" stroke="#4CC9C0" fill="url(#residentialFill)" strokeWidth={2} stackId="1" />
          <Area type="monotone" dataKey="industrial" name="Industrial" stroke="#C08B3F" fill="url(#industrialFill)" strokeWidth={2} stackId="1" />
        </AreaChart>
      </ResponsiveContainer>
      <div className="flex gap-5 mt-2">
        <span className="flex items-center gap-1.5 text-xs text-mist-muted"><span className="w-2 h-2 rounded-full bg-water" />Residential</span>
        <span className="flex items-center gap-1.5 text-xs text-mist-muted"><span className="w-2 h-2 rounded-full bg-earth" />Industrial</span>
      </div>
    </div>
  );
}
