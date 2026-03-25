/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,md,mdx,svelte,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        'neo-black': '#111111',
        'neo-parchment': '#F4F0EB',
        'neo-dark': '#1E1E1E',
        'neo-sage': '#8A9A86',
        'neo-mustard': '#D9B756',
        'neo-blue': '#7B8B9E',
      },
      fontFamily: {
        serif: ['Fraunces', 'serif'],
        mono: ['IBM Plex Mono', 'monospace'],
        sans: ['IBM Plex Sans', 'sans-serif'],
      },
      borderRadius: {
        DEFAULT: '0px',
        sm: '0px',
        md: '0px',
        lg: '0px',
        xl: '0px',
        '2xl': '0px',
        '3xl': '0px',
        full: '0px',
      },
      borderWidth: {
        thick: '2px',
        thin: '1px',
      },
    },
  },
  plugins: [],
};
