import type { Text } from "@/lib/i18n";
import type { Location } from "@/lib/api";

// Mock city -> district data, replace with API data when backend is ready.
// City id is language independent, it is what goes into the URL (?city=hcm)
export const CITIES: { id: string; name: Text; districts: string[] }[] = [
  {
    id: "hcm",
    name: { vi: "TP. Hồ Chí Minh", en: "Ho Chi Minh City" },
    districts: [
      "Quận 1",
      "Quận 3",
      "Quận 5",
      "Bình Thạnh",
      "Phú Nhuận",
      "Thủ Đức",
    ],
  },
  {
    id: "hn",
    name: { vi: "Hà Nội", en: "Hanoi" },
    districts: ["Hoàn Kiếm", "Ba Đình", "Đống Đa", "Hai Bà Trưng", "Cầu Giấy"],
  },
];

// Center point of each city, used when no district is picked
const CITY_CENTERS: Record<string, Location> = {
  hcm: { lat: 10.7769, lon: 106.7009 },
  hn: { lat: 21.0285, lon: 105.8542 },
};

// Center point of each district, keyed by the same names as CITIES
const DISTRICT_CENTERS: Record<string, Location> = {
  "Quận 1": { lat: 10.7769, lon: 106.7009 },
  "Quận 3": { lat: 10.7843, lon: 106.6844 },
  "Quận 5": { lat: 10.754, lon: 106.6634 },
  "Bình Thạnh": { lat: 10.8106, lon: 106.7091 },
  "Phú Nhuận": { lat: 10.7991, lon: 106.6803 },
  "Thủ Đức": { lat: 10.8494, lon: 106.7537 },
  "Hoàn Kiếm": { lat: 21.0285, lon: 105.8542 },
  "Ba Đình": { lat: 21.034, lon: 105.8142 },
  "Đống Đa": { lat: 21.018, lon: 105.827 },
  "Hai Bà Trưng": { lat: 21.006, lon: 105.857 },
  "Cầu Giấy": { lat: 21.033, lon: 105.794 },
};

// District wins over city; undefined when nothing is picked
export function coordOf(city: string, district = ""): Location | undefined {
  return DISTRICT_CENTERS[district] ?? CITY_CENTERS[city];
}
