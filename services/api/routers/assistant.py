import asyncio
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db, Business
from models import ChatMessage, ChatResponse
from services.agents.drca.comparator import DRCAComparator

router = APIRouter(prefix="/assistant", tags=["assistant"])

@router.post("/chat", response_model=ChatResponse)
async def rag_chat(payload: ChatMessage, db: AsyncSession = Depends(get_db)):
    drca_comparator = DRCAComparator()
    # 1. Load Business Context
    business = await db.scalar(select(Business).where(Business.id == payload.business_id))
    raw = {k: v for k, v in (business.__dict__ if business else {}).items() if not k.startswith("_")}
    # Make JSON-safe for CAAL ledger storage (UUID, datetime, Decimal → str)
    business_profile = {}
    for k, v in raw.items():
        if hasattr(v, "hex"):  # UUID
            business_profile[k] = str(v)
        elif hasattr(v, "isoformat"):  # datetime
            business_profile[k] = v.isoformat()
        elif isinstance(v, (int, float, bool, str, type(None))):
            business_profile[k] = v
        else:
            business_profile[k] = str(v)

    # 2. Run the Dual-Rail Compliance Architecture
    drca_result = await drca_comparator.run_full_drca(
        query=payload.message,
        business_profile=business_profile,
        portal_data={},
        db_session=db
    )
    
    # 3. Format Response
    # If HITL was required, sources can indicate the queue
    sources = ["drca_rail_a"]
    if drca_result.get("hitl_required"):
        sources.append("hitl_queue")

    return ChatResponse(
        response=drca_result.get("final_response", ""),
        confidence_score=drca_result.get("confidence_score", 0.0),
        sources=sources,
        rail_agreement=drca_result.get("rail_agreement", False),
        hitl_escalated=drca_result.get("hitl_required", False),
    )
