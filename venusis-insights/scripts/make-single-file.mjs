// 使い方: npm run build && node scripts/make-single-file.mjs <出力先.html>
// dist/ の CSS・JS を1つのHTMLに埋め込む（外部ファイルなしで配れる形）。
// 出力は <html><head><body> を含まない断片（埋め込み先が骨組みを付ける想定）。
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';

const out = process.argv[2] ?? 'venusis-insights.single.html';
const assets = readdirSync('dist/assets');
const css = readFileSync('dist/assets/' + assets.find((f) => f.endsWith('.css')), 'utf8');
const js = readFileSync('dist/assets/' + assets.find((f) => f.endsWith('.js')), 'utf8').replace(/<\/script/gi, '<\\/script');
const html = readFileSync('dist/index.html', 'utf8');
const body = html.match(/<body>([\s\S]*?)<\/body>/)[1].replace(/<script[^>]*src=[^>]*><\/script>/g, '');
writeFileSync(out, `<title>VENUSiS 運用レポート</title>\n<style>\n${css}\n</style>\n${body}\n<script type="module">\n${js}\n</script>\n`);
console.log('wrote', out);
