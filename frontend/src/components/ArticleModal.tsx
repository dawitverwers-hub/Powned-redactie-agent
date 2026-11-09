import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { X, ExternalLink, AlertTriangle, CheckCircle, XCircle } from 'lucide-react'
import type { Article } from '../types'

interface Props {
  article: Article
  onClose: () => void
}

const SCORE_CRITERIA = [
  { key: 'viraal',              label: 'Viraal potentieel',  max: 25 },
  { key: 'visueel',             label: 'Visueel materiaal',  max: 20 },
  { key: 'nieuwswaarde',        label: 'Nieuwswaarde',       max: 20 },
  { key: 'landelijkPotentieel', label: 'Landelijk potentieel',max: 20 },
  { key: 'doelgroepfit',        label: 'Doelgroepfit 18-35', max: 15 },
]

const ETHICS_CRITERIA = [
  { key: 'bronherkomst_legitimiteit',      label: 'Bronherkomst' },
  { key: 'paywall_copyright',              label: 'Paywall / copyright' },
  { key: 'privacy_persoonsgegevens',       label: 'Privacy' },
  { key: 'verificatie_framing',            label: 'Verificatie & framing' },
  { key: 'eenzijdigheid_hoor_wederhoor',   label: 'Hoor & wederhoor' },
  { key: 'clickbait_sensatiezucht',        label: 'Clickbait' },
  { key: 'ethische_verkrijging',           label: 'Ethische verkrijging' },
]

