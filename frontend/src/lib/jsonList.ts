/** Mirrors the backend's contest_service.parse_json_list — an image or
 * multi_select field's value is a JSON-encoded array of strings; a bare
 * non-JSON string is a legacy single value from before either existed. */
export function parseJsonList(value: string | null | undefined): string[] {
  if (!value) return []
  try {
    const data = JSON.parse(value)
    return Array.isArray(data) ? data.map(String) : [value]
  } catch {
    return [value]
  }
}
