import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-ink-lighter border border-white/10 rounded-lg px-3 py-2 text-xs font-mono">
      <p className="text-mist-muted mb-1">{label}</p>
      <p className="text-water">{payload[0].value} km²</p>
    </div>
  );
}

function riskTone(risk) {
  if (risk === 'Severe') return 'text-alert-light bg-alert/15';
  if (risk === 'High') return 'text-alert-light bg-alert/10';
  if (risk === 'Moderate') return 'text-earth-light bg-earth/15';
  return 'text-water bg-water/15';
}

export default function LakeMonitoringPanel({ data, floodRisk, droughtRisk }) {
  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="font-display font-semibold text-mist">Lake & Wetland Monitoring</h3>
          <p className="text-xs text-mist-muted mt-0.5">Surface water extent, sq. km</p>
        </div>
        <div className="flex gap-2">
          <span className={`text-[11px] font-mono px-2.5 py-1 rounded-full ${riskTone(floodRisk)}`}>Flood: {floodRisk}</span>
          <span className={`text-[11px] font-mono px-2.5 py-1 rounded-full ${riskTone(droughtRisk)}`}>Drought: {droughtRisk}</span>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ left: -20, right: 10, top: 5 }}>
          <CartesianGrid stroke="#1B383C" vertical={false} />
          <XAxis dataKey="year" stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="#4A6260" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(76,201,192,0.05)' }} />
          <Bar dataKey="sqkm" radius={[4, 4, 0, 0]}>
            {data.map((entry, i) => (
              <Cell key={i} fill={i === data.length - 1 ? '#7EE8DC' : '#4CC9C0'} fillOpacity={i === data.length - 1 ? 1 : 0.55} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
