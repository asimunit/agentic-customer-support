from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TicketCategory(str, Enum):
    TECHNICAL = "technical"
    BILLING = "billing"
    GENERAL = "general"
    PRODUCT = "product"
    ACCOUNT = "account"

class TicketStatus(str, Enum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"

class CustomerTicket(BaseModel):
    id: Optional[str] = None
    customer_id: str
    subject: str
    message: str
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    status: TicketStatus = TicketStatus.NEW
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None

class ClassificationResult(BaseModel):
    category: TicketCategory
    priority: TicketPriority
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

class KnowledgeArticle(BaseModel):
    id: str
    title: str
    content: str
    category: TicketCategory
    tags: List[str]
    created_at: datetime
    updated_at: Optional[datetime] = None
    resolution_count: int = 0
    rating: Optional[float] = None

class SearchResult(BaseModel):
    article: KnowledgeArticle
    score: float
    relevance: str

class EscalationDecision(BaseModel):
    should_escalate: bool
    reason: str
    escalation_type: Optional[str] = None
    priority_level: str
    confidence: float

class Resolution(BaseModel):
    ticket_id: str
    response: str
    confidence: float
    knowledge_articles_used: List[str]
    created_at: datetime = Field(default_factory=datetime.now)
    agent_type: str = "ai"

class LearningFeedback(BaseModel):
    ticket_id: str
    resolution_id: str
    was_helpful: bool
    customer_rating: Optional[int] = Field(ge=1, le=5, default=None)
    feedback_text: Optional[str] = None
    improvement_suggestions: Optional[str] = None

class WorkflowState(BaseModel):
    ticket: CustomerTicket
    classification: Optional[ClassificationResult] = None
    knowledge_results: List[SearchResult] = []
    escalation_decision: Optional[EscalationDecision] = None
    resolution: Optional[Resolution] = None
    learning_feedback: Optional[LearningFeedback] = None
    workflow_status: str = "started"
    error_messages: List[str] = []

class APIResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: str = ""
    error: Optional[str] = None