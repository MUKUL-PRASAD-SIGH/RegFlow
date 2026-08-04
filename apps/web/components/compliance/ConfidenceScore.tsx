"use client";

import { cn } from "@/lib/utils";

export function ConfidenceScore({ score, size }: { score: number; size: "sm" | "md" | "lg" }) {
  const pct = Math.round(Math.max(0, Math.min(1, score)) * 100);
  const dim = size === "sm" ? 48 : size === "md" ? 72 : 96;
  const stroke = size === "sm" ? 6 : size === "md" ? 8 : 10;
  const r = dim / 2 - stroke;
  const c = 2 * Math.PI * r;
  const offset = c - (pct / 100) * c;

  const color =
    pct > 90 ? "stroke-emerald-400" : pct >= 70 ? "stroke-amber-400" : "stroke-red-400";

  return (
    <div className="inline-flex items-center gap-3">
      <svg width={dim} height={dim} className="shrink-0">
        <circle cx={dim / 2} cy={dim / 2} r={r} strokeWidth={stroke} className="stroke-white/10" fill="none" />
        <circle
          cx={dim / 2}
          cy={dim / 2}
          r={r}
          strokeWidth={stroke}
          className={cn("transition-all duration-700", color)}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${dim / 2} ${dim / 2})`}
        />
      </svg>
      <div className="font-mono">
        <div className="text-xl font-semibold">{pct}%</div>
        <div className="text-xs text-white/60">confidence</div>
      </div>
    </div>
  );
}

