import { api } from './client'
import type { FinishStatus, ModerationStatus } from '../types'

export interface UnmatchedRecord {
  attendance_id: number
  full_name: string
  email?: string | null
  phone?: string | null
  group_id: number
  group_name: string
  event_title: string
  suggested_runner_id?: number | null
  suggested_runner_name?: string | null
}

export interface ResultData {
  attendance_id: number
  distance_km: number
  duration_seconds: number
  pace_seconds_per_km?: number | null
  finish_status: FinishStatus
  moderation_status: ModerationStatus
  source: 'file' | 'manual'
  has_track?: boolean
}

// Raw shapes as actually returned by the backend (see backend/app/schemas/attendance.py
// and result.py) — kept private to this module.
interface RawUnmatchedRecord {
  id: number
  group_id: number
  raw_name: string
  raw_email: string | null
  raw_phone: string | null
}

interface RawResult {
  attendance_record_id: number
  distance_km: number
  duration_seconds: number
  pace_seconds_per_km: number | null
  finish_status: string
  status: string
  source: string
  track_points: unknown[] | null
}

function mapUnmatched(raw: RawUnmatchedRecord): UnmatchedRecord {
  return {
    attendance_id: raw.id,
    full_name: raw.raw_name,
    email: raw.raw_email,
    phone: raw.raw_phone,
    group_id: raw.group_id,
    group_name: '',
    event_title: '',
  }
}

function mapResult(raw: RawResult): ResultData {
  return {
    attendance_id: raw.attendance_record_id,
    distance_km: raw.distance_km,
    duration_seconds: raw.duration_seconds,
    pace_seconds_per_km: raw.pace_seconds_per_km,
    finish_status: raw.finish_status as FinishStatus,
    moderation_status: raw.status as ModerationStatus,
    source: raw.source as 'file' | 'manual',
    has_track: Boolean(raw.track_points?.length),
  }
}

export const attendanceApi = {
  // Admin-only
  importCsv: (eventId: number | string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{
      created: number
      skipped_duplicates: number
      skipped_empty: number
      skipped_no_tag: number
      skipped_unmatched_tag: number
      fallback_used: boolean
    }>(`/events/${eventId}/attendance/import-csv`, form)
  },
  unmatched: async () => {
    const raw = await api.get<RawUnmatchedRecord[]>('/attendance/unmatched')
    return raw.map(mapUnmatched)
  },
  match: (attendanceId: number | string, runner_id: number) =>
    api.post<{ message?: string }>(`/attendance/${attendanceId}/match`, { runner_id }),

  // Results
  getResult: async (attendanceId: number | string) =>
    mapResult(await api.get<RawResult>(`/attendance/${attendanceId}/result`)),

  submitResultFile: async (attendanceId: number | string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return mapResult(await api.post<RawResult>(`/attendance/${attendanceId}/result`, form))
  },

  // Backend expects manual entry as multipart Form fields on the same endpoint as
  // the file upload (not a JSON body) — see backend/app/api/results.py.
  submitResultManual: async (
    attendanceId: number | string,
    payload: { distance_km: number; duration_seconds: number; start_time?: string },
  ) => {
    const form = new FormData()
    form.append('distance_km', String(payload.distance_km))
    form.append('duration_seconds', String(Math.round(payload.duration_seconds)))
    if (payload.start_time) form.append('start_time', payload.start_time)
    return mapResult(await api.post<RawResult>(`/attendance/${attendanceId}/result`, form))
  },
}
