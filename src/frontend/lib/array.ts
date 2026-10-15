/** Return one random item from the list */
export function pickRandom<T>(items: T[]): T {
    return items[Math.floor(Math.random() * items.length)];
}

/** Remove `item` if it present otherwise add it. */
export function toggleItem<T>(items: T[], item: T): T[] {
    return items.includes(item) ? items.filter((i) => i !== item) : [...items, item];
}