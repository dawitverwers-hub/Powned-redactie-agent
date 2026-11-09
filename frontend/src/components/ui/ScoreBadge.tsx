interface Props {
  score: number
  prioriteit?: string | null
  small?: boolean
}

const PRIO_CONFIG: Record<string, { color: string; bg: string; label: string }> = {
  'must-have':  { color: '#E2148B', bg: 'linear-gradient(135deg,#E2148B,#9C2D8F)', label: 'MUST' },
  'sterk':      { color: '#22C55E', bg: 'rgba(34,197,94,0.2)',   label: 'STERK' },
  'interessant':{ color: '#6366F1', bg: 'rgba(99,102,241,0.2)',  label: 'OK' },
  'zwak':       { color: '#F59E0B', bg: 'rgba(245,158,11,0.15)', label: 'ZWAK' },
  'afwijzen':   { color: '#606068', bg: 'rgba(96,96,104,0.15)',  label: '—' },
}

export default function ScoreBadge({ score, prioriteit, small }: Props) {
  if (!score) return null
  const cfg = prioriteit ? PRIO_CONFIG[prioriteit] : null

  return (
    <span
      className={`inline-flex items-center font-bold rounded ${small ? 'text-[8.5px] px-1 py-0.5' : 'text-[10px] px-1.5 py-0.5'} ${prioriteit === 'must-have' ? 'text-white' : ''}`}
      style={{
        background: cfg?.bg ?? 'rgba(255,255,255,0.08)',
        color: cfg?.color ?? '#A0A0A8',
      }}
    >
      {small
        ? (cfg ? cfg.label : `${score}`)
        : (prioriteit ? `${score} · ${cfg?.label ?? prioriteit}` : `${score}/100`)
      }
    </span>
  )
}
