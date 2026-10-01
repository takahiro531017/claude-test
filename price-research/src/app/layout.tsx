import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = { title: "家電 競合価格調査", description: "家電の価格・発売時期・競合を比較する社内ツール" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body className="bg-slate-50 text-slate-900 antialiased">
        <header className="border-b bg-white">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-4 py-3 text-sm">
            <Link href="/" className="font-bold">家電 競合価格調査</Link>
            <Link href="/history" className="text-slate-600 hover:underline">履歴</Link>
          </nav>
        </header>
        <div className="border-b border-amber-300 bg-amber-50 px-4 py-2 text-center text-xs text-amber-900">
          開発フェーズ1：表示はすべて架空のモックデータです。実在の商品・価格ではありません。
        </div>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
