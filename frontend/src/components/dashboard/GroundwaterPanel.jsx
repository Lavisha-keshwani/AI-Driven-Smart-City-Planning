import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-ink-lighter border border-white/10 rounded-lg px-3 py-2 text-xs font-mono">
      <p className="text-mist-muted mb-1">{label}</p>
      <p className="text-alert-light">{payload[0].value} cm anomaly</p>
    </div>
  );
}

export default function GroundwaterPanel({ data, riskZones }) {
  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-display font-semibold text-mist">Groundwater Prediction</h3>
          <p className="text-xs text-mist-muted mt-0.5">GRACE liquid water equivalent anomaly</p>
        </div>
        <div className="text-right">
          <p className="font-display text-lg font-semibold text-alert-light">{riskZones}</p>
          <p className="text-[10px] text-mist-muted font-mono uppercase">risk zones</p>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={data} margin={{ left: -20, right: 10, top: 5 }}>
          <CartesianGrid stroke="#1B383C" vertical={false} />
          <XAxis dataKey="year" stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <ReferenceLine y={0} stroke="#4A6260" strokeDasharray="3 3" />
          <Tooltip content={<CustomTooltip />} />
          <Line type="monotone" dataKey="level" stroke="#E2583E" strokeWidth={2.5} dot={{ r: 3, fill: '#E2583E' }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
