import { ApiError } from "./api";
import type { Dict } from "./i18n";

// Turn any thrown value into a translated sentence. Never shows the server's raw message
export function errorText(t: Dict, e: unknown): string {
  const code = e instanceof ApiError ? e.code : "unknown";
  const table = t.errors as Record<string, string>;
  return table[code] ?? t.errors.unknown;
}
