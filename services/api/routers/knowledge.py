import networkx as nx
from dataclasses import asdict
from fastapi import APIRouter
from fastapi.requests import Request
from services.knowledge.rag.vector_store import RegulationVectorStore

router = APIRouter(prefix="/knowledge", tags=["knowledge"])

@router.get("/graph")
async def get_graph(request: Request):
    graph: nx.DiGraph = request.app.state.obligation_graph
    
    nodes = []
    edges = []
    
    for node_id, attrs in graph.nodes(data=True):
        node_obj = attrs.get("data")
        if node_obj is not None:
            try:
                node_dict = asdict(node_obj)
            except Exception:
                node_dict = {"node_id": node_id}
            nodes.append(node_dict)
        else:
            nodes.append({
                "node_id": node_id,
                "domain": attrs.get("domain", node_id),
                "title": attrs.get("title", f"{node_id} Obligation"),
            })
        
    for u, v, meta in graph.edges(data=True):
        edges.append({
            "source": u,
            "target": v,
            "edge_type": meta.get("edge_type", "dependency")
        })
        
    return {"nodes": nodes, "edges": edges}

@router.get("/rag/stats")
async def get_rag_stats():
    from pathlib import Path
    persist_dir = Path(__file__).resolve().parents[2] / "chroma_db"
    try:
        store = RegulationVectorStore(str(persist_dir))
        return store.get_collection_stats()
    except Exception as e:
        return {"name": "rgai_regulations", "count": 0, "error": str(e)}
