import useSWR from 'swr'
import type { FeedResponse, Filters } from '../types'

const fetcher = (url: string) => fetch(url).then(r => r.json())

export function useFeed(filters: Filters = {}, limit = 200) {
  const params = new URLSearchParams({ limit: String(limit) })
  if (filters.prio)   params.set('prio', filters.prio)
  if (filters.ethics) params.set('ethics', filters.ethics)
  if (filters.region) params.set('region', filters.region)
  if (filters.q)      params.set('q', filters.q)

  const { data, error, isLoading, mutate } = useSWR<FeedResponse>(
    `/api/feed?${params}`,
    fetcher,
    { refreshInterval: 120_000, revalidateOnFocus: false }
  )

  return {
    data,
    items: data?.items ?? [],
    total: data?.total ?? 0,
    pipeline: data?.pipeline,
    stats: data?.stats,
    isLoading,
    error,
    refresh: mutate,
  }
}

export function useStatus() {
  const { data } = useSWR('/status', fetcher, { refreshInterval: 30_000 })
  return data
}
