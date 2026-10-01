import Link from "next/link";
import { notFound } from "next/navigation";
import { getProduct } from "@/lib/search";
import { KIND_LABEL, UNAVAILABLE, dateJa, dateTimeJa, yen } from "@/lib/format";
import { effectivePrice, summarize } from "@/lib/pricing";

export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const p = getProduct(id);
  if (!p) notFound();
  const s = summarize(p.prices);

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-700 underline">← 検索へ</Link>
        <h1 className="mt-2 text-xl font-bold">{p.modelNumber} <span className="text-base font-normal">{p.name}</span></h1>
        <p className="text-sm text-slate-600">{p.manufacturerName} ／ {p.categoryName}</p>
      </div>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-2 font-semibold">発売時期</h2>
        <p>発売日: {dateJa(p.releaseDate)}（出典: {p.releaseSource ?? UNAVAILABLE}）</p>
        <p className="text-sm text-slate-500">生産終了・後継機・モデルチェンジ周期: {UNAVAILABLE}（Phase 3 で対応）</p>
      </section>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-2 font-semibold">価格サマリー（新品）</h2>
        <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
          <div><dt className="text-slate-500">最安</dt><dd>{yen(s.min)}</dd></div>
          <div><dt className="text-slate-500">平均</dt><dd>{yen(s.avg)}</dd></div>
          <div><dt className="text-slate-500">最高</dt><dd>{yen(s.max)}</dd></div>
          <div><dt className="text-slate-500">取得元数</dt><dd>{s.count}</dd></div>
        </dl>
      </section>

      <section className="overflow-x-auto rounded border bg-white p-4">
        <h2 className="mb-2 font-semibold">価格一覧（取得元別）</h2>
        <table className="w-full min-w-[720px] text-sm">
          <thead className="text-left text-slate-500">
            <tr><th>種別</th><th>取得元</th><th>価格</th><th>税</th><th>送料</th><th>ポイント</th><th>実質価格</th><th>取得日時</th><th>URL</th></tr>
          </thead>
          <tbody>
            {p.prices.map((r, i) => (
              <tr key={i} className="border-t">
                <td>{KIND_LABEL[r.kind]}</td>
                <td>{r.sourceName}</td>
                <td>{yen(r.amount)}</td>
                <td>{r.taxIncluded === null ? UNAVAILABLE : r.taxIncluded ? "税込" : "税抜"}</td>
                <td>{yen(r.shipping)}</td>
                <td>{yen(r.pointBack)}</td>
                <td>{yen(effectivePrice(r))}</td>
                <td>{dateTimeJa(r.fetchedAt)}</td>
                <td><a className="text-blue-700 underline" href={r.url} target="_blank" rel="noreferrer">開く</a></td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-500">価格推移・セール/クーポン・法人価格・レンタル: {UNAVAILABLE}（Phase 2〜3 で対応）</p>
      </section>

      <section className="rounded border bg-white p-4">
        <h2 className="mb-2 font-semibold">主要スペック</h2>
        <dl className="grid gap-1 text-sm sm:grid-cols-2">
          {Object.entries(p.specs).map(([k, v]) => (
            <div key={k} className="flex gap-2"><dt className="w-32 text-slate-500">{k}</dt><dd>{v ?? UNAVAILABLE}</dd></div>
          ))}
        </dl>
      </section>

      <Link href={`/compare/${p.id}`} className="inline-block rounded bg-slate-900 px-4 py-2 text-white">競合比較へ</Link>
    </div>
  );
}
