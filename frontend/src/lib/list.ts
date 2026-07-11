import type { Paginated } from '../types'

/** Accepts either a bare array or a { items } envelope and returns the array. */
export function asList<T>(res: Paginated<T> | T[] | null | undefined): T[] {
  if (!res) return []
  if (Array.isArray(res)) return res
  return res.items ?? []
}
