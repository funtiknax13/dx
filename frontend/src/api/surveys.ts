import { api } from './client'
import type { Survey } from '../types'

export const surveysApi = {
  active: (): Promise<Survey | null> => api.get<Survey | null>('/surveys/active'),

  submit: (surveyId: number, answers: { question_id: number; value: string }[]) =>
    api.post<{ detail: string }>(`/surveys/${surveyId}/responses`, { answers }),
}
