/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // DAI HARD — black-to-white through gray, no hue at all. Poster-grade
        // monochrome: paper is the lightest stop, ink the darkest.
        paper: {
          DEFAULT: '#F6F6F5',
          soft: '#EBEBE9',
          deep: '#DCDCD9',
        },
        ink: {
          DEFAULT: '#0E0E0D',
          800: '#1B1B19',
          700: '#292927',
          600: '#4C4C48',
        },
        // "signal" — the primary interactive tone. Was finish-line orange; now a
        // dense charcoal that reads as deliberate accent/action against both
        // paper and ink, without introducing a hue.
        signal: {
          DEFAULT: '#2E2E2B',
          600: '#181816',
          soft: '#55554F',
          wash: '#E7E7E4',
        },
        // "volt" — the flash tone, used sparingly on ink surfaces (eyebrow
        // labels, stat call-outs). Was lime; now near-white for maximum pop
        // against black rather than maximum saturation.
        volt: {
          DEFAULT: '#F7F7F5',
          deep: '#C4C4C0',
        },
        clay: '#87857F',
      },
      fontFamily: {
        display: ['Unbounded', 'system-ui', 'sans-serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
      letterSpacing: {
        tightest: '-0.04em',
      },
      borderRadius: {
        xl2: '1.25rem',
      },
      boxShadow: {
        card: '0 1px 0 0 rgba(14,14,13,0.05), 0 12px 32px -18px rgba(14,14,13,0.4)',
        lift: '0 20px 50px -24px rgba(14,14,13,0.55)',
      },
      keyframes: {
        'fade-up': {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        marquee: {
          '0%': { transform: 'translateX(0)' },
          '100%': { transform: 'translateX(-50%)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.6s cubic-bezier(0.16,1,0.3,1) both',
        'fade-in': 'fade-in 0.5s ease both',
        marquee: 'marquee 22s linear infinite',
      },
    },
  },
  plugins: [],
}
