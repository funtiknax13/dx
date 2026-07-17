import badge25 from '../assets/achievements/badge-25.png'
import badge50 from '../assets/achievements/badge-50.png'
import badge100 from '../assets/achievements/badge-100.png'
import badge150 from '../assets/achievements/badge-150.png'
import badge200 from '../assets/achievements/badge-200.png'

// Artwork only exists for some milestones so far — thresholds without an
// entry (e.g. 250/300) fall back to a plain numbered circle wherever this
// is used.
export const ACHIEVEMENT_BADGE_IMAGES: Record<number, string> = {
  25: badge25,
  50: badge50,
  100: badge100,
  150: badge150,
  200: badge200,
}