export default function ArticleModal({ article, onClose }: Props) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  let scoreBreakdown: Record<string, number> = {}
  let ethicsReport: Record<string, any> = {}
  try { scoreBreakdown = JSON.parse(article.score_breakdown ?? '{}') } catch {}
  try { ethicsReport = JSON.parse(article.ethics_report ?? '{}') } catch {}

  const ethicsScores = ethicsReport?.scores ?? {}
  const ethicsVerdict = article.ethics_verdict
  const verdictColor = { GROEN: '#22C55E', ORANJE: '#F59E0B', ROOD: '#EF4444' }[ethicsVerdict ?? ''] ?? '#606068'

  const pub = article.published_at
    ? new Date(article.published_at).toLocaleString('nl-NL', { weekday:'long', year:'numeric', month:'long', day:'numeric', hour:'2-digit', minute:'2-digit' })
    : ''

  const content = article.full_content
    ? article.full_content.replace(/<[^>]+>/g, '').slice(0, 2000)
    : article.content?.replace(/<[^>]+>/g, '').slice(0, 500) ?? ''

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      {/* Backdrop */}
      <motion.div
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onClose}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
      />

      {/* Modal */}
      <motion.div
        className="relative w-full max-w-2xl max-h-[90vh] flex flex-col bg-[#0C0C0F] border border-[rgba(255,255,255,0.1)] rounded-t-2xl sm:rounded-2xl overflow-hidden shadow-2xl"
        initial={{ opacity: 0, y: 40, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 20, scale: 0.97 }}
        transition={{ type: 'spring', damping: 25, stiffness: 280 }}
      >
        {/* Image header */}
        {article.image_url && (
          <div className="relative h-48 flex-shrink-0 overflow-hidden">
            <img src={article.image_url} alt="" className="w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0C0C0F] via-transparent to-transparent" />
          </div>
        )}

        {/* Close btn */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 w-8 h-8 flex items-center justify-center rounded-full bg-black/50 backdrop-blur text-white hover:bg-black/70 transition-colors"
        >
          <X size={15} />
        </button>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Meta */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded text-white bg-[#E2148B]">
              {article.source}
            </span>
            {article.prioriteit && (
              <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded ${
                article.prioriteit === 'must-have' ? 'bg-[rgba(226,20,139,0.2)] text-[#E2148B]' :
                article.prioriteit === 'sterk' ? 'bg-[rgba(34,197,94,0.2)] text-[#22C55E]' :
                'bg-[#1E1E22] text-[#A0A0A8]'
              }`}>
                {article.prioriteit}
              </span>
            )}
            {ethicsVerdict && (
              <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-1 rounded" style={{
                background: `${verdictColor}20`, color: verdictColor
              }}>
                {ethicsVerdict === 'GROEN' ? <CheckCircle size={10} className="inline mr-1" /> :
                 ethicsVerdict === 'ROOD' ? <XCircle size={10} className="inline mr-1" /> :
                 <AlertTriangle size={10} className="inline mr-1" />}
                {ethicsVerdict}
              </span>
            )}
          </div>

          {/* Title */}
          <h2 className="text-[20px] font-black leading-tight text-[#F0F0F0] tracking-tight">
            {article.title}
          </h2>

          {pub && <p className="text-[12px] text-[#606068]">{pub}</p>}

          {/* AI Reason */}
          {article.relevance_reason && (
            <div className="px-3 py-2.5 rounded-lg bg-[rgba(226,20,139,0.08)] border border-[rgba(226,20,139,0.15)]">
              <p className="text-[12px] text-[rgba(226,20,139,0.9)] font-medium">💡 {article.relevance_reason}</p>
            </div>
          )}

          {/* Content */}
          {content && (
            <div>
              <p className="text-[11px] font-bold uppercase tracking-widest text-[#606068] mb-2">Inhoud</p>
              <p className="text-[13.5px] text-[#A0A0A8] leading-relaxed">
                {content}{content.length >= 500 ? '…' : ''}
              </p>
            </div>
          )}

          {/* Score breakdown */}
          {Object.keys(scoreBreakdown).length > 0 && (
            <div>
              <p className="text-[11px] font-bold uppercase tracking-widest text-[#606068] mb-3">
                Score — {article.relevance_score}/100
              </p>
              <div className="space-y-2">
                {SCORE_CRITERIA.map(c => {
                  const val = scoreBreakdown[c.key] ?? 0
                  const pct = (val / c.max) * 100
                  return (
                    <div key={c.key} className="flex items-center gap-3">
                      <span className="text-[11px] text-[#A0A0A8] w-36 flex-shrink-0">{c.label}</span>
                      <div className="flex-1 h-1.5 bg-[#1E1E22] rounded-full overflow-hidden">
                        <motion.div
                          className="h-full gradient-bg rounded-full"
                          initial={{ width: 0 }}
                          animate={{ width: `${pct}%` }}
                          transition={{ delay: 0.1, duration: 0.5, ease: 'easeOut' }}
                        />
                      </div>
                      <span className="text-[11px] font-bold text-[#F0F0F0] w-12 text-right font-mono">
                        {val}/{c.max}
                      </span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Ethics breakdown */}
          {Object.keys(ethicsScores).length > 0 && (
            <div>
              <p className="text-[11px] font-bold uppercase tracking-widest text-[#606068] mb-3">
                Ethiekcheck — {article.ethics_score}/100
              </p>
              <div className="space-y-1.5">
                {ETHICS_CRITERIA.map(c => {
                  const val = ethicsScores[c.key] ?? 0
                  const color = val >= 70 ? '#22C55E' : val >= 45 ? '#F59E0B' : '#EF4444'
                  return (
                    <div key={c.key} className="flex items-center gap-3">
                      <span className="text-[11px] text-[#A0A0A8] w-36 flex-shrink-0">{c.label}</span>
                      <div className="flex-1 h-1 bg-[#1E1E22] rounded-full overflow-hidden">
                        <motion.div
                          className="h-full rounded-full"
                          style={{ background: color }}
                          initial={{ width: 0 }}
                          animate={{ width: `${val}%` }}
                          transition={{ delay: 0.2, duration: 0.4, ease: 'easeOut' }}
                        />
                      </div>
                      <span className="text-[11px] font-bold w-8 text-right font-mono" style={{ color }}>{val}</span>
                    </div>
                  )
                })}
              </div>
              {ethicsReport?.aanbeveling && (
                <p className="mt-3 text-[12px] text-[#A0A0A8] italic">{ethicsReport.aanbeveling}</p>
              )}
            </div>
          )}
        </div>

        {/* Footer actions */}
        <div className="flex-shrink-0 flex items-center gap-2 p-4 border-t border-[rgba(255,255,255,0.07)]">
          <a
            href={article.url}
            target="_blank"
            rel="noopener"
            className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl gradient-bg text-white text-[13px] font-bold hover:opacity-85 transition-opacity"
          >
            Lees origineel <ExternalLink size={13} />
          </a>
          <button
            onClick={onClose}
            className="px-5 py-2.5 rounded-xl bg-[#1E1E22] border border-[rgba(255,255,255,0.07)] text-[#A0A0A8] text-[13px] font-medium hover:text-[#F0F0F0] transition-colors"
          >
            Sluiten
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
