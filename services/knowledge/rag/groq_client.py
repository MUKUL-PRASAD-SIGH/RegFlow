import os
from groq import Groq

from services.api.config import settings

SYSTEM_PROMPT = (
    "You are a compliance expert for Indian SMBs. Always cite which regulation you are referencing. "
    "Never make up due dates or rates — use only the provided context. If uncertain, say so explicitly."
)

class GroqComplianceClient:
    def __init__(self) -> None:
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = settings.groq_model

    def generate_compliance_response(self, system_prompt: str, user_query: str, context: str) -> dict:
        prompt = f"Context:\n{context}\n\nUser Query:\n{user_query}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        
        text = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else len(prompt.split()) + len(text.split())
        return {"response": text, "model_used": self.model, "tokens_used": tokens}

    def generate_plain_language_card(self, regulation_changes: list, business_profile: dict) -> str:
        business_name = business_profile.get("name", "the business")
        change_text = "; ".join([str(c) for c in regulation_changes])
        prompt = f"Create a concise plain-language compliance card for {business_name}. Changes: {change_text}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content

    def generate_audit_packet_summary(self, audit_entries: list) -> str:
        prompt = f"Summarize these audit entries for an auditor:\n{audit_entries[:30]}"
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
        )
        return response.choices[0].message.content
