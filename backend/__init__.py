# backend/__init__.py
"""
Adaptive Customer Support Resolver Backend

Multi-agent AI system for customer support automation.
"""

__version__ = "1.0.0"

# backend/agents/__init__.py
"""
AI Agents for Customer Support Resolution

This package contains specialized agents for different aspects of customer support:
- Classifier Agent: Categorizes and prioritizes tickets
- Knowledge Agent: Searches documentation and solutions
- Escalation Agent: Determines escalation needs
- Resolution Agent: Generates customer responses
- Learning Agent: Improves system based on feedback
"""

from backend.agents.classifier_agent import classifier_agent
from backend.agents.knowledge_agent import knowledge_agent
from backend.agents.escalation_agent import escalation_agent
from backend.agents.resolution_agent import resolution_agent
from backend.agents.learning_agent import learning_agent

__all__ = [
    "classifier_agent",
    "knowledge_agent",
    "escalation_agent",
    "resolution_agent",
    "learning_agent"
]

# backend/services/__init__.py
"""
Core Services for Customer Support System

This package contains the core services that power the customer support system:
- LLM Service: Google Gemini integration
- Embedding Service: MxBai embeddings for vector search
- Elasticsearch Service: Vector database operations
"""

from backend.services.llm_service import llm_service
from backend.services.embedding_service import embedding_service
from backend.services.elasticsearch_service import es_service

__all__ = [
    "llm_service",
    "embedding_service",
    "es_service"
]

# backend/models/__init__.py
"""
Data Models and Schemas

Pydantic models for data validation and serialization.
"""

from backend.models.schemas import (
    CustomerTicket,
    ClassificationResult,
    KnowledgeArticle,
    SearchResult,
    EscalationDecision,
    Resolution,
    LearningFeedback,
    WorkflowState,
    APIResponse
)

__all__ = [
    "CustomerTicket",
    "ClassificationResult",
    "KnowledgeArticle",
    "SearchResult",
    "EscalationDecision",
    "Resolution",
    "LearningFeedback",
    "WorkflowState",
    "APIResponse"
]

# backend/workflows/__init__.py
"""
LangGraph Workflows

This package contains workflow definitions using LangGraph for orchestrating
the multi-agent customer support resolution process.
"""

from backend.workflows.support_workflow import support_workflow

__all__ = ["support_workflow"]