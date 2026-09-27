export function runFromSearch(search: string): { runId: string | null; error: string } {
  const params = new URLSearchParams(search);
  if (!params.has("run")) return { runId: null, error: "" };
  const value = params.get("run") ?? "";
  return params.getAll("run").length === 1 && /^run-[a-zA-Z0-9-]{1,80}$/.test(value)
    ? { runId: value, error: "" }
    : { runId: null, error: "올바르지 않은 실행 주소입니다." };
}

export function runUrl(href: string, runId: string): string {
  const url = new URL(href);
  url.searchParams.set("run", runId);
  return url.href;
}
