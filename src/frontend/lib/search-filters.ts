export const FOOD_STYLES = [
  { id: 'wet', emoji: '🍜', vi: 'Món nước (Phở, Bún)', en: 'Soup & noodles', values: ['broth', 'soup'] },
  { id: 'dry', emoji: '🍚', vi: 'Món khô', en: 'Dry dishes', values: ['dry'] },
  { id: 'hotpot', emoji: '🍲', vi: 'Món lẩu', en: 'Hot pot', values: ['hotpot'] },
] as const;

export type FoodStyle = typeof FOOD_STYLES[number]['id'];
export type ItemKind = '' | 'food' | 'beverage';
export const RADII = ['1', '3', '5', '10', ''] as const;

export function parseStyles(values: string[]): FoodStyle[] {
  return FOOD_STYLES.filter((style) => values.includes(style.id)).map((style) => style.id);
}

export function servingStyles(styles: FoodStyle[]) {
  return FOOD_STYLES.filter((style) => styles.includes(style.id)).flatMap((style) => [...style.values]);
}
