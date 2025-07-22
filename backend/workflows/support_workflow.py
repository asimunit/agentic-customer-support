from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
import asyncio

from backend.models.schemas import WorkflowState, CustomerTicket
from backend.agents.classifier_agent import classifier_agent
from backend.agents.knowledge_agent import knowledge_agent
from backend.agents.escalation_agent import escalation_agent
from backend.agents.resolution_agent import resolution_agent
from backend.agents.learning_agent import learning_agent


class SupportWorkflowState(TypedDict):
    """State for the support workflow"""
    ticket: CustomerTicket
    classification: Dict[str, Any]
    knowledge_results: List[Dict[str, Any]]
    escalation_decision: Dict[str, Any]
    resolution: Dict[str, Any]
    workflow_status: str
    error_messages: List[str]
    metadata: Dict[str, Any]


class CustomerSupportWorkflow:
    """LangGraph workflow for processing customer support tickets"""

    def __init__(self):
        self.workflow = self._build_workflow()

    def _build_workflow(self) -> StateGraph:
        """Build the LangGraph workflow"""

        # Create the state graph
        workflow = StateGraph(SupportWorkflowState)

        # Add nodes
        workflow.add_node("classify", self._classify_node)
        workflow.add_node("search_knowledge", self._search_knowledge_node)
        workflow.add_node("check_escalation", self._check_escalation_node)
        workflow.add_node("generate_resolution",
                          self._generate_resolution_node)
        workflow.add_node("escalate_ticket", self._escalate_ticket_node)
        workflow.add_node("finalize", self._finalize_node)

        # Define the workflow edges
        workflow.set_entry_point("classify")

        workflow.add_edge("classify", "search_knowledge")
        workflow.add_edge("search_knowledge", "check_escalation")

        # Conditional edge based on escalation decision
        workflow.add_conditional_edges(
            "check_escalation",
            self._should_escalate,
            {
                "escalate": "escalate_ticket",
                "resolve": "generate_resolution"
            }
        )

        workflow.add_edge("generate_resolution", "finalize")
        workflow.add_edge("escalate_ticket", "finalize")
        workflow.add_edge("finalize", END)

        return workflow.compile()

    async def _classify_node(self,
                             state: SupportWorkflowState) -> SupportWorkflowState:
        """Classify the customer ticket"""
        try:
            ticket = state["ticket"]

            # Classify the ticket
            classification_result = await classifier_agent.classify_ticket(
                ticket)

            # Get additional insights
            insights = await classifier_agent.get_classification_insights(
                ticket)

            state["classification"] = {
                "category": classification_result.category.value,
                "priority": classification_result.priority.value,
                "confidence": classification_result.confidence,
                "reasoning": classification_result.reasoning,
                "insights": insights
            }

            state["workflow_status"] = "classified"
            print(
                f"✓ Classified ticket as {classification_result.category.value}/{classification_result.priority.value}")

        except Exception as e:
            error_msg = f"Classification failed: {str(e)}"
            state["error_messages"].append(error_msg)
            state["classification"] = {
                "category": "general",
                "priority": "medium",
                "confidence": 0.3,
                "reasoning": error_msg
            }

        return state

    async def _search_knowledge_node(self,
                                     state: SupportWorkflowState) -> SupportWorkflowState:
        """Search the knowledge base for relevant articles"""
        try:
            ticket = state["ticket"]
            classification = state["classification"]

            # Convert classification back to object for agent
            from backend.models.schemas import ClassificationResult, \
                TicketCategory, TicketPriority
            classification_obj = ClassificationResult(
                category=TicketCategory(classification["category"]),
                priority=TicketPriority(classification["priority"]),
                confidence=classification["confidence"],
                reasoning=classification["reasoning"]
            )

            # Search knowledge base
            search_results = await knowledge_agent.search_knowledge_base(
                ticket, classification_obj, search_type="hybrid"
            )

            # Get search summary
            search_summary = await knowledge_agent.get_article_summary(
                search_results)

            # Convert results to serializable format
            state["knowledge_results"] = [
                {
                    "article_id": result.article.id,
                    "title": result.article.title,
                    "content": result.article.content,
                    "category": result.article.category,
                    "score": result.score,
                    "relevance": result.relevance
                }
                for result in search_results
            ]

            state["metadata"]["search_summary"] = search_summary
            state["workflow_status"] = "knowledge_searched"
            print(f"✓ Found {len(search_results)} relevant knowledge articles")

        except Exception as e:
            error_msg = f"Knowledge search failed: {str(e)}"
            state["error_messages"].append(error_msg)
            state["knowledge_results"] = []

        return state

    async def _check_escalation_node(self,
                                     state: SupportWorkflowState) -> SupportWorkflowState:
        """Check if the ticket should be escalated"""
        try:
            ticket = state["ticket"]
            classification = state["classification"]
            knowledge_results = state["knowledge_results"]

            # Convert data back to objects
            from backend.models.schemas import ClassificationResult, \
                TicketCategory, TicketPriority, SearchResult, KnowledgeArticle

            classification_obj = ClassificationResult(
                category=TicketCategory(classification["category"]),
                priority=TicketPriority(classification["priority"]),
                confidence=classification["confidence"],
                reasoning=classification["reasoning"]
            )

            # Convert search results back to objects
            search_results_obj = []
            for result_data in knowledge_results:
                article = KnowledgeArticle(
                    id=result_data["article_id"],
                    title=result_data["title"],
                    content=result_data["content"],
                    category=result_data["category"],
                    tags=[],
                    created_at=state.get("metadata", {}).get("current_time",
                                                             "2024-01-01T00:00:00")
                )
                search_result = SearchResult(
                    article=article,
                    score=result_data["score"],
                    relevance=result_data["relevance"]
                )
                search_results_obj.append(search_result)

            # Check escalation
            escalation_decision = await escalation_agent.evaluate_escalation(
                ticket, classification_obj, search_results_obj
            )

            # Get routing information
            routing_info = await escalation_agent.get_escalation_routing(
                escalation_decision)

            state["escalation_decision"] = {
                "should_escalate": escalation_decision.should_escalate,
                "reason": escalation_decision.reason,
                "escalation_type": escalation_decision.escalation_type,
                "priority_level": escalation_decision.priority_level,
                "confidence": escalation_decision.confidence,
                "routing": routing_info
            }

            state["workflow_status"] = "escalation_checked"
            escalation_status = "escalated" if escalation_decision.should_escalate else "resolved by AI"
            print(f"✓ Escalation check complete: {escalation_status}")

        except Exception as e:
            error_msg = f"Escalation check failed: {str(e)}"
            state["error_messages"].append(error_msg)
            # Default to escalation for safety
            state["escalation_decision"] = {
                "should_escalate": True,
                "reason": error_msg,
                "escalation_type": "technical",
                "priority_level": "standard",
                "confidence": 0.3
            }

        return state

    async def _generate_resolution_node(self,
                                        state: SupportWorkflowState) -> SupportWorkflowState:
        """Generate AI resolution for the ticket"""
        try:
            ticket = state["ticket"]
            classification = state["classification"]
            knowledge_results = state["knowledge_results"]
            escalation_decision = state["escalation_decision"]

            # Convert data back to objects for resolution agent
            from backend.models.schemas import (
                ClassificationResult, TicketCategory, TicketPriority,
                SearchResult, KnowledgeArticle, EscalationDecision
            )

            classification_obj = ClassificationResult(
                category=TicketCategory(classification["category"]),
                priority=TicketPriority(classification["priority"]),
                confidence=classification["confidence"],
                reasoning=classification["reasoning"]
            )

            escalation_obj = EscalationDecision(
                should_escalate=escalation_decision["should_escalate"],
                reason=escalation_decision["reason"],
                escalation_type=escalation_decision.get("escalation_type"),
                priority_level=escalation_decision["priority_level"],
                confidence=escalation_decision["confidence"]
            )

            # Convert search results
            search_results_obj = []
            for result_data in knowledge_results:
                article = KnowledgeArticle(
                    id=result_data["article_id"],
                    title=result_data["title"],
                    content=result_data["content"],
                    category=result_data["category"],
                    tags=[],
                    created_at=state.get("metadata", {}).get("current_time",
                                                             "2024-01-01T00:00:00")
                )
                search_result = SearchResult(
                    article=article,
                    score=result_data["score"],
                    relevance=result_data["relevance"]
                )
                search_results_obj.append(search_result)

            # Generate resolution
            resolution = await resolution_agent.generate_resolution(
                ticket, classification_obj, search_results_obj, escalation_obj
            )

            state["resolution"] = {
                "ticket_id": resolution.ticket_id,
                "response": resolution.response,
                "confidence": resolution.confidence,
                "knowledge_articles_used": resolution.knowledge_articles_used,
                "agent_type": resolution.agent_type,
                "created_at": resolution.created_at.isoformat()
            }

            state["workflow_status"] = "resolved"
            print(
                f"✓ Generated AI resolution with confidence: {resolution.confidence:.2f}")

        except Exception as e:
            error_msg = f"Resolution generation failed: {str(e)}"
            state["error_messages"].append(error_msg)
            # Fallback resolution
            state["resolution"] = {
                "ticket_id": ticket.id or "unknown",
                "response": "I apologize, but I'm experiencing technical difficulties. A human agent will assist you shortly.",
                "confidence": 0.1,
                "knowledge_articles_used": [],
                "agent_type": "fallback"
            }

        return state

    async def _escalate_ticket_node(self,
                                    state: SupportWorkflowState) -> SupportWorkflowState:
        """Handle ticket escalation"""
        try:
            ticket = state["ticket"]
            escalation_decision = state["escalation_decision"]

            # Generate escalation response
            from backend.models.schemas import EscalationDecision
            escalation_obj = EscalationDecision(
                should_escalate=escalation_decision["should_escalate"],
                reason=escalation_decision["reason"],
                escalation_type=escalation_decision.get("escalation_type"),
                priority_level=escalation_decision["priority_level"],
                confidence=escalation_decision["confidence"]
            )

            # Use resolution agent to generate escalation response
            classification = state["classification"]
            from backend.models.schemas import ClassificationResult, \
                TicketCategory, TicketPriority
            classification_obj = ClassificationResult(
                category=TicketCategory(classification["category"]),
                priority=TicketPriority(classification["priority"]),
                confidence=classification["confidence"],
                reasoning=classification["reasoning"]
            )

            resolution = await resolution_agent._generate_escalation_response(
                ticket, escalation_obj
            )

            state["resolution"] = {
                "ticket_id": resolution.ticket_id,
                "response": resolution.response,
                "confidence": resolution.confidence,
                "knowledge_articles_used": resolution.knowledge_articles_used,
                "agent_type": resolution.agent_type,
                "created_at": resolution.created_at.isoformat()
            }

            state["workflow_status"] = "escalated"
            print(
                f"✓ Ticket escalated to {escalation_decision.get('escalation_type', 'general')} team")

        except Exception as e:
            error_msg = f"Escalation failed: {str(e)}"
            state["error_messages"].append(error_msg)
            # Fallback escalation response
            state["resolution"] = {
                "ticket_id": ticket.id or "unknown",
                "response": "Your request has been escalated to our specialist team. Someone will contact you shortly.",
                "confidence": 0.8,
                "knowledge_articles_used": [],
                "agent_type": "escalation_fallback"
            }

        return state

    async def _finalize_node(self,
                             state: SupportWorkflowState) -> SupportWorkflowState:
        """Finalize the workflow"""
        state["workflow_status"] = "completed"

        # Add completion metadata
        if "metadata" not in state:
            state["metadata"] = {}

        state["metadata"][
            "completed_at"] = "2024-01-01T00:00:00"  # Would be datetime.now().isoformat()
        state["metadata"]["total_errors"] = len(
            state.get("error_messages", []))

        # Log completion
        if state.get("error_messages"):
            print(
                f"⚠ Workflow completed with {len(state['error_messages'])} errors")
        else:
            print("✓ Workflow completed successfully")

        return state

    def _should_escalate(self, state: SupportWorkflowState) -> str:
        """Conditional function to determine if ticket should be escalated"""
        escalation_decision = state.get("escalation_decision", {})
        return "escalate" if escalation_decision.get("should_escalate",
                                                     False) else "resolve"

    async def process_ticket(self, ticket: CustomerTicket) -> Dict[str, Any]:
        """Process a customer ticket through the workflow"""
        try:
            # Initialize state
            initial_state = SupportWorkflowState(
                ticket=ticket,
                classification={},
                knowledge_results=[],
                escalation_decision={},
                resolution={},
                workflow_status="started",
                error_messages=[],
                metadata={"started_at": "2024-01-01T00:00:00"}
                # Would be datetime.now().isoformat()
            )

            print(f"🎫 Processing ticket: {ticket.subject}")

            # Run the workflow
            final_state = await self.workflow.ainvoke(initial_state)

            print(
                f"✅ Ticket processing complete: {final_state['workflow_status']}")

            return dict(final_state)

        except Exception as e:
            error_msg = f"Workflow execution failed: {str(e)}"
            print(f"❌ {error_msg}")

            # Return error state
            return {
                "ticket": ticket,
                "workflow_status": "failed",
                "error_messages": [error_msg],
                "resolution": {
                    "response": "I apologize for the technical difficulty. Please contact our support team directly.",
                    "confidence": 0.1,
                    "agent_type": "error_fallback"
                }
            }

    async def process_batch(self, tickets: List[CustomerTicket]) -> List[
        Dict[str, Any]]:
        """Process multiple tickets in batch"""
        print(f"📦 Processing batch of {len(tickets)} tickets")

        # Process tickets concurrently (with reasonable limit)
        semaphore = asyncio.Semaphore(3)  # Limit concurrent processing

        async def process_with_semaphore(ticket):
            async with semaphore:
                return await self.process_ticket(ticket)

        results = await asyncio.gather(
            *[process_with_semaphore(ticket) for ticket in tickets],
            return_exceptions=True
        )

        # Handle any exceptions in results
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    "ticket": tickets[i],
                    "workflow_status": "failed",
                    "error_messages": [str(result)],
                    "resolution": {
                        "response": "Processing failed due to technical error.",
                        "confidence": 0.1,
                        "agent_type": "batch_error"
                    }
                })
            else:
                processed_results.append(result)

        print(
            f"✅ Batch processing complete: {len(processed_results)} tickets processed")
        return processed_results


# Global workflow instance
support_workflow = CustomerSupportWorkflow()