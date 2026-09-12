import { Droplets, Building2, Leaf, Factory, Users, GitMerge, AlertTriangle } from 'lucide-react';

const AGENT_ICON = {
  'Water Authority': Droplets,
  'Urban Planner': Building2,
  'Environment': Leaf,
  'Industry': Factory,
  'Citizen Welfare': Users,
  'Coordinator': GitMerge,
};

const TONE_STYLE = {
  positive: 'border-l-water text-mist',
  neutral: 'border-l-mist-faint text-mist',
  caution: 'border-l-earth text-mist',
  alert: 'border-l-alert text-mist',
  decision: 'border-l-water bg-water/[0.04]',
};

export default function RecommendationFeed({ recommendations }) {
  return (
    <div className="bg-ink-light border border-white/5 rounded-2xl p-6">
      <h3 className="font-display font-semibold text-mist mb-1">AI Recommendations</h3>
      <p className="text-xs text-mist-muted mb-5">Agent-by-agent reasoning, coordinated into one decision</p>

      <div className="space-y-3">
        {recommendations.map((rec, i) => {
          const Icon = AGENT_ICON[rec.agent] || AlertTriangle;
          const isDecision = rec.tone === 'decision';
          return (
            <div
              key={i}
              className={`border-l-2 rounded-r-lg pl-4 pr-4 py-3 ${TONE_STYLE[rec.tone]} ${isDecision ? '' : 'bg-white/[0.02]'}`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Icon size={14} className={isDecision ? 'text-water' : 'text-mist-muted'} strokeWidth={2} />
                <span className={`text-xs font-mono uppercase tracking-wide ${isDecision ? 'text-water' : 'text-mist-muted'}`}>
                  {rec.agent}{isDecision ? ' · Final' : ''}
                </span>
              </div>
              <p className="text-sm leading-relaxed text-mist/90">{rec.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
