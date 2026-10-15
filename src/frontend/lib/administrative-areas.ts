import entries from "./administrative-areas.json";

// Post-merger 2025 administrative boundaries, already present in the AI1 data.
// Coordinates are representative points inside each polygon, not street addresses.
// Name references:
// https://tphcm.chinhphu.vn/danh-sach-chinh-thuc-168-phuong-xa-cua-tphcm-sau-sap-xep-101250617000144317.htm
// https://hanoi.gov.vn/bo-may-chinh-quyen-thanh-pho-ha-noi
export const CURRENT_ADMIN_AREAS = entries.map((area) => ({
  ...area,
  address: `${area.fullName}, ${area.cityId === "hcm" ? "TP. Hồ Chí Minh" : "Hà Nội"} (điểm đại diện khu vực)`,
  shortLabel: `${area.name}, ${area.cityId === "hcm" ? "TP.HCM" : "Hà Nội"}`,
  source: "manual" as const,
}));
