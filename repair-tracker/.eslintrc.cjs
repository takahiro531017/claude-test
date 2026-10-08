module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended', 'plugin:react-hooks/recommended'],
  env: { browser: true, es2022: true },
  ignorePatterns: ['dist', 'node_modules', 'supabase/functions/**'],
  rules: {
    // 個人情報の漏洩防止: console出力とlocalStorage/sessionStorage直接利用を禁止
    'no-console': 'error',
    'no-restricted-globals': ['error', 'localStorage', 'sessionStorage'],
    'no-restricted-properties': ['error',
      { object: 'window', property: 'localStorage' }, { object: 'window', property: 'sessionStorage' }],
    '@typescript-eslint/no-explicit-any': 'error',
  },
  overrides: [
    // テストはストレージ/コンソールに個人情報が残っていないことを検査するため参照を許可
    { files: ['e2e/**', 'tests/**'], rules: { 'no-restricted-globals': 'off', 'no-console': 'off' } },
  ],
}
