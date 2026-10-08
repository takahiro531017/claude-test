// Edge Functions を Node の tsc で型検査するための最小定義(実行時は Deno 本体が提供する)
declare const Deno: {
  serve(handler: (req: Request) => Response | Promise<Response>): void
  env: { get(key: string): string | undefined }
}
