"use client";

import { useEffect, useRef } from "react";
import { hashSeed, mulberry32 } from "@/lib/mock/seeded-random";

interface Pt {
  sx: number; // scattered position (unit)
  sy: number;
  tx: number; // target position on the % glyph (unit)
  ty: number;
  delay: number;
  phase: number;
  tone: number;
}

/**
 * Hero background (spec §7.2): abstract data points drift, then slowly
 * converge into the Quant Percent "%" mark. Slow movement, few objects,
 * simplified on mobile, static under prefers-reduced-motion.
 */
export function HeroAnimation() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let raf = 0;
    let points: Pt[] = [];
    let w = 0;
    let h = 0;
    const start = performance.now();

    // Build "%" glyph targets inside the right portion of the hero
    const buildPoints = () => {
      const mobile = w < 768;
      const n = mobile ? 70 : 150;
      const rng = mulberry32(hashSeed("hero", n));
      points = [];

      const squareEdge = (cx: number, cy: number, size: number, u: number) => {
        const edge = u * 4;
        const half = size / 2;
        if (edge < 1) {
          return { x: cx - half + edge * size, y: cy - half };
        }
        if (edge < 2) {
          return { x: cx + half, y: cy - half + (edge - 1) * size };
        }
        if (edge < 3) {
          return { x: cx + half - (edge - 2) * size, y: cy + half };
        }
        return { x: cx - half, y: cy + half - (edge - 3) * size };
      };

      for (let i = 0; i < n; i++) {
        const r = rng();
        let tx: number;
        let ty: number;
        if (r < 0.3) {
          const point = squareEdge(0.25, 0.25, 0.29, rng());
          tx = point.x;
          ty = point.y;
        } else if (r < 0.6) {
          const point = squareEdge(0.75, 0.75, 0.29, rng());
          tx = point.x;
          ty = point.y;
        } else {
          const u = rng();
          tx = 0.86 - u * 0.72 + (rng() - 0.5) * 0.02;
          ty = 0.06 + u * 0.88 + (rng() - 0.5) * 0.02;
        }
        points.push({
          sx: rng(),
          sy: rng(),
          tx,
          ty,
          delay: rng() * 280,
          phase: rng() * Math.PI * 2,
          tone: rng(),
        });
      }
    };

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      w = parent.clientWidth;
      h = parent.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      buildPoints();
    };

    // Map unit glyph coords into a square on the right side (or centered
    // faintly behind text on mobile)
    const glyphRect = () => {
      const mobile = w < 768;
      const side = mobile ? Math.min(w, h) * 0.7 : Math.min(w * 0.36, h * 0.72);
      const x0 = mobile ? (w - side) / 2 : w * 0.61 + (w * 0.37 - side) / 2;
      const y0 = (h - side) / 2;
      return { x0, y0, side };
    };

    const easeInOut = (x: number) =>
      x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;

    const draw = (now: number) => {
      const t = now - start;
      ctx.clearRect(0, 0, w, h);

      // Faint coordinate grid
      ctx.strokeStyle = "rgba(8,127,120,0.05)";
      ctx.lineWidth = 1;
      for (let x = 0.5; x < w; x += 80) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, h);
        ctx.stroke();
      }
      for (let y = 0.5; y < h; y += 80) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(w, y);
        ctx.stroke();
      }

      const { x0, y0, side } = glyphRect();
      const mobile = w < 768;
      const holdMs = 110;
      const settleMs = 1250;

      const positions: { x: number; y: number; p: number; tone: number }[] = [];
      for (const pt of points) {
        const local = reduced
          ? 1
          : Math.max(0, Math.min(1, (t - holdMs - pt.delay) / settleMs));
        const p = easeInOut(local);
        // Scattered position drifts slowly; converged position breathes
        const driftX = Math.sin(t * 0.00025 + pt.phase) * 0.012;
        const driftY = Math.cos(t * 0.0002 + pt.phase) * 0.012;
        const sx = (pt.sx + driftX) * w * 0.92 + w * 0.04;
        const sy = (pt.sy + driftY) * h * 0.86 + h * 0.07;
        const breathe = reduced ? 0 : Math.sin(t * 0.0006 + pt.phase) * 1.5;
        const gx = x0 + pt.tx * side + breathe;
        const gy = y0 + pt.ty * side + breathe * 0.6;
        positions.push({
          x: sx + (gx - sx) * p,
          y: sy + (gy - sy) * p,
          p,
          tone: pt.tone,
        });
      }

      // Sparse connecting lines while scattered (fade out as points settle)
      if (!mobile) {
        for (let i = 0; i < positions.length; i += 5) {
          const a = positions[i];
          const b = positions[(i + 7) % positions.length];
          const alpha = 0.05 * (1 - Math.min(a.p, b.p));
          if (alpha <= 0.004) continue;
          ctx.strokeStyle = `rgba(8,127,120,${alpha})`;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      for (const pos of positions) {
        const alpha = 0.5 + pos.p * 0.45;
        if (pos.tone < 0.24) {
          ctx.fillStyle = `rgba(8,127,120,${alpha})`;
        } else if (pos.tone < 0.4) {
          ctx.fillStyle = `rgba(217,119,6,${alpha})`;
        } else {
          const shade = Math.round(145 - pos.p * 132);
          ctx.fillStyle = `rgba(${shade},${shade},${shade},${alpha})`;
        }
        const r = 1.4 + pos.p * 0.8;
        ctx.beginPath();
        ctx.arc(pos.x, pos.y, r, 0, Math.PI * 2);
        ctx.fill();
      }
    };

    resize();
    if (reduced) {
      draw(start + 100000); // final, static frame
    } else {
      const loop = (now: number) => {
        draw(now);
        raf = requestAnimationFrame(loop);
      };
      raf = requestAnimationFrame(loop);
    }

    const ro = new ResizeObserver(() => {
      resize();
      if (reduced) draw(start + 100000);
    });
    ro.observe(canvas.parentElement as Element);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0"
    />
  );
}
