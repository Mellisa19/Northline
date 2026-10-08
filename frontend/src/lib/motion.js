import { useCallback, useEffect, useRef, useState } from "react";

/* ==========================================================================
   Motion primitives.

   Everything here respects prefers-reduced-motion and cleans up after itself.
   Animations are driven by rAF rather than CSS transitions where the value has
   to be interpolated (numbers), and by CSS classes where it does not.
   ========================================================================== */

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return undefined;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  return reduced;
}

/** Marks an element visible once it scrolls into view. */
export function useInView({ threshold = 0.12, rootMargin = "0px 0px -6% 0px", once = true } = {}) {
  const ref = useRef(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const node = ref.current;
    if (!node) return undefined;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return undefined;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) observer.disconnect();
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { threshold, rootMargin },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [threshold, rootMargin, once]);

  return [ref, inView];
}

/** Eases a number towards its target. Used for headline figures. */
export function useCountUp(value, { duration = 850, enabled = true } = {}) {
  const reduced = usePrefersReducedMotion();
  const target = Number(value) || 0;
  const [display, setDisplay] = useState(target);
  const displayRef = useRef(target);
  const frame = useRef(0);
  const started = useRef(false);

  useEffect(() => {
    if (!enabled || reduced) {
      displayRef.current = target;
      setDisplay(target);
      return undefined;
    }
    const from = started.current ? displayRef.current : 0;
    started.current = true;
    if (from === target) {
      displayRef.current = target;
      setDisplay(target);
      return undefined;
    }

    const start = typeof performance !== "undefined" ? performance.now() : Date.now();
    const step = (now) => {
      const elapsed = now - start;
      const t = Math.min(1, elapsed / duration);
      const eased = 1 - Math.pow(1 - t, 3);
      const current = from + (target - from) * eased;
      displayRef.current = current;
      setDisplay(current);
      if (t < 1) frame.current = requestAnimationFrame(step);
      else displayRef.current = target;
    };
    frame.current = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame.current);
  }, [target, duration, enabled, reduced]);

  return enabled && !reduced ? display : target;
}

/** Reading progress through the document, 0 to 1. */
export function useScrollProgress() {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    const update = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - window.innerHeight;
      setProgress(max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0);
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  return progress;
}

/** Closes a floating element on outside click or Escape. */
export function useDismiss(ref, onDismiss, active = true) {
  const handler = useCallback(
    (event) => {
      if (!active) return;
      if (event.type === "keydown" && event.key === "Escape") {
        onDismiss();
        return;
      }
      if (ref.current && !ref.current.contains(event.target)) onDismiss();
    },
    [ref, onDismiss, active],
  );

  useEffect(() => {
    if (!active) return undefined;
    document.addEventListener("mousedown", handler);
    document.addEventListener("keydown", handler);
    return () => {
      document.removeEventListener("mousedown", handler);
      document.removeEventListener("keydown", handler);
    };
  }, [handler, active]);
}

/** Trailing debounce for search inputs. */
export function useDebounced(value, delay = 260) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
