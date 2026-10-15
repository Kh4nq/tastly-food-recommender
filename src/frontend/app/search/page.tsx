import SearchPageContent from "@/components/search/SearchPageContent";
import SearchScrollArea from "@/components/search/SearchScrollArea";

export default async function SearchPage({ searchParams }: PageProps<"/search">) {
  const params = await searchParams;
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    for (const entry of Array.isArray(value) ? value : value === undefined ? [] : [value]) query.append(key, entry);
  }
  return <SearchScrollArea><SearchPageContent query={query.toString()} /></SearchScrollArea>;
}
