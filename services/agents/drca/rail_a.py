from services.knowledge.obligation_graph.graph_builder import ObligationGraphBuilder
from services.knowledge.rag.groq_client import GroqComplianceClient, SYSTEM_PROMPT

import logging

logger = logging.getLogger("drca.rail_a")


class RailA:
    def __init__(self) -> None:
        self.graph_builder = ObligationGraphBuilder()
        self.graph_builder.build_graph()
        self.llm = GroqComplianceClient()

    def compute_rail_a_confidence(self, retrieved_docs: list, query: str) -> float:
        if not retrieved_docs:
            return 0.35
        strong_hits = sum(1 for d in retrieved_docs if (d.get("distance") or 1.0) < 0.5)
        score = min(0.95, 0.55 + strong_hits * 0.08)
        return round(score, 3)

    def generate_response(self, query: str, business_profile: dict, portal_data: dict) -> dict:
        # Try RAG retrieval, but fall back gracefully if embeddings fail
        retrieved = []
        try:
            from services.knowledge.rag.retriever import retrieve_relevant_regulations, build_context_prompt
            retrieved = retrieve_relevant_regulations(query, business_profile, n_results=5)
        except Exception as e:
            logger.warning("RAG retrieval failed (likely embedding model issue), falling back to direct LLM: %s", str(e))

        obligations = self.graph_builder.get_applicable_obligations(business_profile)

        # Build context even without RAG docs
        if retrieved:
            from services.knowledge.rag.retriever import build_context_prompt
            context = build_context_prompt(query, retrieved, business_profile)
        else:
            business_name = business_profile.get("name", "Unknown Business")
            context = f"Business: {business_name}\nQuery: {query}\nNo RAG documents available — answer from general compliance knowledge."

        context += "\n\nApplicable obligations:\n" + "\n".join(
            [f"- {o.node_id}: {o.title} ({o.regulation_id})" for o in obligations[:10]]
        )

        try:
            llm_out = self.llm.generate_compliance_response(SYSTEM_PROMPT, query, context)
        except Exception as e:
            logger.error("LLM call failed: %s", str(e))
            return {
                "response": "I'm currently unable to generate a response. The AI model service is temporarily unavailable. Please try again shortly.",
                "confidence": 0.0,
                "sources": [],
                "regulation_ids": [],
                "domain": "ERROR",
            }

        regulation_ids = [doc["id"] for doc in retrieved]
        sources = [doc.get("metadata", {}).get("source", "unknown") for doc in retrieved]
        domain = retrieved[0].get("metadata", {}).get("domain", "GENERAL") if retrieved else "GENERAL"
        return {
            "response": llm_out["response"],
            "confidence": self.compute_rail_a_confidence(retrieved, query),
            "sources": sources,
            "regulation_ids": regulation_ids,
            "domain": domain,
        }
