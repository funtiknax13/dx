import { api } from './client'
import type { GuestClaim, GuestProfile } from '../types'

// Raw shapes as actually returned by the backend (see backend/app/schemas/guest.py).
interface RawGuest {
  id: number
  first_name: string
  last_name: string
  avatar: string | null
}

interface RawClaim {
  id: number
  guest_user_id: number
  claimant_user_id: number
  status: string
  created_at: string
  decided_at: string | null
  guest?: RawGuest
}

function mapGuest(raw: RawGuest): GuestProfile {
  return { id: raw.id, first_name: raw.first_name, last_name: raw.last_name, avatar_url: raw.avatar }
}

function mapClaim(raw: RawClaim): GuestClaim {
  return {
    id: raw.id,
    guest_user_id: raw.guest_user_id,
    claimant_user_id: raw.claimant_user_id,
    status: raw.status as GuestClaim['status'],
    created_at: raw.created_at,
    decided_at: raw.decided_at,
    guest: raw.guest ? mapGuest(raw.guest) : { id: raw.guest_user_id, first_name: '?', last_name: '' },
  }
}

export const guestsApi = {
  search: async (q: string): Promise<GuestProfile[]> => {
    if (q.trim().length < 2) return []
    const raw = await api.get<RawGuest[]>('/guests', { query: { q } })
    return raw.map(mapGuest)
  },

  claim: async (guestId: number | string): Promise<GuestClaim> =>
    mapClaim(await api.post<RawClaim>(`/guests/${guestId}/claim`)),

  myClaims: async (): Promise<GuestClaim[]> => {
    const raw = await api.get<RawClaim[]>('/guests/me/claims')
    return raw.map(mapClaim)
  },
}
