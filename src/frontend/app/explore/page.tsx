import SpecialtyCard from "@/components/explore/SpecialtyCard";
import { getT } from "@/lib/i18n-server";
import type {Dict , Text} from "@/lib/i18n";

// A specialty dish, its name is translated per language
type Dish = { name: Text; image: string };

// A region and its dishes (id must match a key in the locale files)
type Region = {id : keyof Dict["explore"]["regions"] ; dishes : Dish[]};

// Mock data: specialties grouped by region (North / Central / South)
const regions: Region[] = [
  {
    id: "mien-bac",
    dishes: [
      { name: { vi: "Phở", en: "Pho" }, image: "/explore/mien_bac/pho.jpg" },
      { name: { vi: "Bún chả", en: "Grilled pork with noodles" }, image: "/explore/mien_bac/bun_cha.webp" },
      { name: { vi: "Bánh cuốn", en: "Steamed rice rolls" }, image: "/explore/mien_bac/banh_cuon_thanh_tri.jpg" },
      { name: { vi: "Chả cá Lã Vọng", en: "La Vong turmeric fish" }, image: "/explore/mien_bac/cha_ca_la_vong.jpg" },
      { name: { vi: "Bánh đa cua", en: "Red crab noodle soup" }, image: "/explore/mien_bac/banh_da_cua.jpg" },
      { name: { vi: "Chả mực Hạ Long", en: "Ha Long squid cakes" }, image: "/explore/mien_bac/cha_muc_ha_long.jpg" },
      { name: { vi: "Cốm làng Vòng", en: "Vong village green rice" }, image: "/explore/mien_bac/xoi_com_lang_vong.jpg" },
      { name: { vi: "Bánh tôm Hồ Tây", en: "West Lake shrimp fritters" }, image: "/explore/mien_bac/banh_tom_ho_tay.jpg" },
    ],
  },
  {
    id: "mien-trung",
    dishes: [
      { name: { vi: "Bún bò Huế", en: "Hue spicy beef noodle soup" }, image: "/explore/mien_trung/bun_bo.webp" },
      { name: { vi: "Mì Quảng", en: "Quang-style noodles" }, image: "/explore/mien_trung/mi_quang.png" },
      { name: { vi: "Cao lầu Hội An", en: "Hoi An cao lau noodles" }, image: "/explore/mien_trung/cao_lau_hoi_an.jpg" },
      { name: { vi: "Bánh bèo Huế", en: "Hue steamed rice cakes" }, image: "/explore/mien_trung/banh_beo_hue.jpg" },
      { name: { vi: "Nem lụi Huế", en: "Hue lemongrass pork skewers" }, image: "/explore/mien_trung/nem_lui_hue.jpg" },
      { name: { vi: "Cơm hến", en: "Baby clam rice" }, image: "/explore/mien_trung/com_hen.jpg" },
      { name: { vi: "Bánh tráng cuốn thịt heo", en: "Pork rice paper rolls" }, image: "/explore/mien_trung/banh_trang_cuon.jpeg" },
      { name: { vi: "Bánh căn", en: "Mini clay-pot pancakes" }, image: "/explore/mien_trung/banh_can.jpg" },
    ],
  },
  {
    id: "mien-nam",
    dishes: [
      { name: { vi: "Cơm tấm", en: "Broken rice" }, image: "/explore/mien_nam/com_tam.jpeg" },
      { name: { vi: "Bánh mì chảo", en: "Banh mi skillet" }, image: "/explore/mien_nam/banh_mi_chao.jpg" },
      { name: { vi: "Bánh xèo", en: "Crispy pancake" }, image: "/explore/mien_nam/banh_xeo.jpg" },
      { name: { vi: "Hủ tiếu Mỹ Tho", en: "My Tho noodle soup" }, image: "/explore/mien_nam/hu_tieu_my_tho.jpg" },
      { name: { vi: "Bánh khọt Vũng Tàu", en: "Vung Tau mini pancakes" }, image: "/explore/mien_nam/banh_khot.jpg" },
      { name: { vi: "Cá lóc nướng trui", en: "Straw-grilled snakehead fish" }, image: "/explore/mien_nam/ca_loc_nuong_trui.jpg" },
      { name: { vi: "Gỏi cá mai Vũng Tàu", en: "Vung Tau raw fish salad" }, image: "/explore/mien_nam/goi_ca_mai.jpg" },
      { name: { vi: "Lẩu mắm", en: "Fermented fish hot pot" }, image: "/explore/mien_nam/lau_mam.jpg" },
    ],
  },
];

// Explore page: one section per region, each with a grid of dish cards
export default async function ExplorePage() {
  const t = await getT();

  return (
    <main className="mx-6 my-10">
      <h1 className="text-2xl font-bold text-ink">{t.explore.title}</h1>
      <p className="mt-1 text-sm text-neutral-500">{t.explore.desc}</p>

      <div className = "mt-6 flex flex-col gap-8">
        {regions.map((r) => {
          const regionName = t.explore.regions[r.id];
          return (
            <section key = {r.id}>
              <h2 className = "text-2xl font-bold text-ink">{regionName}</h2>

              <div className = "mt-3 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {r.dishes.map((dish) => (
                  <SpecialtyCard 
                    key = {dish.image}
                    image = {dish.image}
                    name = {dish.name[t.lang]}
                    region = {regionName}
                  />
                ))}
              </div>
            </section>
          );
        })}
      </div>
      
    </main>
  );
}