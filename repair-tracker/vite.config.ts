/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: { sourcemap: false },
  test: {
    // Edge Function のURLインポートをテスト用の偽物に差し替える
    alias: { 'https://esm.sh/@supabase/supabase-js@2.117.3': new URL('./tests/fakes/supabase.ts', import.meta.url).pathname }, environment: 'jsdom', include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx', 'src/**/*.test.ts', 'src/**/*.test.tsx'] },
})
