import {SPIN_CATEGORIES} from "@/components/spin/spinData";
import type {Dict , Text} from "./i18n";

// Folder of the dish images inside /public
const trendingPath = "/trending_section";

export type MockDish = {
    id : string;
    image : string;
    name : Text;
    restaurant : string;
    category : keyof Dict["cat"];
    rating : number;
    reviewCount : number;
    price : number;
    perPiece? : boolean;
    city : string;
    district : string;
};

// Mock data changed by API when backend is ready
export const DISHES : MockDish[] = [
  {
    id: "R12",
    image: `${trendingPath}/pho_thin.jpg`,
    name: { vi: "Phở bò tái chín đặc biệt", en: "Special rare & well-done beef pho" },
    restaurant: "Phở Thìn - Lò Đúc",
    category: "pho-bun",
    rating: 4.9,
    reviewCount: 2841,
    price: 120000,
    city: "hn",
    district: "Hai Bà Trưng",
  },
  {
    id: "R7",
    image: `${trendingPath}/banh_mi_chao.jpg`,
    name: { vi: "Bánh mì chảo đầy đủ", en: "Loaded banh mi skillet" },
    restaurant: "Bánh Mì Hòa Mã - Quận 3",
    category: "banh-man",
    rating: 4.8,
    reviewCount: 1923,
    price: 52000,
    city: "hcm",
    district: "Quận 3",
  },
  {
    id: "R21",
    image: `${trendingPath}/bun_bo_hue.jpg`,
    name: { vi: "Bún bò Huế thập cẩm", en: "Hue spicy beef noodle soup, the works" },
    restaurant: "Bún Bò Huế Nam Giao - Quận 1",
    category: "pho-bun",
    rating: 4.7,
    reviewCount: 5310,
    price: 100000,
    city: "hcm",
    district: "Quận 1",
  },
  {
    id: "R31",
    image: `${trendingPath}/banh_xeo.jpg`,
    name: { vi: "Bánh xèo thường", en: "Classic crispy pancake" },
    restaurant: "Bánh Xèo Ngọc Sơn - Quận 1",
    category: "cuon-banh",
    rating: 4.2,
    reviewCount: 1493,
    price: 90000,
    perPiece: true,
    city: "hcm",
    district: "Quận 1",
  },
];

// Convert a mock dish into the props of DishCard (picks language, builds badge and price)
export function toDishCard (d : MockDish , t : Dict) {
  const emoji = SPIN_CATEGORIES.find((c) => c.id === d.category)?.emoji ?? "";
  return {
    image: d.image,
    name: d.name[t.lang],
    restaurant: d.restaurant,
    badge: `${emoji} ${t.cat[d.category]}`,
    rating: d.rating,
    reviewCount: d.reviewCount,
    price: t.price(d.price) + (d.perPiece ? t.card.perPiece : ""),
  };
}