import { NextRequest, NextResponse } from "next/server";
import { searchProducts } from "@/lib/search";

export function GET(req: NextRequest) {
  const q = req.nextUrl.searchParams.get("q") ?? "";
  if (q.length > 200) return NextResponse.json({ error: "クエリが長すぎます" }, { status: 400 });
  return NextResponse.json(searchProducts(q));
}
