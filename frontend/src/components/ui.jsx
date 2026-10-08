import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useCountUp, useDismiss, useInView } from "../lib/motion";

/* ==========================================================================
   Shared interface pieces. Small, unopinionated, and used by both the site and
   the workspace so the two never drift apart.
   ========================================================================== */

/** Fades and lifts its children into view once. */
export function Reveal({ children, delay = 0, variant = "", as: Tag = "div", className = "", ...rest }) {
  const [ref, inView] = useInView();
  return (
    <Tag
      ref={ref}
      className={`reveal${variant ? ` reveal--${variant}` : ""}${inView ? " is-visible" : ""}${className ? ` ${className}` : ""}`}
      style={{ "--reveal-delay": `${delay}ms` }}
      {...rest}
    >
      {children}
    </Tag>
  );
}

/** A figure that eases to its value, formatted the way the rest of the app formats. */
export function CountUp({ value, format = (n) => Math.round(n).toLocaleString("en-NG"), duration, enabled = true }) {
  const current = useCountUp(value, { duration, enabled });
  return <span className="tnum">{format(current)}</span>;
}

const TONES = ["clay", "ochre", "sage", "plum", "marine", "rust"];

/** Initials on a warm tint. Cheaper and more honest than stock photography. */
export function Avatar({ name = "", tone, size = 30, src }) {
  const initials = useMemo(
    () =>
      String(name)
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((word) => word[0])
        .join("")
        .toUpperCase() || "–",
    [name],
  );
  const resolved = tone ?? TONES[String(name).length % TONES.length];

  if (src) {
    return <img className="avatar" src={src} alt={name} width={size} height={size} />;
  }

  return (
    <span
      className={`avatar avatar--${resolved}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      title={name}
      aria-hidden="true"
    >
      {initials}
    </span>
  );
}

/**
 * A dropdown that looks like the rest of the product.
 *
 * Native selects cannot be styled consistently across platforms, which is why
 * they read as a browser control dropped into a designed page. This is a real
 * listbox: keyboard navigable, dismissible, and labelled.
 */
export function Select({
  value,
  onChange,
  options = [],
  placeholder = "Any",
  label,
  size = "md",
  align = "start",
  disabled = false,
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [flip, setFlip] = useState(false);
  const root = useRef(null);
  const listId = useId();

  useDismiss(root, () => setOpen(false), open);

  const selectedIndex = options.findIndex((option) => String(option.value) === String(value));
  const selected = selectedIndex >= 0 ? options[selectedIndex] : null;

  useEffect(() => {
    if (open) setActive(selectedIndex >= 0 ? selectedIndex : 0);
  }, [open, selectedIndex]);

  useEffect(() => {
    if (!open || !root.current) return;
    // Flip the panel upwards when there is not enough room below.
    const rect = root.current.getBoundingClientRect();
    setFlip(window.innerHeight - rect.bottom < 260 && rect.top > 260);
  }, [open]);

  function commit(index) {
    const option = options[index];
    if (!option) return;
    onChange?.(option.value, option);
    setOpen(false);
  }

  function onKeyDown(event) {
    if (disabled) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => Math.min(options.length - 1, Math.max(0, index + delta)));
      return;
    }
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      if (open) commit(active);
      else setOpen(true);
      return;
    }
    if (event.key === "Home" && open) {
      event.preventDefault();
      setActive(0);
    }
    if (event.key === "End" && open) {
      event.preventDefault();
      setActive(options.length - 1);
    }
  }

  return (
    <div className={`select select--${size}${open ? " is-open" : ""}${disabled ? " is-disabled" : ""}`} ref={root}>
      {label ? <span className="eyebrow select__label">{label}</span> : null}
      <button
        type="button"
        className="select__button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => setOpen((state) => !state)}
        onKeyDown={onKeyDown}
      >
        <span className={`select__value${selected ? "" : " select__value--placeholder"}`}>
          {selected ? (
            <>
              {selected.tone ? <span className="select__swatch" style={{ background: selected.tone }} /> : null}
              {selected.label}
            </>
          ) : (
            placeholder
          )}
        </span>
        <span className="select__chevron" aria-hidden="true">
          <svg viewBox="0 0 12 8" width="11" height="8">
            <path d="M1 1.5 6 6.5 11 1.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
      </button>

      {open ? (
        <ul
          className={`select__menu${flip ? " select__menu--up" : ""}`}
          role="listbox"
          id={listId}
          style={{ [align === "end" ? "right" : "left"]: 0 }}
        >
          {options.map((option, index) => {
            const isSelected = index === selectedIndex;
            return (
              <li key={String(option.value)}>
                <button
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  className={`select__option${index === active ? " is-active" : ""}${isSelected ? " is-selected" : ""}`}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => commit(index)}
                >
                  {option.tone ? <span className="select__swatch" style={{ background: option.tone }} /> : null}
                  <span className="select__option-label">{option.label}</span>
                  {option.hint ? <span className="select__option-hint">{option.hint}</span> : null}
                  {isSelected ? (
                    <span className="select__check" aria-hidden="true">
                      <svg viewBox="0 0 12 10" width="11" height="9">
                        <path d="M1 5l3.2 3.2L11 1.6" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
                      </svg>
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

/** A row of mutually exclusive pills. Used for review budgets and list filters. */
export function Segmented({ value, onChange, options = [], size = "md" }) {
  const highlight = useRef(null);
  const container = useRef(null);

  useEffect(() => {
    const node = container.current;
    const target = node?.querySelector(`[data-key="${value}"]`);
    if (!node || !target) return;
    const box = node.getBoundingClientRect();
    const rect = target.getBoundingClientRect();
    highlight.current?.style.setProperty("transform", `translateX(${rect.left - box.left}px)`);
    highlight.current?.style.setProperty("width", `${rect.width}px`);
  }, [value, options]);

  return (
    <div className={`segmented segmented--${size}`} ref={container} role="tablist">
      <span className="segmented__highlight" ref={highlight} aria-hidden="true" />
      {options.map((option) => (
        <button
          key={String(option.value)}
          type="button"
          role="tab"
          data-key={option.value}
          aria-selected={String(value) === String(option.value)}
          className={String(value) === String(option.value) ? "is-active" : ""}
          onClick={() => onChange?.(option.value, option)}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

/** An infinite strip of short facts. Sits under the hero. */
export function Ticker({ items = [], speed = 46 }) {
  const doubled = [...items, ...items];
  return (
    <div className="ticker" aria-hidden="true">
      <div className="ticker__track" style={{ animationDuration: `${speed}s` }}>
        {doubled.map((item, index) => (
          <span className="ticker__item" key={`${item.label}-${index}`}>
            <span className="ticker__dot" />
            <span className="ticker__label">{item.label}</span>
            <span className="ticker__value tnum">{item.value}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function Spinner({ size = 16 }) {
  return (
    <span className="spinner" style={{ width: size, height: size }} aria-label="Loading">
      <svg viewBox="0 0 24 24" width={size} height={size}>
        <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.2" strokeWidth="3" />
        <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
      </svg>
    </span>
  );
}

/** Deterministic tint for an officer or borrower, so colours stay stable. */
export function toneFor(name = "") {
  return TONES[String(name).length % TONES.length];
}
