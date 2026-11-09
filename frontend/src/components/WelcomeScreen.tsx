import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { useFeed } from '../hooks/useFeed'

interface Props {
  userName: string
  onEnter: (tab: 'relevant' | 'feed', filter?: string) => void
  onNameChange: (name: string) => void
}

function greeting() {
  const h = new Date().getHours()
  if (h >= 6  && h < 12) return 'Goedemorgen,'
  if (h >= 12 && h < 18) return 'Goedemiddag,'
  if (h >= 18)           return 'Goedenavond,'
  return 'Goedenacht,'
}

function dateStr() {
  const d = new Date()
  const days = ['zo','ma','di','wo','do','vr','za']
  const months = ['jan','feb','mrt','apr','mei','jun','jul','aug','sep','okt','nov','dec']
  return `${days[d.getDay()]} ${d.getDate()} ${months[d.getMonth()]}`
}

const container = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.08, delayChildren: 0.1 } },
  exit: { opacity: 0, scale: 0.97, transition: { duration: 0.3 } },
}

const item = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 22, stiffness: 250 } },
}

const cardVariant = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { type: 'spring', damping: 22, stiffness: 220 } },
}

export default function WelcomeScreen({ userName, onEnter, onNameChange }: Props) {
  const { stats, pipeline } = useFeed({}, 1)
  const [editingName, setEditingName] = useState(false)
  const [nameInput, setNameInput] = useState(userName)

  useEffect(() => { setNameInput(userName) }, [userName])

  const handleNameSave = () => {
    if (nameInput.trim()) { onNameChange(nameInput.trim()); setEditingName(false) }
  }

  const feeds = [
    {
      icon: '🔥',
      title: 'PowNed Relevant',
      sub: 'Top gescoorde verhalen van vandaag',
      count: (stats?.must_have ?? 0) + (stats?.sterk ?? 0),
      tab: 'relevant' as const,
      filter: '',
      accent: '#E2148B',
    },
    {
      icon: '⚡',
      title: 'Must-have',
      sub: 'Alleen de urgente — vandaag publiceren',
      count: stats?.must_have ?? 0,
      tab: 'relevant' as const,
      filter: 'must-have',
      accent: '#FF6B35',
    },
    {
      icon: '📰',
      title: 'Alle artikelen',
      sub: 'Volledige nieuwsfeed — alle bronnen',
      count: (stats as any)?.total ?? 0,
      tab: 'feed' as const,
      filter: '',
      accent: '#6366F1',
    },
    {
      icon: '📍',
      title: 'Regionaal',
      sub: 'Lokaal nieuws met landelijke haak',
      count: (stats as any)?.regionaal ?? 0,
      tab: 'feed' as const,
      filter: 'regionaal',
      accent: '#10B981',
    },
  ]

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-[#000]"
      variants={container}
      initial="hidden"
      animate="show"
      exit="exit"
    >
      {/* Subtle grid background */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage: 'linear-gradient(rgba(226,20,139,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(226,20,139,0.5) 1px, transparent 1px)',
          backgroundSize: '48px 48px',
        }}
      />

      <div className="relative w-full max-w-[640px] px-6 py-16 flex flex-col gap-10">

        {/* Greeting */}
        <motion.div variants={item} className="flex flex-col gap-1">
          <span
            className="text-5xl font-black tracking-tight leading-[1] text-[#F0F0F0]"
            style={{ letterSpacing: '-0.03em' }}
          >
            {greeting()}
          </span>
          {editingName ? (
            <div className="flex items-center gap-2 mt-1">
              <input
                autoFocus
                value={nameInput}
                onChange={e => setNameInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleNameSave()}
                onBlur={handleNameSave}
                className="text-5xl font-black tracking-tight leading-[1] bg-transparent border-b-2 border-[#E2148B] outline-none text-transparent"
                style={{
                  background: 'linear-gradient(135deg, #E2148B, #9C2D8F)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                  letterSpacing: '-0.03em',
                  minWidth: '120px',
                  width: `${nameInput.length + 1}ch`,
                }}
              />
            </div>
          ) : (
            <button
              onClick={() => setEditingName(true)}
              className="text-5xl font-black tracking-tight leading-[1] gradient-text text-left hover:opacity-80 transition-opacity"
              style={{ letterSpacing: '-0.03em' }}
              title="Naam aanpassen"
            >
              {userName}.
            </button>
          )}

          <div className="flex items-center gap-3 mt-3">
            <span className="text-sm text-[#606068]">{dateStr()}</span>
            {pipeline && (
              <div className="flex items-center gap-2 text-xs px-2.5 py-1 rounded-md bg-[#141417] border border-[rgba(255,255,255,0.07)]">
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: pipeline.fresh ? '#22C55E' : '#F59E0B', boxShadow: pipeline.fresh ? '0 0 6px #22C55E' : 'none' }}
                />
                <span className="text-[#A0A0A8]">
                  {pipeline.running ? 'Bezig…' : `Pipeline: ${pipeline.age_minutes < 2 ? 'zojuist' : `${pipeline.age_minutes}m geleden`}`}
                </span>
                {pipeline.new_count > 0 && (
                  <span className="text-[#E2148B] font-bold">+{pipeline.new_count}</span>
                )}
              </div>
            )}
          </div>
        </motion.div>

        {/* Sub label */}
        <motion.p variants={item} className="text-[#606068] text-sm -mt-4">
          Wat wil je vandaag bekijken?
        </motion.p>

        {/* Feed options */}
        <motion.div
          variants={item}
          className="grid grid-cols-2 gap-3"
        >
          {feeds.map((feed) => (
            <motion.button
              key={feed.title}
              variants={cardVariant}
              onClick={() => onEnter(feed.tab, feed.filter)}
              whileHover={{ y: -3, transition: { type: 'spring', damping: 20, stiffness: 300 } }}
              whileTap={{ scale: 0.97 }}
              className="group flex flex-col gap-2 p-5 text-left rounded-xl bg-[#0C0C0F] border border-[rgba(255,255,255,0.07)] hover:border-[rgba(255,255,255,0.13)] transition-colors relative overflow-hidden"
            >
              <div
                className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-300"
                style={{ background: `radial-gradient(circle at 0% 0%, ${feed.accent}10, transparent 60%)` }}
              />
              <span className="text-2xl leading-none relative z-10">{feed.icon}</span>
              <span className="font-bold text-[#F0F0F0] text-[15px] leading-tight relative z-10">{feed.title}</span>
              <span className="text-[#A0A0A8] text-[12px] leading-snug relative z-10">{feed.sub}</span>
              <div className="flex items-center justify-between mt-1 relative z-10">
                <span className="text-[11px] font-bold" style={{ color: feed.accent }}>
                  {feed.count > 0 ? `${feed.count} items` : '—'}
                </span>
                <span className="text-[#606068] text-sm group-hover:text-[#A0A0A8] group-hover:translate-x-0.5 transition-all">›</span>
              </div>
            </motion.button>
          ))}
        </motion.div>

        {/* Footer */}
        <motion.div variants={item} className="flex items-center gap-4">
          <button
            onClick={() => onEnter('relevant')}
            className="text-[13px] text-[#606068] hover:text-[#A0A0A8] transition-colors"
          >
            Of ga direct naar de feed →
          </button>
          <button
            onClick={() => setEditingName(true)}
            className="text-[12px] text-[#606068] hover:text-[#A0A0A8] transition-colors flex items-center gap-1 ml-auto"
          >
            ✏ Naam
          </button>
        </motion.div>
      </div>
    </motion.div>
  )
}
