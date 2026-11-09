import { motion } from 'framer-motion'
import { ExternalLink } from 'lucide-react'
import EthicsBadge from './ui/EthicsBadge'
import ScoreBadge from './ui/ScoreBadge'
import type { Article } from '../types'

interface Props {
  items: Article[]
  sourceColors: Record<string, string>
  onSelect: (a: Article) => void
}

export default function EditorialGrid({ items, sourceColors, onSelect }: Props) {
  if (!items.length) return null
  const [hero, ...sides] = items

  return (
    <div className="grid gap-2.5" style={{ gridTemplateColumns: '1fr 320px', gridTemplateRows: '1fr 1fr', height: '440px' }}>
      {/* Hero */}
      <motion.article
        className="row-span-2 relative overflow-hidden rounded-xl cursor-pointer group bg-[#0C0C0F]"
        onClick={() => onSelect(hero)}
        whileHover={{ scale: 1.005 }}
        transition={{ type: 'spring', damping: 20, stiffness: 300 }}
      >
        {hero.image_url && (
          <>
            <div
              className="absolute inset-0 bg-cover bg-center transition-transform duration-700 group-hover:scale-105"
              style={{ backgroundImage: `url(${hero.image_url})` }}
            />
            <div className="absolute inset-0 bg-gradient-to-r from-black/90 via-black/50 to-black/10" />
            <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent" />
          </>
        )}
        <div className="absolute bottom-0 left-0 p-7 max-w-[520px] flex flex-col gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded text-white" style={{ background: sourceColors[hero.source] ?? '#888' }}>
              {hero.source}
            </span>
            <ScoreBadge score={hero.relevance_score} prioriteit={hero.prioriteit} />
            {hero.ethics_verdict && <EthicsBadge verdict={hero.ethics_verdict} />}
          </div>
          <h2 className="text-white font-black text-[clamp(1.1rem,2.5vw,1.65rem)] leading-[1.15] tracking-tight">
            {hero.title}
          </h2>
          {hero.relevance_reason && (
            <p className="text-[13px] text-[rgba(226,20,139,0.9)] font-medium line-clamp-1">
              {hero.relevance_reason}
            </p>
          )}
          <div className="flex items-center gap-3 mt-1">
            <button
              onClick={e => { e.stopPropagation(); onSelect(hero) }}
              className="px-4 py-2 rounded-lg gradient-bg text-white text-[13px] font-bold hover:opacity-85 transition-opacity"
            >
              Snelle preview
            </button>
            <a
              href={hero.url}
              target="_blank"
              rel="noopener"
              onClick={e => e.stopPropagation()}
              className="px-4 py-2 rounded-lg bg-white/10 text-white text-[13px] font-semibold hover:bg-white/15 transition-colors flex items-center gap-1.5 border border-white/10"
            >
              Lees artikel <ExternalLink size={12} />
            </a>
          </div>
        </div>
      </motion.article>

      {/* Side cards */}
      {sides.slice(0, 2).map(item => (
        <motion.article
          key={item.url}
          className="relative overflow-hidden rounded-xl cursor-pointer group bg-[#0C0C0F] flex"
          onClick={() => onSelect(item)}
          whileHover={{ scale: 1.01 }}
          transition={{ type: 'spring', damping: 22, stiffness: 280 }}
        >
          {item.image_url && (
            <div
              className="w-[110px] flex-shrink-0 bg-cover bg-center transition-transform duration-500 group-hover:scale-105"
              style={{ backgroundImage: `url(${item.image_url})` }}
            />
          )}
          <div className="flex-1 p-4 flex flex-col gap-2 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded text-white" style={{ background: sourceColors[item.source] ?? '#888' }}>
                {item.source}
              </span>
              <ScoreBadge score={item.relevance_score} prioriteit={item.prioriteit} small />
              {item.ethics_verdict && <EthicsBadge verdict={item.ethics_verdict} small />}
            </div>
            <h3 className="font-bold text-[13.5px] leading-snug text-[#F0F0F0] line-clamp-3">
              {item.title}
            </h3>
            <a
              href={item.url}
              target="_blank"
              rel="noopener"
              onClick={e => e.stopPropagation()}
              className="mt-auto text-[11px] font-semibold text-[#E2148B] hover:opacity-70 transition-opacity"
            >
              Lees ↗
            </a>
          </div>
        </motion.article>
      ))}
    </div>
  )
}
