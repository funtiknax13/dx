import { api } from './client'
import type { EventDetail, EventPhoto, EventSummary, Paginated } from '../types'

// Raw shapes as actually returned by the backend (see backend/app/schemas/event.py) —
// kept private to this module; every exported method returns the frontend's own
// EventSummary/EventDetail/EventPhoto types via the mappers below.
interface RawEvent {
  id: number
  title: string
  date: string
  description?: string | null
  cover_image?: string | null
}

interface RawEventPhoto {
  id: number
  event_id: number
  image: string
  thumbnail?: string | null
}

function mapEvent(raw: RawEvent): EventSummary {
  return {
    id: raw.id,
    title: raw.title,
    date: raw.date,
    description: raw.description ?? null,
    cover_url: raw.cover_image ?? null,
  }
}

function mapPhoto(raw: RawEventPhoto): EventPhoto {
  return { id: raw.id, url: raw.image, thumbnail_url: raw.thumbnail ?? null, caption: null }
}

export const eventsApi = {
  list: async (params?: { page?: number; page_size?: number; upcoming?: boolean }) => {
    const res = await api.get<Paginated<RawEvent> | RawEvent[]>('/events', { query: params })
    const items = Array.isArray(res) ? res : res.items
    return items.map(mapEvent)
  },

  detail: async (id: number | string): Promise<EventDetail> => {
    const raw = await api.get<RawEvent>(`/events/${id}`)
    return { ...mapEvent(raw), photos: [], groups: [] }
  },

  photos: async (id: number | string) => {
    const raw = await api.get<RawEventPhoto[]>(`/events/${id}/photos`)
    return raw.map(mapPhoto)
  },

  create: async (payload: { title: string; date: string; description?: string }) =>
    mapEvent(await api.post<RawEvent>('/events', payload)),

  update: async (
    id: number | string,
    payload: Partial<{ title: string; date: string; description: string }>,
  ) => mapEvent(await api.patch<RawEvent>(`/events/${id}`, payload)),

  uploadCover: async (id: number | string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return mapEvent(await api.post<RawEvent>(`/events/${id}/cover`, form))
  },

  uploadPhotos: async (id: number | string, files: File[]) => {
    const form = new FormData()
    for (const file of files) form.append('files', file)
    const raw = await api.post<RawEventPhoto[]>(`/events/${id}/photos`, form)
    return raw.map(mapPhoto)
  },
}
