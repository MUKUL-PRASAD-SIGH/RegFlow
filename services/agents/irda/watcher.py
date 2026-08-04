import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.config import settings
from services.api.database import RegulationDelta, RegulationSnapshot

logger = logging.getLogger("irda.watcher")

# Regex to extract JSON from <script type="application/json" id="regulations-data">
_EMBEDDED_JSON_RE = re.compile(
    r'<script\s+type=["\']application/json["\']\s+id=["\']regulations-data["\']>\s*(.*?)\s*</script>',
    re.DOTALL | re.IGNORECASE,
)


def _extract_regulations_from_html(html_text: str) -> dict | None:
    """
    Extract regulation JSON from an HTML page.
    Looks for a <script type="application/json" id="regulations-data"> block.
    Returns the parsed dict, or None if not found.
    """
    match = _EMBEDDED_JSON_RE.search(html_text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


class RegulationWatcher:
    """Watches live Vercel-deployed regulatory portals for changes via HTTP scraping."""

    def __init__(self) -> None:
        self._last_poll_results: dict[str, dict] = {}

    async def fetch_portal_data(
        self, portal_name: str, url: str, *, allow_demo_override: bool = False
    ) -> dict:
        """
        Fetch regulation data from a live portal URL.

        Supports two response formats:
          1. Raw JSON (Content-Type: application/json) — parsed directly
          2. HTML page — extracts embedded JSON from <script id="regulations-data">

        Redis demo-override path is only used when explicitly requested
        by the demo trigger endpoint (allow_demo_override=True).
        """

        # ── Demo-only override (used exclusively by /admin/demo/trigger-change) ──
        if allow_demo_override:
            try:
                import redis as _redis
                r = _redis.from_url(settings.redis_url)
                override = r.get(f"portal_override:{portal_name}")
                if override:
                    logger.info(
                        "[%s] Using Redis demo-override (demo trigger path)", portal_name
                    )
                    return json.loads(override)
            except Exception:
                pass

        # ── Live HTTP scraping with retry ──
        last_error: Exception | None = None
        for attempt in range(1, 4):  # 3 attempts with exponential backoff
            t0 = time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    response = await client.get(url)
                    response.raise_for_status()

                elapsed_ms = round((time.monotonic() - t0) * 1000)
                content_type = response.headers.get("content-type", "")
                raw_text = response.text

                # ── Try raw JSON first ──
                data: dict | None = None
                if "application/json" in content_type:
                    try:
                        data = response.json()
                    except Exception:
                        pass

                # ── If HTML, extract embedded regulation JSON ──
                if data is None and ("text/html" in content_type or raw_text.strip().startswith("<!") or raw_text.strip().startswith("<html")):
                    data = _extract_regulations_from_html(raw_text)
                    if data:
                        logger.info(
                            "[%s] Extracted regulations from HTML page (embedded JSON block)",
                            portal_name,
                        )

                # ── Last resort: try parsing as JSON regardless of content-type ──
                if data is None:
                    try:
                        data = json.loads(raw_text)
                    except Exception:
                        pass

                if data is None:
                    logger.warning(
                        "[%s] Could not parse regulation data from %s (content-type: %s)",
                        portal_name,
                        url,
                        content_type,
                    )
                    return {"regulations": [], "_error": "parse_failed"}

                # Validate response structure
                if not isinstance(data, dict) or "regulations" not in data:
                    logger.warning(
                        "[%s] Invalid response structure from %s (missing 'regulations' key)",
                        portal_name,
                        url,
                    )
                    return {"regulations": [], "_error": "invalid_structure"}

                reg_count = len(data.get("regulations", []))
                logger.info(
                    "[%s] Live scrape OK — %d regulations, %dms, attempt %d",
                    portal_name,
                    reg_count,
                    elapsed_ms,
                    attempt,
                )

                # Track last poll result for status reporting
                self._last_poll_results[portal_name] = {
                    "status": "ok",
                    "url": url,
                    "regulations_count": reg_count,
                    "latency_ms": elapsed_ms,
                    "source": "html_embedded" if "text/html" in content_type else "json_direct",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                return data

            except Exception as e:
                elapsed_ms = round((time.monotonic() - t0) * 1000)
                last_error = e
                logger.warning(
                    "[%s] Scrape attempt %d/3 failed (%dms): %s",
                    portal_name,
                    attempt,
                    elapsed_ms,
                    str(e),
                )
                if attempt < 3:
                    import asyncio
                    await asyncio.sleep(2 ** attempt)  # 2s, 4s backoff

        # All retries exhausted
        logger.error(
            "[%s] All 3 scrape attempts failed for %s — last error: %s",
            portal_name,
            url,
            str(last_error),
        )
        self._last_poll_results[portal_name] = {
            "status": "error",
            "url": url,
            "error": str(last_error),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return {"regulations": [], "_error": str(last_error)}

    def compute_hash(self, data: dict) -> str:
        """Compute a deterministic SHA-256 hash of portal data (excluding internal keys)."""
        # Strip internal keys before hashing
        clean = {k: v for k, v in data.items() if not k.startswith("_")}
        normalized = json.dumps(clean, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    async def check_portal_for_changes(
        self,
        portal_name: str,
        url: str,
        db_session: AsyncSession,
        *,
        allow_demo_override: bool = False,
    ) -> Optional[RegulationDelta]:
        current_data = await self.fetch_portal_data(
            portal_name, url, allow_demo_override=allow_demo_override
        )

        # Skip processing if fetch returned an error
        if current_data.get("_error"):
            return None

        current_hash = self.compute_hash(current_data)

        latest_snapshot = await db_session.scalar(
            select(RegulationSnapshot)
            .where(RegulationSnapshot.portal_name == portal_name)
            .order_by(RegulationSnapshot.fetched_at.desc())
            .limit(1)
        )

        if latest_snapshot and latest_snapshot.content_hash == current_hash:
            # No change — update heartbeat timestamp
            latest_snapshot.fetched_at = datetime.now(timezone.utc)
            await db_session.commit()
            logger.debug("[%s] No change detected (hash: %s…)", portal_name, current_hash[:12])
            return None

        # Change detected or first-time snapshot
        previous_hash = latest_snapshot.content_hash if latest_snapshot else None
        snapshot = RegulationSnapshot(
            portal_name=portal_name,
            portal_url=url,
            content_hash=current_hash,
            raw_content=current_data,
            change_detected=latest_snapshot is not None,
        )
        db_session.add(snapshot)

        delta = RegulationDelta(
            portal_name=portal_name,
            previous_hash=previous_hash,
            new_hash=current_hash,
            changed_regulation_ids=[],
            delta_summary={},
            affected_business_count=0,
            processed=False,
        )
        db_session.add(delta)
        await db_session.commit()
        await db_session.refresh(delta)

        if latest_snapshot:
            logger.info(
                "[%s] ⚡ CHANGE DETECTED — old hash: %s… → new hash: %s…",
                portal_name,
                (previous_hash or "none")[:12],
                current_hash[:12],
            )
        else:
            logger.info("[%s] First snapshot recorded (hash: %s…)", portal_name, current_hash[:12])

        return delta

    async def check_all_portals(
        self, db_session: AsyncSession, *, allow_demo_override: bool = False
    ) -> list[RegulationDelta]:
        """Check all configured portals sequentially with a small stagger delay."""
        import asyncio

        portals = {
            "gstn": settings.mock_gstn_url,
            "epfo": settings.mock_epfo_url,
            "fssai": settings.mock_fssai_url,
            "pt_states": settings.mock_pt_url,
        }
        deltas: list[RegulationDelta] = []
        for i, (portal_name, url) in enumerate(portals.items()):
            if i > 0:
                await asyncio.sleep(2)  # 2s stagger between portals
            delta = await self.check_portal_for_changes(
                portal_name, url, db_session, allow_demo_override=allow_demo_override
            )
            if delta is not None:
                deltas.append(delta)
        return deltas

    def get_last_poll_results(self) -> dict[str, dict]:
        """Return the most recent poll status for each portal (for the admin dashboard)."""
        return dict(self._last_poll_results)
