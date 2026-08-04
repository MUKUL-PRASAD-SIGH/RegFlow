"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useMemo, useState } from "react";

import { createApiClient } from "@/lib/api-client";
import { WebSocketEvent } from "@/hooks/useWebSocket";

export type ComplianceAlert = {
  id: string;
  business_id: string;
  alert_type?: string;
  title?: string;
  message?: string;
  is_read: boolean;
  created_at?: string;
  plain_language_card?: unknown;
};

export function useComplianceAlerts(businessId?: string, wsEvent?: WebSocketEvent | null) {
  const { getToken } = useAuth();
  const api = useMemo(() => createApiClient({ getToken }), [getToken]);

  const [alerts, setAlerts] = useState<ComplianceAlert[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(false);

  const refresh = useCallback(async () => {
    if (!businessId) return;
    setLoading(true);
    try {
      const res = await api.get<{ alerts: ComplianceAlert[]; unread_count: number }>(
        `/compliance/alerts?business_id=${encodeURIComponent(businessId)}`
      );
      setAlerts(res.alerts ?? []);
      setUnreadCount(res.unread_count ?? 0);
    } finally {
      setLoading(false);
    }
  }, [api, businessId]);

  const markRead = useCallback(
    async (alertId: string) => {
      await api.post(`/compliance/alerts/${alertId}/read`);
      await refresh();
    },
    [api, refresh]
  );

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    if (!wsEvent) return;
    if (wsEvent.event === "regulation_change" || wsEvent.event === "pending_alerts") {
      refresh();
    }
  }, [wsEvent, refresh]);

  return { alerts, unreadCount, loading, refresh, markRead };
}

