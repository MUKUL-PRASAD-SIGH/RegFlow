"use client";

import { useAuth } from "@clerk/nextjs";
import { useCallback, useMemo, useState } from "react";

import { createApiClient } from "@/lib/api-client";

export type AuditEntry = {
  id: string;
  timestamp?: string;
  agent_did: string;
  agent_name: string;
  action_type: string;
  business_id?: string;
  regulation_version?: string;
  confidence_score?: number;
  rail_agreement?: boolean;
  human_approved?: boolean;
  action_hash?: string;
  action_payload?: unknown;
  source_citations?: unknown;
};

export function useAuditTrail() {
  const { getToken } = useAuth();
  const api = useMemo(() => createApiClient({ getToken }), [getToken]);

  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchLedger = useCallback(
    async (params?: { page?: number; pageSize?: number; businessId?: string }) => {
      const page = params?.page ?? 1;
      const pageSize = params?.pageSize ?? 20;
      const businessId = params?.businessId;
      const qs = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
        ...(businessId ? { business_id: businessId } : {}),
      });

      setLoading(true);
      try {
        const res = await api.get<AuditEntry[]>(`/audit/ledger?${qs.toString()}`);
        setEntries(res ?? []);
      } finally {
        setLoading(false);
      }
    },
    [api]
  );

  return { entries, loading, fetchLedger };
}

