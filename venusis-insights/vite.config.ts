import { defineConfig } from 'vitest/config';

// base を './' にすることで、Vercel / Netlify / GitHub Pages（サブパス）のどれでも動く
export default defineConfig({
  base: './',
  build: { target: 'es2020', chunkSizeWarningLimit: 600 },
  test: { environment: 'node' },
});
