"use client";
/* eslint-disable @typescript-eslint/no-explicit-any */

import { useAuth } from "@clerk/nextjs";
import { useEffect, useMemo, useState, Fragment, useCallback } from "react";
import { createApiClient } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useWebSocket } from "@/hooks/useWebSocket";
import { RetriggerBanner } from "@/components/compliance/RetriggerBanner";

type DeltaRow = {
  id: string;
  portal_name: string;
  detected_at: string;
  changed_regulation_ids: string[];
  affected_business_count: number;
  processed: boolean;
  delta_summary?: any;
  affected_businesses?: Array<{ id: string; name: string | null }>;
  skipped_businesses?: Array<{ id: string; name: string | null }>;
};

type PortalStatus = {
  portal: string;
  url: string;
  last_checked: string | null;
  last_hash: string | null;
  change_detected: boolean;
  regulations_monitored: number;
  changes_24h: number;
  status: string;
};

type ScrapingHealth = {
  last_poll_at: string | null;
  poll_interval_seconds: number;
  next_poll_at: string | null;
};

const PORTAL_COLORS: Record<string, string> = {
  gstn: "from-green-500/10 to-green-500/[0.02] border-green-500/15",
  epfo: "from-blue-500/10 to-blue-500/[0.02] border-blue-500/15",
  fssai: "from-orange-500/10 to-orange-500/[0.02] border-orange-500/15",
  pt_states: "from-purple-500/10 to-purple-500/[0.02] border-purple-500/15",
  "pt-states": "from-purple-500/10 to-purple-500/[0.02] border-purple-500/15",
};

const PORTAL_DOT: Record<string, string> = {
  gstn: "bg-green-400",
  epfo: "bg-blue-400",
  fssai: "bg-orange-400",
  pt_states: "bg-purple-400",
  "pt-states": "bg-purple-400",
};

const PORTAL_LABELS: Record<string, string> = {
  gstn: "GSTN",
  epfo: "EPFO",
  fssai: "FSSAI",
  pt_states: "PT States",
  "pt-states": "PT States",
};

