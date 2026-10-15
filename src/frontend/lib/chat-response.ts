import type { SearchResponse } from "./api";
import type { Dict } from "./i18n";
import { resultGroups } from "./search-results";

export function searchReply(response: SearchResponse, chat: Dict["chat"]): string {
  // Generated replies are authoritative for ordinary conversation, without
  // replaying warnings from the previous search or implying a retrieval ran.
  if (response.intent === "conversation" || response.intent === "informational") {
    return response.assistant_message?.trim() || chat.searchClarification;
  }
  let reply: string;
  if (response.retrieval_deferred) reply = chat.searchDeferred;
  else if (response.clarification_required || response.intent === "clarification") reply = chat.searchClarification;
  else {
    const groups = resultGroups(response.results);
    const primary = groups.primary.filter((r) => r.recommendation_group === "primary").length;
    if (primary) reply = chat.searchFound(primary);
    else if (groups.primary.length) reply = chat.searchFoundGeneral(groups.primary.length);
    else if (groups.supplementary.length) reply = chat.searchAlternatives(groups.supplementary.length);
    else reply = chat.searchEmpty;
  }
  // Full evidence warnings remain on the results page. Keep unverified sides,
  // allergies and other actionable warnings here, without repeating raw labels.
  const important = (warning: string) => /món kèm|accompaniment|dị ứng|allerg/i.test(warning);
  const warnings = [...new Set(response.warnings ?? [])].filter((warning) =>
    important(warning) ||
    !/^(?:Chưa có dữ liệu xác minh cho một số kết quả:|Một số kết quả không khớp ưu tiên:|Chưa đối chiếu được yêu cầu tránh:|Khoảng cách là khoảng cách địa lý,)/.test(warning),
  ).filter((warning) => warning.trim())
    .sort((a, b) => Number(important(b)) - Number(important(a)))
    .slice(0, 2).map((warning) => warning.length > 300 ? warning.slice(0, 297) + "…" : warning);
  return [reply, ...warnings].join("\n");
}
