import Link from "next/link";
import { searchProducts } from "@/lib/search";
import { yen } from "@/lib/format";
import { summarize } from "@/lib/pricing";

const KIND_LABEL = { model: "品番", maker: "メーカー名", keyword: "商品名・キーワード" } as const;

export default async function Home({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q = "" } = await searchParams;
  const result = q.trim() ? searchProducts(q) : null;

  return (
    <div className="space-y-6">
      <form action="/" method="get" className="flex gap-2">
        <input
          name="q"
          defaultValue={q}
          placeholder="品番・メーカー名・商品名（例: SE-WD100 / サンプル電機 洗濯機 / ドラム式洗濯乾燥機）"
          className="flex-1 rounded border border-slate-300 bg-white px-3 py-2"
          aria-label="検索キーワード"
        />
        <button className="rounded bg-slate-900 px-4 py-2 text-white">検索</button>
      </form>

      {result && (
        <section className="space-y-3">
          <p className="text-sm text-slate-600">
            判定: <b>{KIND_LABEL[result.query.kind]}</b>
            {result.query.manufacturerId && <> ／ メーカー: {result.query.manufacturerId}</>}
            {result.query.categoryId && <> ／ カテゴリ: {result.query.categoryId}</>}
            {result.query.modelKeys.length > 0 && <> ／ 品番キー: {result.query.modelKeys.join(", ")}</>}
          </p>
          {result.candidates.length === 0 ? (
            <p className="rounded border bg-white p-4">該当する商品が見つかりませんでした。</p>
          ) : (
            <ul className="grid gap-3 sm:grid-cols-2">
              {result.candidates.map(({ product: p, reason }) => (
                <li key={p.id} className="rounded border bg-white p-4">
                  <div className="text-xs text-slate-500">{p.manufacturerName} ／ {p.categoryName}</div>
                  <div className="font-semibold">{p.modelNumber}</div>
                  <div className="text-sm">{p.name}</div>
                  <div className="mt-1 text-sm text-slate-600">最安（新品）: {yen(summarize(p.prices).min)}</div>
                  <div className="text-xs text-slate-400">{reason}</div>
                  <div className="mt-2 flex gap-3 text-sm">
                    <Link className="text-blue-700 underline" href={`/product/${p.id}`}>詳細</Link>
                    <Link className="text-blue-700 underline" href={`/compare/${p.id}`}>競合比較</Link>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
