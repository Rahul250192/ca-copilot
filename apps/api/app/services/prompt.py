from typing import List, Dict
from app.models.models import Scope, DocEmbedding

class PromptService:
    @staticmethod
    def build_specialist_system_prompt(kits: List[str]) -> str:
        kit_names = ", ".join(kits)
        return (
            f"You are a specialized CA assistant focused on: {kit_names}.\n"
            "Your primary goal is to provide accurate information based on the provided hierarchy of knowledge.\n\n"
            "KNOWLEDGE HIERARCHY:\n"
            "1. SPECIALIST KNOWLEDGE (KIT): Most trusted. If you find the answer here, start your response with '[HIGH CONFIDENCE - SPECIALIST KNOWLEDGE]'.\n"
            "2. FIRM/CLIENT KNOWLEDGE: Internal facts. If you find the answer here but NOT in the Kit, start with '[ADVISORY - INTERNAL/CLIENT DATA]'.\n"
            "3. GENERAL KNOWLEDGE: Only as a last resort. If you use this, start with '[LOW CONFIDENCE - GENERAL KNOWLEDGE]'.\n\n"
            "CONSTRAINTS:\n"
            "- Always prioritize information from higher in the hierarchy.\n"
            "- Mention which 'layer' or 'kit' your answer is coming from.\n"
            "- Keep responses professional, precise, and cited."
        )

    @staticmethod
    def format_context_for_prompt(docs: List[DocEmbedding]) -> str:
        # Group by scope
        grouped = {
            Scope.KIT.value: [],
            Scope.FIRM.value: [],
            Scope.CLIENT.value: []
        }
        for d in docs:
            grouped[d.document.scope.value].append(d.chunk_text)

        context_parts = []
        if grouped[Scope.KIT.value]:
            context_parts.append("### SPECIALIST KNOWLEDGE (KITS):\n" + "\n".join(grouped[Scope.KIT.value]))
        if grouped[Scope.FIRM.value]:
            context_parts.append("### FIRM KNOWLEDGE:\n" + "\n".join(grouped[Scope.FIRM.value]))
        if grouped[Scope.CLIENT.value]:
            context_parts.append("### CLIENT CONTEXT:\n" + "\n".join(grouped[Scope.CLIENT.value]))

        return "\n\n".join(context_parts)
