"use client";

import { useEffect, useRef, type ReactNode } from "react";

export default function SearchScrollArea({ children }: { children: ReactNode }) {
  const rootRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const animations = new Map<Element, { destination: number; frame: number }>();
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

    function stopAnimations() {
      for (const animation of animations.values()) cancelAnimationFrame(animation.frame);
      animations.clear();
    }

    function slowWheel(event: WheelEvent) {
      // Preserve browser zoom, horizontal gestures and native form controls.
      if (event.ctrlKey || event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
      const target = event.target;
      if (!(target instanceof Element) || target.closest("select, input, textarea")) return;
      // Map engines handle their own wheel gestures for zooming.
      if (target.closest(".mapboxgl-map, .leaflet-container")) {
        stopAnimations();
        return;
      }

      const list = target.closest<HTMLElement>("[data-search-results-scroll]");
      const scroller = list ?? document.scrollingElement;
      if (!scroller || !event.cancelable || !event.deltaY) return;
      if (scroller.scrollHeight <= scroller.clientHeight) return;

      const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE
        ? 16
        : event.deltaMode === WheelEvent.DOM_DELTA_PAGE
          ? scroller.clientHeight
          : 1;
      event.preventDefault();
      const delta = event.deltaY * unit * 0.75;
      if (reducedMotion.matches) {
        stopAnimations();
        scroller.scrollBy({ top: delta, behavior: "instant" });
        return;
      }

      const existing = animations.get(scroller);
      const destination = Math.max(0, Math.min(
        scroller.scrollHeight - scroller.clientHeight,
        (existing?.destination ?? scroller.scrollTop) + delta,
      ));
      if (existing) {
        existing.destination = destination;
        return;
      }

      const animation = { destination, frame: 0 };
      animations.set(scroller, animation);
      let previousTime = performance.now();
      function tick(time: number) {
        const elapsed = time - previousTime;
        previousTime = time;
        const remaining = animation.destination - scroller!.scrollTop;
        if (Math.abs(remaining) < 0.5) {
          scroller!.scrollTo({ top: animation.destination, behavior: "instant" });
          animations.delete(scroller!);
          return;
        }
        const step = Math.sign(remaining) * Math.min(
          Math.abs(remaining),
          Math.max(1, Math.abs(remaining) * (1 - Math.exp(-elapsed / 120))),
        );
        scroller!.scrollBy({
          top: step,
          behavior: "instant",
        });
        animation.frame = requestAnimationFrame(tick);
      }
      animation.frame = requestAnimationFrame(tick);
    }

    root.addEventListener("wheel", slowWheel, { passive: false });
    // Hand control back immediately when dragging a scrollbar or using the keyboard.
    document.addEventListener("pointerdown", stopAnimations);
    document.addEventListener("keydown", stopAnimations);
    return () => {
      stopAnimations();
      root.removeEventListener("wheel", slowWheel);
      document.removeEventListener("pointerdown", stopAnimations);
      document.removeEventListener("keydown", stopAnimations);
    };
  }, []);

  return (
    <main ref={rootRef} className="mx-6 mt-4 mb-0 lg:mx-10 [&>form]:mt-0 [&+footer]:mt-4">
      {children}
    </main>
  );
}
