"use client";

import { type ComponentPropsWithoutRef, type ElementType, useEffect, useRef } from "react";

/** 구역이 화면에 들어올 때 한 번, 안의 요소들이 차례로 올라온다.
    스크립트가 없거나 움직임 줄이기 설정이면 처음부터 보인다(내용을 숨기지 않는다). */
export default function Reveal<T extends ElementType = "div">({
  as,
  children,
  className = "",
  ...rest
}: { as?: T } & ComponentPropsWithoutRef<T>) {
  const Tag = (as ?? "div") as ElementType;
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    el.classList.add("reveal-armed");
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          el.classList.add("reveal-in");
          io.disconnect();
        }
      },
      { threshold: 0.18 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag ref={ref} className={className} {...rest}>
      {children}
    </Tag>
  );
}
