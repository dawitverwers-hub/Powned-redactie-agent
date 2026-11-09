import { useMemo } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import type { Article, Filters, Stats } from '../types'

interface Props {
  open: boolean
  filters: Filters
  stats?: Stats
  items: Article[]
  onFilter: (key: keyof Filters, val: string | undefined) => void
  onClear: () => void
}

const ETHICS_OPTIONS = [
  { val: 'GROEN',  label: 'Groen',  color: '#22C55E', bg: 'rgba(34,197,94,0.1)',   border: 'rgba(34,197,94,0.2)' },
  { val: 'ORANJE', label: 'Oranje', color: '#F59E0B', bg: 'rgba(245,158,11,0.1)',  border: 'rgba(245,158,11,0.2)' },
  { val: 'ROOD',   label: 'Rood',   color: '#EF4444', bg: 'rgba(239,68,68,0.1)',   border: 'rgba(239,68,68,0.2)' },
]

const PRIO_OPTIONS = [
  { val: 'must-have',  label: 'Must-have',  color: '#E2148B' },
  { val: 'sterk',      label: 'Sterk',      color: '#22C55E' },
  { val: 'interessant',label: 'Interessant',color: '#6366F1' },
]

export default function Sidebar({ open, filters, stats, items, onFilter, onClear }: Props) {
  const cityCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    items.forEach(item => {
      // Use source as a proxy for city filtering (region is the actual geographic data)
      if (item.region && item.region !== 'NL') {
        counts[item.region] = (counts[item.region] ?? 0) + 1
      }
    })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
  }, [items])

  const sourceCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    items.forEach(i => { if (i.source) counts[i.source] = (counts[i.source] ?? 0) + 1 })
    return Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 15)
  }, [items])

  const hasFilters = Object.values(filters).some(Boolean)

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.aside
          key="sidebar"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 224, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          className="flex-shrink-0 overflow-hidden border-r border-[rgba(255,255,255,0.07)] bg-[#0C0C0F] sticky top-[96px] h-[calc(100vh-96px)]"
        >
          <div className="w-[224px] h-full flex flex-col">
            <div className="flex-1 overflow-y-auto px-3 py-4 space-y-5 scrollbar-thin">

              {/* Ethics */}
              <Section label="⚖️ Ethiek">
                <div className="space-y-1.5">
                  {ETHICS_OPTIONS.map(opt => {
                    const count = stats?.[`ethics_${opt.val.toLowerCase()}` as keyof Stats] ?? 0
                    const active = filters.ethics === opt.val
                    return (
                      <button
                        key={opt.val}
                        onClick={() => onFilter('ethics', active ? undefined : opt.val)}
                        className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[12.5px] font-medium transition-all"
                        style={{
                          background: active ? opt.bg : 'transparent',
                          border: `1px solid ${active ? opt.border : 'rgba(255,255,255,0.06)'}`,
                          color: active ? opt.color : '#A0A0A8',
                        }}
                      >
                        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: opt.color }} />
                        <span className="flex-1 text-left">{opt.label}</span>
                        <span className="text-[11px] opacity-60">{count}</span>
                      </button>
                    )
                  })}
                </div>
              </Section>

              {/* Priority */}
              <Section label="🎯 Prioriteit">
                <div className="space-y-1">
                  {PRIO_OPTIONS.map(opt => {
                    const count = stats?.[opt.val.replace('-','_') as keyof Stats] ?? 0
                    const active = filters.prio === opt.val
                    return (
                      <Chip
                        key={opt.val}
                        label={opt.label}
                        count={count as number}
                        active={active}
                        color={opt.color}
                        onClick={() => onFilter('prio', active ? undefined : opt.val)}
                      />
                    )
                  })}
                </div>
              </Section>

              {/* Regions */}
              {cityCounts.length > 0 && (
                <Section label="📍 Regio's">
                  <div className="space-y-1">
                    {cityCounts.map(([region, count]) => (
                      <Chip
                        key={region}
                        label={region}
                        count={count}
                        active={filters.region === region}
                        color="#6366F1"
                        onClick={() => onFilter('region', filters.region === region ? undefined : region)}
                      />
                    ))}
                  </div>
                </Section>
              )}

              {/* Sources */}
              <Section label="📰 Bronnen">
                <div className="space-y-1">
                  {sourceCounts.map(([source, count]) => (
                    <Chip
                      key={source}
                      label={source}
                      count={count}
                      active={false}
                      color="#A0A0A8"
                      onClick={() => {}}
                    />
                  ))}
                </div>
              </Section>

            </div>

            {/* Clear button */}
            <AnimatePresence>
              {hasFilters && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 8 }}
                  className="px-3 py-3 border-t border-[rgba(255,255,255,0.07)]"
                >
                  <button
                    onClick={onClear}
                    className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg border border-[rgba(255,255,255,0.07)] text-[12px] font-medium text-[#A0A0A8] hover:text-[#E2148B] hover:border-[rgba(226,20,139,0.3)] transition-all"
                  >
                    <X size={12} />
                    Wis filters
                  </button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  )
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#606068] px-1 mb-2">{label}</p>
      {children}
    </div>
  )
}

function Chip({ label, count, active, color, onClick }: {
  label: string; count: number; active: boolean; color: string; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-2 px-2.5 py-1.5 rounded-lg text-[12px] transition-all hover:bg-[#1E1E22]"
      style={{ background: active ? '#1E1E22' : 'transparent', color: active ? '#F0F0F0' : '#A0A0A8' }}
    >
      <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: active ? color : '#3C3C44' }} />
      <span className="flex-1 text-left truncate">{label}</span>
      <span className="text-[10px] text-[#606068]">{count}</span>
    </button>
  )
}
