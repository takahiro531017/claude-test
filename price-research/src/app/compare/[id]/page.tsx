import Link from "next/link";
import { notFound } from "next/navigation";
import { getCatalog, getProduct } from "@/lib/search";
import { UNAVAILABLE, dateJa, yen } from "@/lib/format";
import { summarize } from "@/lib/pricing";

export default async function ComparePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const base = getProduct(id);
  if (!base) notFound();
  // Phase 1 の暫定: 同カテゴリのみ。価格帯±20%・スペック近接度は Phase 4 で実装する。
  const rivals = getCatalog().filter((p) => p.id !== base.id && p.categoryId === base.categoryId);
  const rows = [base, ...rivals];

  return (
    <div className="space-y-4">
      <Link href={`/product/${base.id}`} className="text-sm text-blue-700 underline">← 商品詳細へ</Link>
      <h1 className="text-xl font-bold">競合比較: {base.modelNumber}</h1>
      <p className="text-sm text-slate-500">暫定表示（同カテゴリのみ）。価格帯 ±20% 抽出・差分ハイライト・ポジショニングマップは Phase 4 で実装します。</p>
      <div className="overflow-x-auto rounded border bg-white p-4">
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left text-slate-500"><tr><th>メーカー</th><th>型番</th><th>発売</th><th>最安</th><th>メーカー希望</th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id} className={`border-t ${p.id === base.id ? "bg-amber-50" : ""}`}>
                <td>{p.manufacturerName}</td>
                <td>{p.modelNumber}{p.id === base.id && "（検索商品）"}</td>
                <td>{dateJa(p.releaseDate)}</td>
                <td>{yen(summarize(p.prices).min)}</td>
                <td>{yen(p.prices.find((r) => r.kind === "list")?.amount ?? null)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {rivals.length === 0 && <p className="mt-2 text-sm">{UNAVAILABLE}: 競合候補なし</p>}
      </div>
    </div>
  );
}
