// Accept only a path on this site. Anything that would leave it falls back
export function safeNext(raw: unknown, fallback = "/profile"): string {
  if (typeof raw !== "string" || !raw.startsWith("/")) return fallback;

  // Let the URL parser decide, it applies the same quirks as a browser
  // (strips tabs, treats "\" as "/"), so "//evil.com" and "/\evil.com" are caught too
  const base = "http://localhost";
  try {
    const url = new URL(raw, base);
    return url.origin === base
      ? url.pathname + url.search + url.hash
      : fallback;
  } catch {
    return fallback;
  }
}
