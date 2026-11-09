import { Search, SlidersHorizontal, RefreshCw, Zap } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import type { Pipeline } from '../types'

interface Props {
  userName: string
  pipeline?: Pipeline
  total: number
  search: string
  onSearch: (q: string) => void
  onShowWelcome: () => void
  onRefresh: () => void
  sidebarOpen: boolean
  onToggleSidebar: () => void
}

export default function Header({
  userName, pipeline, total, search, onSearch, onShowWelcome,
  onRefresh, sidebarOpen, onToggleSidebar,
}: Props) {
  const fresh = pipeline?.fresh ?? true
  const running = pipeline?.running ?? false

  return (
    <header className="sticky top-0 z-40 h-[60px] flex items-center gap-3 px-4 glass border-b border-[rgba(255,255,255,0.07)]">
      {/* Gradient line at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-[1px] gradient-bg opacity-50" />

      {/* Sidebar toggle */}
      <button
        onClick={onToggleSidebar}
        className={`flex items-center justify-center w-9 h-9 rounded-lg border transition-all ${
          sidebarOpen
            ? 'border-[rgba(226,20,139,0.4)] text-[#E2148B] bg-[rgba(226,20,139,0.08)]'
            : 'border-[rgba(255,255,255,0.07)] text-[#606068] hover:text-[#A0A0A8] hover:border-[rgba(255,255,255,0.13)]'
        }`}
        title="Filters"
      >
        <SlidersHorizontal size={15} />
      </button>

      {/* Logo */}
      <button
        onClick={onShowWelcome}
        className="flex items-center gap-2.5 flex-shrink-0 hover:opacity-80 transition-opacity"
        title="Terug naar startscherm"
      >
        <img
          src="https://www.google.com/s2/favicons?sz=64&domain=powned.tv"
          alt="PowNed"
          className="w-8 h-8 rounded-md"
        />
        <span className="text-[11px] font-semibold text-[#606068] uppercase tracking-widest hidden sm:block">
          Redactie
        </span>
      </button>

      {/* Search */}
      <div className="flex-1 relative max-w-sm mx-2">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#606068] pointer-events-none" />
        <input
          type="search"
          value={search}
          onChange={e => onSearch(e.target.value)}
          placeholder="Zoek in artikelen…"
          className="w-full pl-8 pr-3 py-2 bg-[#141417] border border-[rgba(255,255,255,0.07)] rounded-lg text-[13px] text-[#F0F0F0] placeholder-[#606068] outline-none focus:border-[rgba(226,20,139,0.4)] focus:ring-1 focus:ring-[rgba(226,20,139,0.15)] transition-all"
        />
      </div>

      {/* Pipeline status */}
      <AnimatePresence mode="wait">
        {pipeline && (
          <motion.div
            key={running ? 'running' : 'idle'}
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#141417] border border-[rgba(255,255,255,0.07)] text-[12px] flex-shrink-0"
          >
            {running ? (
              <RefreshCw size={11} className="text-[#E2148B] animate-spin" />
            ) : (
              <span
                className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                style={{
                  background: fresh ? '#22C55E' : '#F59E0B',
                  boxShadow: fresh ? '0 0 5px #22C55E' : 'none',
                }}
              />
            )}
            <span className="text-[#A0A0A8]">
              {running ? 'Bezig…' : `⚡ ${pipeline.age_minutes < 2 ? 'zojuist' : `${pipeline.age_minutes}m`}`}
            </span>
            {pipeline.new_count > 0 && (
              <span className="text-[#E2148B] font-bold">+{pipeline.new_count}</span>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Right actions */}
      <div className="ml-auto flex items-center gap-2">
        <span className="text-[12px] text-[#606068] hidden lg:block">
          <strong className="text-[#A0A0A8]">{total}</strong> artikelen
        </span>
        <div className="w-px h-5 bg-[rgba(255,255,255,0.07)] hidden lg:block" />
        <button
          onClick={() => onRefresh()}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#141417] border border-[rgba(255,255,255,0.07)] hover:border-[rgba(255,255,255,0.13)] text-[12px] font-medium text-[#A0A0A8] hover:text-[#F0F0F0] transition-all"
        >
          <Zap size={12} />
          <span className="hidden sm:inline">Vernieuwen</span>
        </button>
      </div>
    </header>
  )
}
