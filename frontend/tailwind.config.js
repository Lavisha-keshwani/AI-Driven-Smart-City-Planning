/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#0D1B1E',
          light: '#142B2E',
          lighter: '#1B383C',
        },
        water: {
          DEFAULT: '#4CC9C0',
          bright: '#7EE8DC',
          dim: '#2C6E68',
        },
        earth: {
          DEFAULT: '#C08B3F',
          light: '#E0B370',
          dim: '#6B4F26',
        },
        alert: {
          DEFAULT: '#E2583E',
          light: '#F0836D',
        },
        mist: {
          DEFAULT: '#EAF4F2',
          muted: '#8FA8A6',
          faint: '#4A6260',
        },
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"Inter"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}

