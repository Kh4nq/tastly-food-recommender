// Save a cookie for one year so server components can read it on the next request
export function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000`;
}
