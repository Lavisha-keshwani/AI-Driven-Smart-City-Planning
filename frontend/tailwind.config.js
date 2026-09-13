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
        // Suitability and risk classes. Chosen to stay distinguishable against
        // the dark ground and for the common forms of colour-vision deficiency:
        // they differ in lightness as well as hue, and every map layer also
        // carries a text label so colour is never the only signal.
        suitable: {
          DEFAULT: '#3FBF7F',
          light: '#6FD9A2',
        },
        conditional: {
          DEFAULT: '#E3A93C',
          light: '#F0C571',
        },
        avoid: {
          DEFAULT: '#E2583E',
          light: '#F0836D',
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

