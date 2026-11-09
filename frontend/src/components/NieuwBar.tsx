import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import type { Article } from '../types'

interface Props {
  newItems: Article[]
}

export default function NieuwBar({ newItems }: Props) {
  const [dismissed, setDismissed] = useState(false)

  if (dismissed || newItems.length === 0) return null

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ type: 'spring', damping: 22, stiffness: 260 }}
        className="flex items-center gap-3 mb-5 px-4 py-2.5 rounded-xl bg-[rgba(226,20,139,0.07)] border border-[rgba(226,20,139,0.2)]"
      >
        <motion.span
          className="w-2 h-2 rounded-full bg-[#E2148B] flex-shrink-0"
          animate={{ opacity: [1, 0.3, 1] }}
          transition={{ duration: 1.4, repeat: Infinity }}
        />
        <span className="text-[13px] font-bold text-[#E2148B]">
          {newItems.length} nieuw
        </span>
        <span className="text-[12px] text-[#A0A0A8]">
          sinds je laatste bezoek
        </span>
        <button
          onClick={() => {
            setDismissed(true)
            localStorage.setItem('powned_last_visit', new Date().toISOString())
          }}
          className="ml-auto text-[#606068] hover:text-[#A0A0A8] transition-colors"
        >
          <X size={14} />
        </button>
      </motion.div>
    </AnimatePresence>
  )
}
