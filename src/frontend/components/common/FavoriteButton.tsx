"use client";

import Link from 'next/link';
import { useRef, useState } from 'react';
import { Heart, X } from 'lucide-react';
import { useT } from '../layout/LangProvider';
import { toggleFavorite, useFavorites, type SavedRestaurant } from '@/lib/favorites';
import { ApiError, me } from '@/lib/api';
import { errorText } from '@/lib/error-text';

export default function FavoriteButton({ restaurant }: { restaurant: SavedRestaurant }) {
  const t = useT();
  const vi = t.lang === 'vi';
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [returnTo, setReturnTo] = useState('/search');
  const saved = useFavorites().some((item) => item.restaurant_id === restaurant.restaurant_id);
  async function toggle() {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await me(); // fetch sends the HttpOnly cookie without exposing it to JavaScript.
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setReturnTo(window.location.pathname + window.location.search);
        dialogRef.current?.showModal();
      } else setError(errorText(t, err));
      setBusy(false);
      return;
    }
    try { toggleFavorite(restaurant); setError(''); }
    catch { setError(vi ? 'Chưa lưu được. Kiểm tra quyền lưu trữ của trình duyệt nhé.' : 'Unable to save. Check your browser storage settings.'); }
    finally { setBusy(false); }
  }
  return <>
    <button type="button" disabled={busy} aria-busy={busy} onClick={(event) => { event.stopPropagation(); toggle(); }} aria-pressed={saved} aria-label={saved ? (vi ? 'Bỏ yêu thích' : 'Remove favorite') : (vi ? 'Thêm vào yêu thích' : 'Save favorite')} title={saved ? (vi ? 'Đã yêu thích' : 'Saved') : (vi ? 'Thêm vào yêu thích' : 'Save favorite')} className={`relative z-10 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border transition-[color,background-color,transform] duration-200 hover:scale-105 focus-visible:outline-2 focus-visible:outline-brick motion-reduce:transform-none ${saved ? 'border-brick/10 bg-brick/5 text-brick' : 'border-neutral-100 bg-white text-neutral-400 hover:bg-brick/5 hover:text-brick'}`}>
      <Heart className={`h-4 w-4 ${saved ? 'fill-current' : ''}`} strokeWidth={1.7} />
    </button>
    {error && <span role="status" className="relative z-10 text-xs text-brick">{error}</span>}
    <dialog ref={dialogRef} aria-labelledby={`favorite-title-${restaurant.restaurant_id}`} onClick={(event) => { event.stopPropagation(); if (event.target === event.currentTarget) dialogRef.current?.close(); }} className="fixed inset-0 m-auto w-[calc(100%_-_2rem)] max-w-sm rounded-3xl border border-black/5 bg-cream p-7 text-center text-ink shadow-xl backdrop:bg-black/25">
      <button type="button" autoFocus onClick={() => dialogRef.current?.close()} aria-label={vi ? 'Đóng' : 'Close'} className="absolute right-3 top-3 rounded-full p-2 text-neutral-500 hover:bg-white"><X className="h-4 w-4" /></button>
      <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-2xl bg-white text-brick"><Heart className="h-5 w-5" /></div>
      <h2 id={`favorite-title-${restaurant.restaurant_id}`} className="text-xl font-bold">{vi ? 'Giữ lại quán bạn thích' : 'Keep your favorite places'}</h2>
      <p className="mt-3 text-sm leading-relaxed text-neutral-500">{vi ? 'Đăng nhập để lưu quán này vào danh sách yêu thích nhé.' : 'Log in to save this restaurant to your favorites.'}</p>
      <Link href={`/login?next=${encodeURIComponent(returnTo)}`} className="mt-6 block rounded-full bg-brick px-5 py-3 text-sm font-semibold text-white">{t.auth.login}</Link>
      <Link href="/register" className="mt-2 block rounded-full border border-brick/15 bg-white px-5 py-3 text-sm font-semibold text-brick">{t.auth.register}</Link>
    </dialog>
  </>;
}
