"use client";

import { useMemo, useState } from "react";

export type SourceItem = {
  regulation_id: string;
  portal: string;
  title: string;
  fetched_date: string;
  url?: string;
};

export function SourceTrace({ sources }: { sources: SourceItem[] }) {
  const [open, setOpen] = useState(false);
  const count = sources?.length ?? 0;
  const items = useMemo(() => sources ?? [], [sources]);

  return (
    <div className="rounded-md border border-white/10 bg-black/20">
      <button
        className="w-full px-3 py-2 text-left text-xs font-mono text-white/70 hover:bg-white/5"
        onClick={() => setOpen((v) => !v)}
      >
        Sources ({count}) {open ? "▲" : "▼"}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {items.map((s) => (
            <a
              key={`${s.portal}-${s.regulation_id}`}
              href={s.url ?? "#"}
              target="_blank"
              rel="noreferrer"
              className="block rounded-md border border-white/10 bg-white/5 p-2 text-xs hover:bg-white/10"
            >
              <div className="font-mono text-white/80">
                {s.portal}:{s.regulation_id}
              </div>
              <div className="text-white/70">{s.title}</div>
              <div className="mt-1 font-mono text-white/50">{s.fetched_date}</div>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}

