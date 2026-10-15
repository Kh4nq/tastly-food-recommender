import { cookies } from "next/headers";
import { CITIES } from "./locations";
import { parseLocationCookie } from "./search-location";

export async function getLocation() {
  const value = (await cookies()).get("loc")?.value ?? "";
  const selected = parseLocationCookie(value);
  let decoded = "";
  try { decoded = decodeURIComponent(value); } catch { /* Ignore invalid cookies. */ }
  const [legacyCity, legacyDistrict] = decoded.split("|");
  const city = legacyCity === "current" && selected ? "current" : CITIES.some((entry) => entry.id === legacyCity) ? legacyCity : "";
  const district = CITIES.find((entry) => entry.id === city)?.districts.includes(legacyDistrict) ? legacyDistrict : "";
  return { selected, city, district, coord: selected ? { lat: selected.lat, lon: selected.lon } : undefined };
}
