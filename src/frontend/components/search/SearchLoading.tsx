import { MapPin, Soup } from 'lucide-react';

// withMapPlaceholder = false lets the real map show through, so only the card list is skeleton
export default function SearchLoading({ vi, withMapPlaceholder = true }: { vi: boolean; withMapPlaceholder?: boolean }) {
  return <div>
    <p role="status" className="mt-1 flex items-center gap-2 text-sm text-neutral-500">
      {vi ? 'Tastly đang tìm quán ngon' : 'Tastly is finding tasty places'}
      <span className="inline-flex gap-1" aria-hidden="true">{[0, 1, 2].map((index) => <span key={index} className="tastly-loading-dot h-1 w-1 rounded-full bg-brick/60" style={{ animationDelay: `${index * 160}ms` }} />)}</span>
    </p>
    <div aria-hidden="true" className="mt-4 flex flex-col gap-4 lg:h-[36rem] lg:flex-row">
      <div className="space-y-4 overflow-hidden p-1 lg:w-[42%] lg:shrink-0">
        {[0, 1, 2, 3].map((index) => <div key={index} className="flex gap-4 rounded-2xl border border-black/5 bg-white/80 p-4 shadow-sm">
          <div className="tastly-loading-shimmer flex h-24 w-24 shrink-0 items-center justify-center rounded-2xl bg-cream"><Soup className="h-7 w-7 text-brick/20" strokeWidth={1.5} /></div>
          <div className="flex-1 space-y-3 py-2">
            <div className="tastly-loading-shimmer h-4 w-3/4 rounded-full bg-cream" />
            <div className="tastly-loading-shimmer h-3 w-1/2 rounded-full bg-cream" />
            <div className="tastly-loading-shimmer h-3 w-5/6 rounded-full bg-cream" />
            <div className="tastly-loading-shimmer h-6 w-24 rounded-full bg-cream" />
          </div>
        </div>)}
      </div>
      {withMapPlaceholder && <div className="relative hidden min-w-0 flex-1 overflow-hidden rounded-3xl border border-black/5 bg-white/50 lg:flex lg:items-center lg:justify-center">
        <div className="absolute h-72 w-72 rounded-full border border-brick/5" />
        <div className="absolute h-48 w-48 rounded-full border border-brick/10" />
        <div className="relative text-center">
          <div className="tastly-loading-bowl mx-auto flex h-20 w-20 items-center justify-center rounded-3xl border border-white bg-cream shadow-sm"><Soup className="h-10 w-10 text-brick/70" strokeWidth={1.4} /></div>
          <p className="mt-5 font-semibold text-ink">{vi ? 'Quán ngon đang ở đâu nhỉ?' : 'Where are the tasty spots?'}</p>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-sm text-neutral-500"><MapPin className="h-3.5 w-3.5" />{vi ? 'Đang dò tìm theo lựa chọn của bạn' : 'Searching for your preferences'}</p>
        </div>
      </div>}
    </div>
  </div>;
}
