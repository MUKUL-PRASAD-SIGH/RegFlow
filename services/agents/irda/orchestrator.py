import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select

from services.agents.caal.ledger_writer import LedgerWriter
from services.agents.irda.delta_extractor import DeltaExtractor
from services.agents.irda.notifier import DeltaNotifier
from services.agents.irda.watcher import RegulationWatcher
from services.api.database import Business, RegulationSnapshot

logger = logging.getLogger("irda.orchestrator")


from services.agents.coce.cascade_engine import CascadeEngine

class IRDAOrchestrator:
    def __init__(self) -> None:
        self.watcher = RegulationWatcher()
        self.extractor = DeltaExtractor()
        self.notifier = DeltaNotifier()
        self.ledger = LedgerWriter()
        self.cascade = CascadeEngine()

    async def run_cycle(
        self, db_session, graph_builder, ws_manager, *, allow_demo_override: bool = False
    ) -> dict:
        """
        Run a full IRDA scraping cycle across all portals.

        Args:
            allow_demo_override: If True, check Redis for demo overrides
                before hitting the live URL. Only the demo trigger endpoint
                should pass True here.
        """
        cycle_start = time.monotonic()
        portal_results: list[dict] = []

        deltas = await self.watcher.check_all_portals(
            db_session, allow_demo_override=allow_demo_override
        )
        total_notified = 0

        for delta in deltas:
            portal_start = time.monotonic()
            try:
                old_snapshot = await db_session.scalar(
                    select(RegulationSnapshot)
                    .where(
                        RegulationSnapshot.portal_name == delta.portal_name,
                        RegulationSnapshot.content_hash == delta.previous_hash,
                    )
                    .limit(1)
                )
                new_snapshot = await db_session.scalar(
                    select(RegulationSnapshot)
                    .where(
                        RegulationSnapshot.portal_name == delta.portal_name,
                        RegulationSnapshot.content_hash == delta.new_hash,
                    )
                    .limit(1)
                )
                old_content = old_snapshot.raw_content if old_snapshot else {"regulations": []}
                new_content = new_snapshot.raw_content if new_snapshot else {"regulations": []}

                changed_ids = self.extractor.extract_changed_regulations(old_content, new_content)
                summary = self.extractor.build_delta_summary(old_content, new_content, changed_ids)
                summary["portal"] = delta.portal_name
                summary["delta_id"] = str(delta.id)

                self.extractor.update_obligation_graph(summary, graph_builder)
                all_businesses = (await db_session.scalars(select(Business))).all()
                affected = self.notifier.find_affected_businesses(
                    changed_ids, [b.__dict__ for b in all_businesses], graph_builder
                )
                created = await self.notifier.create_compliance_alerts(
                    affected, summary, str(delta.id), db_session
                )
                total_notified += created

                # Cascade to obligations
                if changed_ids:
                    cascade_result = await self.cascade.evaluate_regulation_change_cascade(changed_ids, all_businesses, db_session)
                    logger.info("Cascade complete for delta %s: %d obligations created/updated.", str(delta.id), cascade_result.get("created", 0) + cascade_result.get("updated", 0))

                delta.changed_regulation_ids = changed_ids
                delta.delta_summary = summary
                delta.affected_business_count = len(affected)
                delta.processed = True
                await db_session.commit()

                await self.notifier.broadcast_websocket_event(summary, len(affected), ws_manager)
                await self.ledger.write_entry(
                    agent_name="irda",
                    action_type="regulation_delta_processed",
                    business_id=affected[0] if affected else None,
                    obligation_id=None,
                    action_payload=summary,
                    confidence_score=0.99,
                    rail_agreement=True,
                    regulation_ids=changed_ids,
                    business_state_snapshot={"affected_count": len(affected)},
                    source_citations=[{"portal": delta.portal_name}],
                    db_session=db_session,
                )

                portal_ms = round((time.monotonic() - portal_start) * 1000)
                portal_results.append({
                    "portal": delta.portal_name,
                    "changed_regulations": changed_ids,
                    "affected_businesses": len(affected),
                    "alerts_created": created,
                    "processing_ms": portal_ms,
                })
                logger.info(
                    "[%s] Delta processed — %d changed regs, %d businesses affected, %dms",
                    delta.portal_name,
                    len(changed_ids),
                    len(affected),
                    portal_ms,
                )

            except Exception as e:
                logger.error(
                    "[%s] Error processing delta: %s", delta.portal_name, str(e), exc_info=True
                )
                portal_results.append({
                    "portal": delta.portal_name,
                    "error": str(e),
                })

        cycle_ms = round((time.monotonic() - cycle_start) * 1000)
        result = {
            "portals_checked": 4,
            "changes_detected": len(deltas),
            "businesses_notified": total_notified,
            "cycle_duration_ms": cycle_ms,
            "portal_details": portal_results,
            "poll_statuses": self.watcher.get_last_poll_results(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            "IRDA cycle complete — %d changes across %d portals, %d businesses notified, %dms total",
            len(deltas),
            4,
            total_notified,
            cycle_ms,
        )
        return result

    def schedule(self, interval_seconds: int):
        async def _job(db_session, graph_builder, ws_manager):
            return await self.run_cycle(db_session, graph_builder, ws_manager)

        return {"interval_seconds": interval_seconds, "job": _job}
