// Shared with the backend's gated-fields list (see
// app/services/profile_completeness_service.py) — human labels for the
// "missing_fields" list shown wherever profile completeness gates a view
// (rating, leaderboard, public profile). Keep in one place: this list already
// drifted out of sync once when duplicated per-page.
export const FIELD_LABELS: Record<string, string> = {
  birthday: 'дата рождения',
  avatar: 'фото на аватар',
  city: 'город',
  gender: 'пол',
  phone: 'телефон',
  running_club: 'беговой клуб',
  prior_experience: 'бегали ли вы раньше с DАЙ ХАРD',
  email_verified: 'подтверждение почты',
  // Only ever appear for runners under 14 (see MINOR_AGE) — parent contacts.
  parent_first_name: 'имя родителя',
  parent_last_name: 'фамилия родителя',
  parent_phone: 'телефон родителя',
}
