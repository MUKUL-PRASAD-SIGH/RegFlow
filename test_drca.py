import asyncio
import sys
sys.path.insert(0, '/app/services/api')

from database import AsyncSessionLocal
from services.agents.drca.comparator import DRCAComparator

async def test():
    async with AsyncSessionLocal() as db:
        c = DRCAComparator()
        res = await c.run_full_drca('What is GST?', {'id': '11111111-1111-1111-1111-111111111001'}, {}, db)
        print(res)

asyncio.run(test())
