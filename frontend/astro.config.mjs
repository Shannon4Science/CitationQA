import { defineConfig } from 'astro/config';
import react from '@astrojs/react';
import tailwind from '@astrojs/tailwind';

const base = process.env.ASTRO_BASE || '/';

export default defineConfig({
  integrations: [
    react(),
    tailwind(),
  ],
  output: 'static',
  base,
});
