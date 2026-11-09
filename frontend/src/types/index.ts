export interface Article {
  url: string
  title: string
  source: string
  region: string
  published_at: string
  fetched_at: string
  content: string
  full_content: string
  image_url: string
  relevance_score: number
  relevance_reason: string
  score_breakdown: string
  prioriteit: 'must-have' | 'sterk' | 'interessant' | 'zwak' | 'afwijzen' | null
  ethics_verdict: 'GROEN' | 'ORANJE' | 'ROOD' | null
  ethics_score: number
  ethics_report: string
}

export interface Pipeline {
  age_minutes: number
  new_count: number
  running: boolean
  fresh: boolean
}

export interface Stats {
  must_have: number
  sterk: number
  interessant: number
  ethics_groen: number
  ethics_oranje: number
  ethics_rood: number
}

export interface FeedResponse {
  items: Article[]
  total: number
  pipeline: Pipeline
  stats: Stats
}

export interface Filters {
  prio?: string
  ethics?: string
  region?: string
  city?: string
  q?: string
  days?: number
}
