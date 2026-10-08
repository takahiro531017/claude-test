// Edge Functions を「1関数=1ファイル」にまとめる。Supabase ダッシュボードのエディタに貼り付けるだけで公開できる。
// 出力: supabase/functions-bundled/<関数名>.ts  (supabase/functions/ を変更したら再生成すること)
import { build } from 'esbuild'
import { mkdirSync, writeFileSync } from 'node:fs'

const names = ['pii-write', 'pii-reveal', 'csv-export', 'admin-users']
mkdirSync('supabase/functions-bundled', { recursive: true })
for (const n of names) {
  const r = await build({
    entryPoints: [`supabase/functions/${n}/index.ts`], bundle: true, write: false, format: 'esm', platform: 'neutral',
    target: 'es2022', external: ['https://*'], legalComments: 'none', charset: 'utf8', minify: false,
  })
  const header = `// ${n}: ダッシュボード貼り付け用(自動生成: scripts/bundle-functions.mjs)。直接編集しないこと。\n`
  writeFileSync(`supabase/functions-bundled/${n}.ts`, header + r.outputFiles[0].text)
  console.log(`生成: ${n}.ts (${r.outputFiles[0].text.length} bytes)`)
}
