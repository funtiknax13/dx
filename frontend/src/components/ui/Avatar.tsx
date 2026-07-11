import { media } from '../../api/client'
import { initials } from '../../lib/format'

interface AvatarProps {
  first?: string
  last?: string
  src?: string | null
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

const sizeMap = {
  sm: 'h-8 w-8 text-[0.65rem]',
  md: 'h-11 w-11 text-sm',
  lg: 'h-16 w-16 text-lg',
  xl: 'h-24 w-24 text-2xl sm:h-28 sm:w-28',
}

export function Avatar({ first, last, src, size = 'md', className = '' }: AvatarProps) {
  const url = media(src)
  return (
    <div
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full bg-ink font-display font-semibold text-volt ring-1 ring-ink/10 ${sizeMap[size]} ${className}`}
    >
      {url ? (
        <img src={url} alt="" className="h-full w-full object-cover" loading="lazy" />
      ) : (
        <span className="tracking-tight">{initials(first, last)}</span>
      )}
    </div>
  )
}
