from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq

from apps.api.app.core.config import settings


def get_llm() -> BaseChatModel:
    """Get configured LLM instance using Groq."""
    return ChatGroq(
        groq_api_key=settings.groq_api_key,
        model_name=settings.model_name,
        temperature=0.1,
        max_tokens=4096,
    )
