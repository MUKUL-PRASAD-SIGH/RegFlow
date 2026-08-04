import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import and_, select

from services.agents.gst_agent.readiness_checker import GSTReadinessChecker
from services.agents.irda.orchestrator import IRDAOrchestrator
from services.agents.payroll_agent.calculator import PayrollCalculator
from services.api.database import AsyncSessionLocal, Business, HITLQueue

logger = logging.getLogger("scheduler")


class SchedulerJobs:
    def __init__(self, graph_builder, ws_manager) -> None:
        self.async_scheduler = AsyncIOScheduler()
        self.background_scheduler = BackgroundScheduler()
        self.irda = IRDAOrchestrator()
        self.gst_checker = GSTReadinessChecker()
        self.payroll_calculator = PayrollCalculator()
        self.graph_builder = graph_builder
        self.ws_manager = ws_manager
        self._last_poll_at: datetime | None = None
        self._last_poll_result: dict | None = None

    async def poll_portals(self) -> None:
        """Live-scrape all Vercel portals — no Redis override, always hits real URLs."""
        logger.info("Scheduled portal poll starting…")
        try:
            async with AsyncSessionLocal() as session:
                result = await self.irda.run_cycle(
                    session, self.graph_builder, self.ws_manager,
                    allow_demo_override=False,  # Always hit live URLs for scheduled polls
                )
                self._last_poll_at = datetime.now(timezone.utc)
                self._last_poll_result = result

                # Broadcast portal-unreachable alerts via WebSocket
                for portal_name, status in result.get("poll_statuses", {}).items():
                    if status.get("status") == "error":
                        await self.ws_manager.broadcast({
                            "event": "portal_unreachable",
                            "portal": portal_name,
                            "error": status.get("error", "Unknown error"),
                            "message": f"⚠️ Portal {portal_name} is unreachable: {status.get('error', 'Unknown error')}",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        })

                changes = result.get("changes_detected", 0)
                if changes > 0:
                    logger.info("Poll complete — %d changes detected", changes)
                else:
                    logger.debug("Poll complete — no changes")
        except Exception as e:
            logger.error("Portal poll failed: %s", str(e), exc_info=True)

    async def compute_due_dates(self) -> None:
        async with AsyncSessionLocal() as session:
            businesses = (await session.scalars(select(Business))).all()
            for b in businesses:
                await self.payroll_calculator.compute_monthly_obligations(str(b.id), datetime.now().strftime("%Y-%m"), session, {})

    async def gst_readiness(self) -> None:
        async with AsyncSessionLocal() as session:
            businesses = (await session.scalars(select(Business).where(Business.gst_registered.is_(True)))).all()
            for b in businesses:
                await self.gst_checker.compute_readiness_score(str(b.id), datetime.now().strftime("%Y-%m"), session, {})

    async def hitl_reminder(self) -> None:
        async with AsyncSessionLocal() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
            pending = (
                await session.scalars(
                    select(HITLQueue).where(and_(HITLQueue.status == "pending", HITLQueue.escalated_at <= cutoff))
                )
            ).all()
            if pending:
                await self.ws_manager.broadcast(
                    {
                        "event": "hitl_reminder",
                        "pending_count": len(pending),
                        "message": "HITL items pending for over 1 hour require review.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )

    def get_poll_status(self) -> dict:
        """Return last poll status for the admin dashboard."""
        return {
            "last_poll_at": self._last_poll_at.isoformat() if self._last_poll_at else None,
            "last_result": self._last_poll_result,
            "poll_interval_seconds": 30,
            "next_poll_at": (
                (self._last_poll_at + timedelta(seconds=30)).isoformat()
                if self._last_poll_at
                else None
            ),
        }

    def start(self) -> None:
        # Portal polling every 30s for responsive change detection
        self.async_scheduler.add_job(self.poll_portals, "interval", seconds=30, id="poll_portals")
        self.async_scheduler.add_job(self.compute_due_dates, "cron", hour=9, minute=0, id="compute_due_dates")
        self.async_scheduler.add_job(self.gst_readiness, "cron", hour=10, minute=0, id="gst_readiness")
        self.async_scheduler.add_job(self.hitl_reminder, "interval", minutes=30, id="hitl_reminder")
        self.async_scheduler.start()
        self.background_scheduler.start()
        logger.info("Scheduler started — portal polling every 30s")
