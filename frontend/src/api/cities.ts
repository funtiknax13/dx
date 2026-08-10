import { api } from './client'

export interface CityResult {
  id: number
  name: string
  region: string | null
  country: string | null
  lat: number
  lng: number
}

export const citiesApi = {
  search: (q: string, limit = 8) =>
    api.get<CityResult[]>('/cities/search', { query: { q, limit }, auth: false }),
}
