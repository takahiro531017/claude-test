import { defineConfig } from '@playwright/test'

// 実バックエンドは使わず、Supabase の API をブラウザ側でモックして画面の主要フローを検証する。
// (RLS/権限そのものは DB テスト `npm run test:db` で実機検証している)
// ブラウザの場所を変えたい環境では PW_CHROMIUM=/path/to/chrome を指定する
export default defineConfig({
  testDir: 'e2e',
  timeout: 30_000,
  fullyParallel: true,
  use: {
    baseURL: 'http://127.0.0.1:4173',
    launchOptions: { executablePath: process.env.PW_CHROMIUM || undefined },
    trace: 'off',
  },
  webServer: {
    command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: { VITE_SUPABASE_URL: 'http://127.0.0.1:54321', VITE_SUPABASE_ANON_KEY: 'test-anon-key' },
  },
})
