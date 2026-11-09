import { useState, useEffect } from 'react'
import { AnimatePresence } from 'framer-motion'
import WelcomeScreen from './components/WelcomeScreen'
import Dashboard from './components/Dashboard'
import ArticleModal from './components/ArticleModal'
import type { Article, Filters } from './types'

export default function App() {
  const [welcomed, setWelcomed] = useState(() =>
    !!sessionStorage.getItem('powned_welcomed')
  )
  const [userName, setUserName] = useState(() =>
    localStorage.getItem('powned_name') || 'Moos'
  )
  const [activeTab, setActiveTab] = useState<'relevant' | 'feed'>('relevant')
  const [filters, setFilters] = useState<Filters>({})
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null)
  const [lastVisit] = useState(() => localStorage.getItem('powned_last_visit'))

  useEffect(() => {
    return () => {
      localStorage.setItem('powned_last_visit', new Date().toISOString())
    }
  }, [])

  const handleEnterFeed = (tab: 'relevant' | 'feed', filter?: string) => {
    sessionStorage.setItem('powned_welcomed', '1')
    setActiveTab(tab)
    if (filter === 'must-have') setFilters({ prio: 'must-have' })
    else if (filter === 'regionaal') setFilters({ region: 'Noord-Holland' })
    else setFilters({})
    setWelcomed(true)
  }

  const handleNameChange = (name: string) => {
    setUserName(name)
    localStorage.setItem('powned_name', name)
  }

  const showWelcome = () => {
    sessionStorage.removeItem('powned_welcomed')
    setWelcomed(false)
  }

  return (
    <>
      <AnimatePresence mode="wait">
        {!welcomed ? (
          <WelcomeScreen
            key="welcome"
            userName={userName}
            onEnter={handleEnterFeed}
            onNameChange={handleNameChange}
          />
        ) : (
          <Dashboard
            key="dashboard"
            userName={userName}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            filters={filters}
            onFiltersChange={setFilters}
            onArticleSelect={setSelectedArticle}
            onShowWelcome={showWelcome}
            lastVisit={lastVisit}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {selectedArticle && (
          <ArticleModal
            article={selectedArticle}
            onClose={() => setSelectedArticle(null)}
          />
        )}
      </AnimatePresence>
    </>
  )
}
