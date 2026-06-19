/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          900: '#0D1117',
          800: '#161B22',
          700: '#1C2128',
          600: '#21262D',
          500: '#30363D',
        },
        clay: {
          600: '#A14A2A',
          500: '#C05621',
          400: '#DD6B20',
          300: '#ED8936',
        },
        muted: '#8B949E',
        faint: '#6E7681',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
