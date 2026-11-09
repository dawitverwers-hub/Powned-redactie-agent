interface Props {
  verdict: 'GROEN' | 'ORANJE' | 'ROOD'
  small?: boolean
}

const CONFIG = {
  GROEN:  { color: '#22C55E', bg: 'rgba(34,197,94,0.12)',  icon: '✓' },
  ORANJE: { color: '#F59E0B', bg: 'rgba(245,158,11,0.12)', icon: '!' },
  ROOD:   { color: '#EF4444', bg: 'rgba(239,68,68,0.12)',  icon: '✕' },
}

export default function EthicsBadge({ verdict, small }: Props) {
  const cfg = CONFIG[verdict]
  return (
    <span
      className={`inline-flex items-center gap-1 font-bold uppercase tracking-wide rounded ${small ? 'text-[8.5px] px-1 py-0.5' : 'text-[10px] px-1.5 py-0.5'}`}
      style={{ background: cfg.bg, color: cfg.color }}
    >
      <span>{cfg.icon}</span>
      {!small && <span>{verdict}</span>}
    </span>
  )
}
