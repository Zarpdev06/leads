/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eef4ff', 100: '#d9e4ff', 200: '#bccdff', 300: '#8eaaff',
          400: '#597dff', 500: '#3454f5', 600: '#2035e0', 700: '#1a29b5',
          800: '#1b2691', 900: '#1c2772',
        },
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,0.05), 0 1px 3px rgba(16,24,40,0.08)',
      },
      keyframes: {
        'fade-in': { '0%': { opacity: 0, transform: 'translateY(4px)' }, '100%': { opacity: 1, transform: 'none' } },
      },
      animation: { 'fade-in': 'fade-in 0.18s ease-out' },
    },
  },
  plugins: [],
}
