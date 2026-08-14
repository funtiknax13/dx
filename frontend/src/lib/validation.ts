// Shared field validation for the auth forms (register / login / reset). Every
// rule here is mirrored on the backend (app/schemas/auth.py) — the frontend
// copy is purely for instant, friendly feedback, never the source of truth.

/** Uppercase just the first character (names are stored/displayed capitalised).
 * Locale-aware so Cyrillic folds correctly; leaves the rest of the string as
 * typed (so "анна-мария" -> "Анна-мария", not "Анна-Мария"). */
export function capitalizeFirst(value: string): string {
  if (!value) return value
  return value.charAt(0).toLocaleUpperCase('ru-RU') + value.slice(1)
}

/** Name must be non-empty and contain no digits. Otherwise permissive (letters
 * of any script, spaces, hyphens, apostrophes for names like «О'Коннор»).
 * `requiredMsg` is the caller's "fill this in" text (grammatical gender differs
 * between имя/фамилия, so it's passed in rather than built here). */
export function nameError(value: string, requiredMsg: string): string | null {
  const v = value.trim()
  if (!v) return requiredMsg
  if (/\d/.test(v)) return 'Не используйте цифры'
  return null
}

export function emailError(value: string): string | null {
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value.trim())) return 'Некорректный email'
  return null
}

/** Password: 8–128 chars, Latin letters + digits + standard symbols only (no
 * Cyrillic, no spaces), and must include at least one Latin letter and one
 * digit. Returns the first failing rule's message, or null when valid. */
export function passwordError(value: string): string | null {
  if (value.length < 8) return 'Минимум 8 символов'
  if (value.length > 128) return 'Не более 128 символов'
  // Printable ASCII excluding space (0x21–0x7E) — rejects Cyrillic and spaces.
  if (!/^[!-~]+$/.test(value)) return 'Только латинские буквы, цифры и символы'
  if (!/[A-Za-z]/.test(value)) return 'Добавьте хотя бы одну латинскую букву'
  if (!/\d/.test(value)) return 'Добавьте хотя бы одну цифру'
  return null
}
