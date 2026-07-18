/** Yandex Maps uses lon,lat order in both `ll` and `pt`. `ll` (map center) is
 * required alongside `pt` (the pin) — without it Yandex doesn't reliably
 * center on the given point and can fall back to the viewer's own geolocation
 * instead. */
export function yandexMapsUrl(lat: number, lng: number): string {
  return `https://yandex.ru/maps/?ll=${lng},${lat}&z=16&pt=${lng},${lat},pm2rdm&l=map`
}
