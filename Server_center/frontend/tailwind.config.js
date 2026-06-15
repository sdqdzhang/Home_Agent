/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: '#0f1117',
          raised: '#171a23',
          border: '#2a2f3d',
        },
        agent: {
          bubble: '#2d3344',
          user: '#4f46e5',
        },
      },
      width: {
        sidebar: '300px',
      },
      transitionProperty: {
        panel: 'transform, opacity',
      },
    },
  },
  plugins: [],
}
