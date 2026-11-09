import { motion } from 'framer-motion'
import EthicsBadge from './ui/EthicsBadge'
import ScoreBadge from './ui/ScoreBadge'
import type { Article } from '../types'

interface Props {
  article: Article
  index: number
  sourceColor: string
  onSelect: (a: Article) => void
}

export default function ArticleCard({ article, index, sourceColor, onSelect }: Props) {
  const isMustHave = article.prioriteit === 'must-have'
  const snippet = article.content?.replace(/<[^>]+>/g, '').slice(0, 120)
  const pub = article.published_at
    ? new Date(article.published_at).toLocaleString('nl-NL', { hour:'2-digit', minute:'2-digit', day: 'numeric', month: 'short' })
    : ''

  return (
    <motion.article
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.02, type: 'spring', damping: 26, stiffness: 280 }}
      onClick={() => onSelect(article)}
      className={`group flex flex-col rounded-xl cursor-pointer overflow-hidden border transition-all
        ${isMustHave
          ? 'must-have-card border-[rgba(226,20,139,0.2)]'
          : 'bg-[#0C0C0F] border-[rgba(255,255,255,0.07)] hover:border-[rgba(255,255,255,0.13)]'
        }`}
      whileHover={{ y: -2, transition: { type: 'spring', damping: 20, stiffness: 300 } }}
    >
      {/* Image */}
      {article.image_url ? (
        <div
          className="h-36 bg-cover bg-center transition-transform duration-500 group-hover:scale-105"
          style={{ backgroundImage: `url(${article.image_url})` }}
        />
      ) : (
        <div className="h-36 bg-[#141417] flex items-center justify-center">
          <span className="text-3xl opacity-20">📰</span>
        </div>
      )}

      {/* Body */}
      <div className="flex flex-col gap-2 p-3.5 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className="text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded text-white flex-shrink-0"
            style={{ background: sourceColor }}
          >
            {article.source}
          </span>
          <ScoreBadge score={article.relevance_score} prioriteit={article.prioriteit} small />
          {article.ethics_verdict && <EthicsBadge verdict={article.ethics_verdict} small />}
        </div>

        <h3 className="font-bold text-[13px] text-[#F0F0F0] leading-snug line-clamp-2">
          {article.title}
        </h3>

        {snippet && (
          <p className="text-[11.5px] text-[#606068] leading-relaxed line-clamp-2">{snippet}…</p>
        )}

        {article.region && article.region !== 'NL' && (
          <span className="text-[10px] text-[#606068]">{article.region}</span>
        )}

        <time className="text-[10.5px] text-[#606068] mt-auto">{pub}</time>
      </div>
    </motion.article>
  )
}
