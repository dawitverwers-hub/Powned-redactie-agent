import { useState, useMemo, useCallback } from 'react'
import { motion } from 'framer-motion'
import Header from './Header'
import Sidebar from './Sidebar'
import EditorialGrid from './EditorialGrid'
import HotCard from './HotCard'
import ArticleCard from './ArticleCard'
import NieuwBar from './NieuwBar'
import { useFeed } from '../hooks/useFeed'
import type { Article, Filters } from '../types'

interface Props {
  userName: string
  activeTab: 'relevant' | 'feed'
  onTabChange: (tab: 'relevant' | 'feed') => void
  filters: Filters
  onFiltersChange: (f: Filters) => void
  onArticleSelect: (a: Article) => void
  onShowWelcome: () => void
  lastVisit: string | null
}

const SOURCES_CONFIG = {
  pink: ['PowNed', 'NOS', 'RTL Nieuws', 'Hart van Nederland', 'AD'],
  default: '#888',
}

const SOURCE_COLORS: Record<string, string> = {
  PowNed: '#E2148B', NOS: '#C0392B', 'De Telegraaf': '#003DA5',
  AD: '#B20000', 'RTL Nieuws': '#FF6600', 'Hart van Nederland': '#E8003C',
  Volkskrant: '#D4001A', Trouw: '#004F99', Rijnmond: '#E2148B',
  'NH Nieuws': '#E4001B', AT5: '#FF4500',
}

export default function Dashboard({
  userName, activeTab, onTabChange, filters, onFiltersChange,
  onArticleSelect, onShowWelcome, lastVisit,
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [search, setSearch] = useState('')

  const feedFilters: Filters = useMemo(() => ({
    ...filters,
    ...(search ? { q: search } : {}),
  }), [filters, search])

  const { items, total, pipeline, stats, isLoading, refresh } = useFeed(feedFilters, 300)

  const hotItems = useMemo(() =>
    items.filter(i => i.prioriteit === 'must-have' || i.prioriteit === 'sterk'),
    [items]
  )

  const editorialItems = useMemo(() =>
    hotItems.filter(i => i.image_url).slice(0, 3),
    [hotItems]
  )

  const newItems = useMemo(() => {
    if (!lastVisit) return []
    const since = new Date(lastVisit)
    return items.filter(i => i.published_at && new Date(i.published_at) > since)
  }, [items, lastVisit])

  const handleFilterChange = useCallback((key: keyof Filters, val: string | undefined) => {
    onFiltersChange({ ...filters, [key]: val })
  }, [filters, onFiltersChange])

  return (
    <motion.div
      className="min-h-screen flex flex-col bg-[#000]"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.3 }}
    >
      <Header
        userName={userName}
        pipeline={pipeline}
        total={total}
        search={search}
        onSearch={setSearch}
        onShowWelcome={onShowWelcome}
        onRefresh={refresh}
        sidebarOpen={sidebarOpen}
        onToggleSidebar={() => setSidebarOpen(p => !p)}
      />

      {/* Tabs */}
      <div className="sticky top-[60px] z-30 border-b border-[rgba(255,255,255,0.07)] bg-[rgba(0,0,0,0.92)] backdrop-blur-xl flex">
        {(['relevant', 'feed'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => onTabChange(tab)}
            className={`relative px-5 h-11 text-[13px] font-semibold transition-colors ${
              activeTab === tab ? 'text-[#F0F0F0]' : 'text-[#606068] hover:text-[#A0A0A8]'
            }`}
          >
            {tab === 'relevant' ? '🔥 PowNed Relevant' : '📰 Alle artikelen'}
            {activeTab === tab && (
              <motion.div
                layoutId="tab-indicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 gradient-bg"
              />
            )}
            <span className={`ml-2 text-[11px] px-1.5 py-0.5 rounded ${
              activeTab === tab ? 'gradient-bg text-white' : 'bg-[#1E1E22] text-[#606068]'
            }`}>
              {tab === 'relevant' ? hotItems.length : total}
            </span>
          </button>
        ))}
      </div>

      <div className="flex flex-1 relative">
        {/* Sidebar */}
        <Sidebar
          open={sidebarOpen}
          filters={filters}
          stats={stats}
          items={items}
          onFilter={handleFilterChange}
          onClear={() => onFiltersChange({})}
        />

        {/* Main content */}
        <main className="flex-1 min-w-0 p-6">
          <NieuwBar newItems={newItems} />

          {isLoading ? (
            <LoadingSkeleton />
          ) : (
            <>
              {/* Editorial Grid */}
              {editorialItems.length > 0 && (
                <div className="mb-8">
                  <EditorialGrid
                    items={editorialItems}
                    sourceColors={SOURCE_COLORS}
                    onSelect={onArticleSelect}
                  />
                </div>
              )}

              {activeTab === 'relevant' ? (
                <RelevantView
                  hotItems={hotItems.slice(3)}
                  sourceColors={SOURCE_COLORS}
                  onSelect={onArticleSelect}
                />
              ) : (
                <FeedView
                  items={items}
                  sourceColors={SOURCE_COLORS}
                  onSelect={onArticleSelect}
                />
              )}
            </>
          )}
        </main>
      </div>
    </motion.div>
  )
}

function RelevantView({ hotItems, sourceColors, onSelect }: {
  hotItems: Article[]
  sourceColors: Record<string,string>
  onSelect: (a: Article) => void
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[11px] font-bold uppercase tracking-widest text-[#606068]">Top gescoord</span>
        <div className="flex-1 h-px bg-[rgba(255,255,255,0.07)]" />
      </div>
      <div className="grid gap-3">
        {hotItems.map((item, i) => (
          <HotCard
            key={item.url}
            article={item}
            index={i}
            sourceColor={sourceColors[item.source] ?? '#888'}
            onSelect={onSelect}
          />
        ))}
        {hotItems.length === 0 && (
          <EmptyState text="Geen relevante artikelen voor deze filters" />
        )}
      </div>
    </div>
  )
}

function FeedView({ items, sourceColors, onSelect }: {
  items: Article[]
  sourceColors: Record<string,string>
  onSelect: (a: Article) => void
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="text-[11px] font-bold uppercase tracking-widest text-[#606068]">Alle artikelen</span>
        <div className="flex-1 h-px bg-[rgba(255,255,255,0.07)]" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {items.map((item, i) => (
          <ArticleCard
            key={item.url}
            article={item}
            index={i}
            sourceColor={sourceColors[item.source] ?? '#888'}
            onSelect={onSelect}
          />
        ))}
        {items.length === 0 && (
          <div className="col-span-full">
            <EmptyState text="Geen artikelen gevonden" />
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-[#606068]">
      <span className="text-4xl mb-3 opacity-30">📭</span>
      <p className="text-sm">{text}</p>
    </div>
  )
}

function LoadingSkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      <div className="h-[420px] rounded-xl bg-[#0C0C0F]" />
      {[1,2,3,4].map(i => (
        <div key={i} className="h-24 rounded-xl bg-[#0C0C0F]" />
      ))}
    </div>
  )
}
