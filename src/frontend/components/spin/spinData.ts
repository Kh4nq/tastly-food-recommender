import type {Dict , Text} from "@/lib/i18n";

export type Dish = {name : Text; desc : Text};

export type SpinCategory = {
    id : keyof Dict["cat"];
    emoji : string;
    dishes : Dish[];
};

// Spin animation: 10 dish swaps, 100ms apart (about 1 second in total)
export const SPIN_TICKS = 10;
export const SPIN_TICK_MS = 100;

// Mock data , replace with API call when backend is ready
export const SPIN_CATEGORIES: SpinCategory[] = [
  {
    id: "pho-bun",
    emoji: "🍜",
    dishes: [
      { name: { vi: "Bún bò Huế", en: "Hue spicy beef noodle soup" },
        desc: { vi: "Quán đông khách buổi tối, đặt bàn trước 30 phút.", en: "Busy in the evening, book a table 30 minutes ahead." } },
      { name: { vi: "Phở bò tái", en: "Rare beef pho" },
        desc: { vi: "Nước dùng đậm đà, ninh xương nhiều giờ.", en: "Rich broth simmered from bones for hours." } },
      { name: { vi: "Phở gà", en: "Chicken pho" },
        desc: { vi: "Thanh nhẹ hơn phở bò, hợp ăn sáng.", en: "Lighter than beef pho, great for breakfast." } },
      { name: { vi: "Bún riêu cua", en: "Crab noodle soup" },
        desc: { vi: "Vị chua thanh, ngon nhất lúc còn nóng.", en: "Light and tangy, best eaten piping hot." } },
    ],
  },
  {
    id: "com-xoi",
    emoji: "🍚",
    dishes: [
      { name: { vi: "Cơm tấm sườn", en: "Broken rice with grilled pork chop" },
        desc: { vi: "Sườn nướng thơm, cơm dẻo, đủ chất cho bữa trưa.", en: "Fragrant grilled pork and soft rice, a filling lunch." } },
      { name: { vi: "Cơm gà xối mỡ", en: "Crispy fried chicken rice" },
        desc: { vi: "Da gà giòn rụm, ăn kèm cơm mỡ hành.", en: "Crispy chicken skin with scallion-oil rice." } },
      { name: { vi: "Xôi mặn", en: "Savory sticky rice" },
        desc: { vi: "No lâu, hợp ăn sáng mang đi.", en: "Keeps you full for long, great breakfast to go." } },
      { name: { vi: "Cơm chiên dương châu", en: "Yangzhou fried rice" },
        desc: { vi: "Nhiều topping, hợp ăn nhóm chia phần.", en: "Loaded with toppings, great for sharing." } },
    ],
  },
  {
    id: "banh-man",
    emoji: "🥪",
    dishes: [
      { name: { vi: "Bánh mì chảo", en: "Banh mi skillet" },
        desc: { vi: "Ngon nhất khi ăn nóng, mở cửa tới 22h.", en: "Best eaten hot, open until 10 PM." } },
      { name: { vi: "Bánh mì thịt nướng", en: "Grilled pork banh mi" },
        desc: { vi: "Thịt nướng thơm, ăn nhanh gọn.", en: "Fragrant grilled pork, quick and easy." } },
      { name: { vi: "Bánh bao", en: "Steamed bun" },
        desc: { vi: "Nóng hổi, tiện mang đi làm bữa xế.", en: "Piping hot, handy as an afternoon snack." } },
      { name: { vi: "Bánh giò", en: "Pyramid rice dumpling" },
        desc: { vi: "Ăn kèm dưa chua, hợp bữa sáng nhẹ.", en: "Served with pickles, a light breakfast." } },
    ],
  },
  {
    id: "mon-lau",
    emoji: "🍲",
    dishes: [
      { name: { vi: "Lẩu thái hải sản", en: "Thai seafood hot pot" },
        desc: { vi: "Vị chua cay đặc trưng, hợp ăn nhóm 3-4 người.", en: "Signature sour and spicy, great for groups of 3-4." } },
      { name: { vi: "Lẩu gà lá giang", en: "Chicken hot pot with sour leaves" },
        desc: { vi: "Chua nhẹ, dễ ăn, hợp cả nhà.", en: "Mildly sour, easy to eat, good for the whole family." } },
      { name: { vi: "Lẩu bò nhúng mẻ", en: "Beef hot pot in fermented rice broth" },
        desc: { vi: "Thịt bò tươi, nước lẩu chua nhẹ đặc trưng.", en: "Fresh beef in a signature mildly sour broth." } },
      { name: { vi: "Lẩu mắm", en: "Fermented fish hot pot" },
        desc: { vi: "Đậm vị mắm, nhiều rau, đúng chất miền Tây.", en: "Bold fermented fish flavor, lots of greens, true Mekong style." } },
    ],
  },
  {
    id: "an-vat",
    emoji: "🍢",
    dishes: [
      { name: { vi: "Ốc", en: "Snails" },
        desc: { vi: "Xem bàn tại quán và giờ hẹn phù hợp với bạn.", en: "Check table availability and a time that suits you." } },
      { name: { vi: "Bánh tráng trộn", en: "Rice paper salad" },
        desc: { vi: "Ăn vặt buổi chiều, hợp rủ bạn cùng ăn.", en: "An afternoon snack, fun to share with friends." } },
      { name: { vi: "Chân gà sả tắc", en: "Lemongrass kumquat chicken feet" },
        desc: { vi: "Giòn sần sật, chua cay đúng vị.", en: "Crunchy, sour and spicy just right." } },
      { name: { vi: "Xoài lắc muối ớt", en: "Shaken mango with chili salt" },
        desc: { vi: "Chua giòn, hợp làm món ăn vặt giải khát.", en: "Sour and crunchy, a refreshing snack." } },
    ],
  },
  {
    id: "cuon-banh",
    emoji: "🌯",
    dishes: [
      { name: { vi: "Bánh xèo", en: "Crispy pancake" },
        desc: { vi: "Giòn rụm, ăn kèm rau sống và nước chấm chua ngọt.", en: "Crispy, served with fresh herbs and sweet-sour dipping sauce." } },
      { name: { vi: "Bánh cuốn", en: "Steamed rice rolls" },
        desc: { vi: "Mỏng mềm, ăn kèm chả và hành phi.", en: "Thin and soft, served with pork sausage and fried shallots." } },
      { name: { vi: "Bánh khọt", en: "Mini crispy pancakes" },
        desc: { vi: "Giòn rụm bên ngoài, béo bên trong, ăn nóng ngon nhất.", en: "Crispy outside, rich inside, best eaten hot." } },
      { name: { vi: "Bánh tráng cuốn thịt heo", en: "Pork rice paper rolls" },
        desc: { vi: "Cuốn tại bàn, hợp ăn cùng nhóm bạn.", en: "Rolled at the table, great with friends." } },
    ],
  },
  {
    id: "goi",
    emoji: "🥗",
    dishes: [
      { name: { vi: "Gỏi gà bắp chuối", en: "Chicken & banana blossom salad" },
        desc: { vi: "Chua chua giòn giòn, hợp làm món khai vị hoặc ăn nhẹ.", en: "Tangy and crunchy, great as a starter or light meal." } },
      { name: { vi: "Gỏi ngó sen tôm thịt", en: "Lotus stem salad with shrimp & pork" },
        desc: { vi: "Giòn thanh, hợp ăn trước bữa chính.", en: "Crisp and fresh, great before the main course." } },
      { name: { vi: "Gỏi xoài khô cá", en: "Green mango salad with dried fish" },
        desc: { vi: "Chua ngọt hài hòa, nhắm cùng vài người bạn.", en: "Balanced sweet and sour, perfect with a few friends." } },
      { name: { vi: "Gỏi cuốn tôm thịt", en: "Fresh shrimp & pork spring rolls" },
        desc: { vi: "Nhẹ bụng, thanh mát, hợp ăn xế.", en: "Light and refreshing, great for an afternoon snack." } },
    ],
  },
];

// What is selected / shown before the user spins for the first time
export const DEFAULT_CATEGORY_IDS : string[] = ["pho-bun"];
export const DEFAULT_DISH = SPIN_CATEGORIES[0].dishes[1];

/** Business rule : no category is selected -> spin over every dish */
export function getDishPool (selectedIds : string[]) : Dish[] {
    const selected = SPIN_CATEGORIES.filter((c) => selectedIds.includes(c.id));
    const categories = selected.length > 0 ? selected : SPIN_CATEGORIES;
    return categories.flatMap((c) => c.dishes);
};