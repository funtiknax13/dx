/** Yandex Maps uses lon,lat order in the `pt` query param. */
export function yandexMapsUrl(lat: number, lng: number): string {
  return `https://yandex.ru/maps/?pt=${lng},${lat},pm2rdm&z=16&l=map`
}