export default function ComplianceFeedPage() {
  const { getToken } = useAuth();
  const api = useMemo(() => createApiClient({ getToken }), [getToken]);
  const ws = useWebSocket({ url: process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8002/ws/retrigger" });

  const [deltas, setDeltas] = useState<DeltaRow[]>([]);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [portal, setPortal] = useState<"gstn" | "epfo" | "fssai" | "pt-states">("gstn");
  const [regulationId, setRegulationId] = useState<string>("GST_LATE_FEE_001");
  const [field, setField] = useState<"value" | "title" | "description">("value");
  const [newValue, setNewValue] = useState<string>("250");
  const [portalStatuses, setPortalStatuses] = useState<PortalStatus[]>([]);
  const [portalRegs, setPortalRegs] = useState<any[]>([]);
  const [isTriggering, setIsTriggering] = useState(false);
  const [scrapingHealth, setScrapingHealth] = useState<ScrapingHealth | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await api.get<any>("/admin/deltas");
      setDeltas(rows ?? []);
    } catch {
      setDeltas([]);
    }
  }, [api]);

  const loadStatuses = useCallback(async () => {
    try {
      const rows = await api.get<PortalStatus[]>("/admin/portal-status");
      setPortalStatuses(rows ?? []);
    } catch {
      setPortalStatuses([]);
    }
  }, [api]);

  const loadScrapingHealth = useCallback(async () => {
    try {
      const data = await api.get<ScrapingHealth>("/admin/scraping-health");
      setScrapingHealth(data);
    } catch {
      setScrapingHealth(null);
    }
  }, [api]);

  const loadPortalRegs = async (p: string) => {
    try {
      const data = await api.get<any>(`/admin/portal/${p}`);
      const regs = data?.regulations ?? [];
      setPortalRegs(regs);
      if (regs[0]?.id) setRegulationId(regs[0].id);
    } catch {
      setPortalRegs([]);
    }
  };

  useEffect(() => {
    load();
    loadStatuses();
    loadScrapingHealth();
    loadPortalRegs(portal);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-refresh every 30s to catch new changes
  useEffect(() => {
    const interval = setInterval(() => {
      load();
      loadStatuses();
      loadScrapingHealth();
    }, 30000);
    return () => clearInterval(interval);
  }, [load, loadStatuses, loadScrapingHealth]);

  // Countdown timer to next scrape
  useEffect(() => {
    if (!scrapingHealth?.next_poll_at) {
      setCountdown(null);
      return;
    }
    const tick = () => {
      const nextPoll = new Date(scrapingHealth.next_poll_at!).getTime();
      const remaining = Math.max(0, Math.round((nextPoll - Date.now()) / 1000));
      setCountdown(remaining);
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [scrapingHealth?.next_poll_at]);

  useEffect(() => {
    loadPortalRegs(portal);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [portal]);

  useEffect(() => {
    if (ws.lastEvent?.event === "regulation_change") {
      load();
      loadStatuses();
      loadScrapingHealth();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ws.lastEvent]);

  const triggerChange = async () => {
    if (isTriggering) return;
    setIsTriggering(true);
    try {
      const payload: any = {
        portal,
        regulation_id: regulationId,
        field,
        new_value: field === "value" ? Number(newValue) : newValue,
      };
      await api.post("/admin/demo/trigger-change", payload);
      setOpen(false);
    } finally {
      setIsTriggering(false);
    }
  };

  const bannerEvent =
    ws.lastEvent?.event === "regulation_change"
      ? ({
          portal: ws.lastEvent.portal as any,
          affected_count: ws.lastEvent.affected_count as any,
          message: ws.lastEvent.message as any,
          delta_id: ws.lastEvent.delta_id as any,
        } as any)
      : null;

  const portalUnreachable =
    ws.lastEvent?.event === "portal_unreachable" ? ws.lastEvent : null;

  return (
    <div className="space-y-5">
      <RetriggerBanner event={bannerEvent} />

      {/* Portal Unreachable Alert */}
      {portalUnreachable && (
        <div className="rounded-lg border border-red-500/20 bg-red-500/[0.06] px-4 py-3 animate-fade-in-up">
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-red-500 animate-pulse" />
            <span className="text-sm font-medium text-red-300">
              Portal Unreachable: {PORTAL_LABELS[portalUnreachable.portal] ?? portalUnreachable.portal}
            </span>
          </div>
          <div className="mt-1 text-[11px] font-mono text-red-300/60">
            {portalUnreachable.error}
          </div>
        </div>
      )}

      {/* ─── Live Scraping Health Bar ─── */}
      <Card className="glass border-white/[0.06] p-4 animate-fade-in-up">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="relative flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75 animate-ping" />
              <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-500" />
            </div>
            <div>
              <div className="text-sm font-semibold">Live Scraping Active</div>
              <div className="text-[10px] font-mono text-white/30">
                IRDA agent polling {portalStatuses.length} portals every 30s
              </div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {scrapingHealth?.last_poll_at && (
              <div className="text-right">
                <div className="text-[10px] font-mono text-white/30">Last scrape</div>
                <div className="text-[11px] font-mono text-white/50">
                  {new Date(scrapingHealth.last_poll_at).toLocaleTimeString()}
                </div>
              </div>
            )}
            {countdown !== null && (
              <div className="text-right">
                <div className="text-[10px] font-mono text-white/30">Next in</div>
                <div className="text-sm font-mono font-semibold text-emerald-400">{countdown}s</div>
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* ─── Portal Status Cards ─── */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-fade-in-up">
        {(portalStatuses ?? []).map((p) => {
          const portalKey = p.portal?.toLowerCase?.() ?? "";
          const isLive = p.status === "live";
          const isAwaiting = p.status === "awaiting_first_scrape";
          return (
            <Card key={p.portal} className={`border bg-gradient-to-br p-4 ${PORTAL_COLORS[portalKey] ?? "border-white/[0.06] from-white/[0.03] to-transparent"}`}>
              <div className="flex items-center justify-between">
                <div className="text-sm font-semibold">{PORTAL_LABELS[portalKey] ?? portalKey}</div>
                <div className="flex items-center gap-1.5">
                  {p.changes_24h > 0 && (
                    <Badge className="bg-amber-500/15 border-amber-500/20 text-amber-300 text-[9px] px-1.5">
                      {p.changes_24h} Δ
                    </Badge>
                  )}
                  <span
                    className={`h-2 w-2 rounded-full ${
                      isLive
                        ? p.change_detected
                          ? `${PORTAL_DOT[portalKey] ?? "bg-emerald-400"} animate-dot-pulse`
                          : "bg-emerald-500/50"
                        : isAwaiting
                        ? "bg-amber-400 animate-pulse"
                        : "bg-white/15"
                    }`}
                  />
                </div>
              </div>
              <div className="mt-3 space-y-1">
                <div className="text-[10px] font-mono text-white/30">
                  status: <span className={isLive ? "text-emerald-400/70" : "text-amber-400/70"}>{p.status}</span>
                </div>
                <div className="text-[10px] font-mono text-white/30">
                  scraped: {p.last_checked ? new Date(p.last_checked).toLocaleTimeString() : "never"}
                </div>
                <div className="text-[10px] font-mono text-white/30">
                  hash: {p.last_hash ? String(p.last_hash).slice(0, 14) + "…" : "—"}
                </div>
                <div className="text-[10px] font-mono text-white/30">
                  monitoring: {p.regulations_monitored ?? 0} regulations
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      {/* ─── Watcher Controls ─── */}
      <Card className="glass border-white/[0.06] p-5 animate-fade-in-up stagger-1">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold">Regulation Watcher Controls</div>
            <div className="mt-0.5 text-[11px] font-mono text-white/30">IRDA live monitoring — demo override trigger</div>
          </div>

          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
              <Button className="bg-blue-500 hover:bg-blue-600 text-white font-medium shadow-[0_0_12px_rgba(59,130,246,0.3)]">
                ⚡ Trigger Manual Check
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-[#0d1117] text-white border-white/[0.08] shadow-2xl">
              <DialogHeader>
                <DialogTitle>Trigger Regulation Change (Demo)</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-mono text-white/40 tracking-widest uppercase mb-1.5">Portal</label>
                  <select
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm focus:border-blue-500/30 focus:outline-none transition"
                    value={portal}
                    onChange={(e) => setPortal(e.target.value as any)}
                  >
                    <option value="gstn">GSTN</option>
                    <option value="epfo">EPFO</option>
                    <option value="fssai">FSSAI</option>
                    <option value="pt-states">PT States</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] font-mono text-white/40 tracking-widest uppercase mb-1.5">Regulation</label>
                  <select
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm focus:border-blue-500/30 focus:outline-none transition"
                    value={regulationId}
                    onChange={(e) => setRegulationId(e.target.value)}
                  >
                    {(portalRegs ?? []).map((r: any) => (
                      <option key={r.id} value={r.id}>
                        {r.id} — {r.title}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] font-mono text-white/40 tracking-widest uppercase mb-1.5">Field</label>
                  <select
                    className="w-full bg-white/[0.04] border border-white/[0.08] rounded-lg px-3 py-2 text-sm focus:border-blue-500/30 focus:outline-none transition"
                    value={field}
                    onChange={(e) => setField(e.target.value as any)}
                  >
                    <option value="value">value</option>
                    <option value="title">title</option>
                    <option value="description">description</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[10px] font-mono text-white/40 tracking-widest uppercase mb-1.5">New Value</label>
                  <Input
                    className="bg-white/[0.04] border-white/[0.08]"
                    value={newValue}
                    onChange={(e) => setNewValue(e.target.value)}
                    placeholder="e.g. 250 or updated title..."
                  />
                </div>
              </div>
              <DialogFooter>
                <Button variant="secondary" onClick={() => setOpen(false)} disabled={isTriggering}>Cancel</Button>
                <Button onClick={triggerChange} disabled={isTriggering} className="bg-blue-500 hover:bg-blue-600">
                  {isTriggering ? "Pushing..." : "Push Change"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </Card>

      {/* ─── Delta History ─── */}
      <Card className="glass border-white/[0.06] p-5 animate-fade-in-up stagger-2">
        <div className="text-sm font-semibold">Delta History</div>
        <div className="mt-0.5 text-[11px] font-mono text-white/30">Regulation snapshots with before/after comparison — auto-refreshes every 30s</div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-[10px] font-mono text-white/30 tracking-wider uppercase">
              <tr>
                <th className="py-2 pr-4">Portal</th>
                <th className="pr-4">Detected</th>
                <th className="pr-4">Changed Regs</th>
                <th className="pr-4">Affected</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {deltas.map((d) => (
                <Fragment key={d.id}>
                  <tr className="border-t border-white/[0.04] hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 pr-4">
                      <span className={`inline-flex items-center gap-1.5 font-mono text-xs`}>
                        <span className={`h-1.5 w-1.5 rounded-full ${PORTAL_DOT[d.portal_name] ?? "bg-white/30"}`} />
                        {PORTAL_LABELS[d.portal_name] ?? d.portal_name}
                      </span>
                    </td>
                    <td className="pr-4 font-mono text-[11px] text-white/40">
                      {d.detected_at ? new Date(d.detected_at).toLocaleString() : "—"}
                    </td>
                    <td className="pr-4 font-mono text-[11px]">{(d.changed_regulation_ids ?? []).join(", ")}</td>
                    <td className="pr-4 font-mono text-sm font-semibold">{d.affected_business_count}</td>
                    <td>
                      <div className="flex items-center gap-3">
                        <Badge
                          className={
                            d.processed
                              ? "bg-emerald-500/15 border-emerald-500/20 text-emerald-300 text-[10px]"
                              : "bg-amber-500/15 border-amber-500/20 text-amber-300 text-[10px]"
                          }
                        >
                          {d.processed ? "processed" : "pending"}
                        </Badge>
                        <button
                          className="text-[11px] text-blue-400 hover:text-blue-300 font-mono transition"
                          onClick={() => setExpandedId((prev) => (prev === d.id ? null : d.id))}
                        >
                          {expandedId === d.id ? "Hide ▲" : "Details ▼"}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedId === d.id && (
                    <tr>
                      <td colSpan={5} className="py-4 px-2">
                        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                          {/* Before/After */}
                          <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-xs font-semibold text-white/70">Before / After</div>
                            <div className="mt-3 space-y-2">
                              {(d.delta_summary?.changes ?? []).length === 0 ? (
                                <div className="text-[11px] text-white/30">No field-level changes stored.</div>
                              ) : (
                                (d.delta_summary?.changes ?? []).map((c: any, idx: number) => (
                                  <div key={idx} className="text-[11px] font-mono">
                                    <span className="text-white/40">{c.field_changed}:</span>{" "}
                                    <span className="text-red-400 line-through">{String(c.old_value)}</span>{" "}
                                    <span className="text-white/20">→</span>{" "}
                                    <span className="text-emerald-400 font-semibold">{String(c.new_value)}</span>
                                  </div>
                                ))
                              )}
                            </div>
                          </div>

                          {/* Re-triggered vs Skipped */}
                          <div className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-4">
                            <div className="text-xs font-semibold text-white/70">Retrigger Log</div>
                            <div className="mt-3 grid grid-cols-2 gap-4">
                              <div>
                                <div className="text-[10px] font-mono text-emerald-400 tracking-wider uppercase">Re-triggered</div>
                                <div className="mt-2 space-y-1">
                                  {(d.affected_businesses ?? []).length === 0 ? (
                                    <div className="text-[11px] text-white/20">—</div>
                                  ) : (
                                    (d.affected_businesses ?? []).map((b: any) => (
                                      <div key={b.id} className="text-[11px] font-mono text-white/60">{b.name ?? b.id}</div>
                                    ))
                                  )}
                                </div>
                              </div>
                              <div>
                                <div className="text-[10px] font-mono text-amber-400 tracking-wider uppercase">Skipped</div>
                                <div className="mt-2 space-y-1">
                                  {(d.skipped_businesses ?? []).length === 0 ? (
                                    <div className="text-[11px] text-white/20">—</div>
                                  ) : (
                                    <>
                                      {(d.skipped_businesses ?? []).slice(0, 10).map((b: any) => (
                                        <div key={b.id} className="text-[11px] font-mono text-white/40">{b.name ?? b.id}</div>
                                      ))}
                                      {(d.skipped_businesses ?? []).length > 10 && (
                                        <div className="text-[10px] text-white/20">+ {(d.skipped_businesses ?? []).length - 10} more</div>
                                      )}
                                    </>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
              {deltas.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-sm text-white/30 text-center">
                    No deltas yet — the IRDA agent is actively scraping portals every 30s. Changes will appear here automatically.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
