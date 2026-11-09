import { motion } from 'framer-motion'
import { ExternalLink } from 'lucide-react'
import EthicsBadge from './ui/EthicsBadge'
import ScoreBadge from './ui/ScoreBadge'
import type { Article } from '../types'

interface Props {
  article: Article
  index: number
  sourceColor: string
  onSelect: (a: Article) => void
}

export default function HotCard({ article, index, sourceColor, onSelect }: Props) {
  const isMustHave = article.prioriteit === 'must-have'

  return (
    <motion.article
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, type: 'spring', damping: 24, stiffness: 260 }}
      onClick={() => onSelect(article)}
      className={`group relative flex gap-4 p-4 rounded-xl cursor-pointer border transition-all
        ${isMustHave
          ? 'must-have-card border-[rgba(226,20,139,0.2)]'
          : 'bg-[#0C0C0F] border-[rgba(255,255,255,0.07)] hover:border-[rgba(255,255,255,0.13)]'
        }`}
      whileHover={{ y: -1, transition: { type: 'spring', damping: 20, stiffness: 300 } }}
    >
      {/* Thumbnail */}
      {article.image_url && (
        <div
          className="w-20 h-20 flex-shrink-0 rounded-lg bg-cover bg-center overflow-hidden"
          style={{ backgroundImage: `url(${article.image_url})` }}
        />
      )}

      {/* Content */}
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span
            className="text-[9.5px] font-bold uppercase tracking-wide px-2 py-0.5 rounded text-white flex-shrink-0"
            style={{ background: sourceColor }}
          >
            {article.source}
          </span>
          <ScoreBadge score={article.relevance_score} prioriteit={article.prioriteit} small />
          {article.ethics_verdict && <EthicsBadge verdict={article.ethics_verdict} small />}
          {article.region && article.region !== 'NL' && (
            <span className="text-[10px] text-[#606068]">{article.region}</span>
          )}
        </div>

        <h3 className={`font-bold leading-snug line-clamp-2 ${isMustHave ? 'text-[15px] text-white' : 'text-[14px] text-[#F0F0F0]'}`}>
          {article.title}
        </h3>

        {article.relevance_reason && (
          <p className="text-[11.5px] text-[#E2148B] font-medium line-clamp-1 opacity-80">
            {article.relevance_reason}
          </p>
        )}
      </div>

      {/* Action */}
      <div className="flex-shrink-0 flex items-center self-center">
        <a
          href={article.url}
          target="_blank"
          rel="noopener"
          onClick={e => e.stopPropagation()}
          className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg bg-[rgba(255,255,255,0.06)] hover:bg-[rgba(255,255,255,0.12)] text-[#A0A0A8]"
        >
          <ExternalLink size={13} />
        </a>
      </div>
    </motion.article>
  )
}
