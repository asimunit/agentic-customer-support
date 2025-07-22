from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Optional
import uvicorn
from datetime import datetime
import uuid

from backend.models.schemas import (
    CustomerTicket, APIResponse, LearningFeedback,
    TicketCategory, TicketPriority, TicketStatus
)
from backend.workflows.support_workflow import support_workflow
from backend.services.elasticsearch_service import es_service
from backend.services.embedding_service import embedding_service
from backend.services.llm_service import llm_service
from backend.agents.learning_agent import learning_agent
from config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("🚀 Starting Customer Support Resolver API...")

    # Initialize services
    es_connected = await es_service.initialize()
    if not es_connected:
        print(
            "⚠️ Warning: Elasticsearch not connected. Some features may not work.")

    print("✅ API startup complete")

    yield

    # Shutdown
    print("🛑 Shutting down API...")
    await es_service.close()
    print("✅ API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Adaptive Customer Support Resolver",
    description="AI-powered customer support system with multi-agent resolution",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    # Streamlit default
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for demo (in production, use proper database)
tickets_db = {}
resolutions_db = {}
feedback_db = {}


@app.get("/", response_model=APIResponse)
async def root():
    """Root endpoint"""
    return APIResponse(
        success=True,
        message="Adaptive Customer Support Resolver API is running",
        data={"version": "1.0.0", "status": "healthy"}
    )


@app.get("/health", response_model=APIResponse)
async def health_check():
    """Health check endpoint"""
    health_data = {
        "api": "healthy",
        "elasticsearch": "connected" if es_service.client else "disconnected",
        "llm_service": "ready",
        "embedding_service": "ready"
    }

    all_healthy = all(
        status != "disconnected" for status in health_data.values())

    return APIResponse(
        success=all_healthy,
        message="Health check complete",
        data=health_data
    )


@app.post("/tickets", response_model=APIResponse)
async def create_ticket(ticket_data: dict):
    """Create a new customer ticket"""
    try:
        # Generate ticket ID
        ticket_id = str(uuid.uuid4())

        # Create ticket object
        ticket = CustomerTicket(
            id=ticket_id,
            customer_id=ticket_data.get("customer_id", "anonymous"),
            subject=ticket_data["subject"],
            message=ticket_data["message"],
            customer_email=ticket_data.get("customer_email"),
            customer_name=ticket_data.get("customer_name"),
            created_at=datetime.now()
        )

        # Store in memory
        tickets_db[ticket_id] = ticket

        return APIResponse(
            success=True,
            message="Ticket created successfully",
            data={"ticket_id": ticket_id, "ticket": ticket.dict()}
        )

    except Exception as e:
        raise HTTPException(status_code=400,
                            detail=f"Failed to create ticket: {str(e)}")


@app.post("/tickets/{ticket_id}/process", response_model=APIResponse)
async def process_ticket(ticket_id: str):
    """Process a ticket through the AI workflow"""
    try:
        # Get ticket from storage
        if ticket_id not in tickets_db:
            raise HTTPException(status_code=404, detail="Ticket not found")

        ticket = tickets_db[ticket_id]

        # Process through workflow
        result = await support_workflow.process_ticket(ticket)

        # Store resolution
        if "resolution" in result:
            resolutions_db[ticket_id] = result["resolution"]

        # Update ticket status
        if result["workflow_status"] == "escalated":
            ticket.status = TicketStatus.ESCALATED
        elif result["workflow_status"] == "completed":
            ticket.status = TicketStatus.RESOLVED
        else:
            ticket.status = TicketStatus.IN_PROGRESS

        ticket.updated_at = datetime.now()

        return APIResponse(
            success=True,
            message="Ticket processed successfully",
            data=result
        )

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Failed to process ticket: {str(e)}")


@app.get("/tickets/{ticket_id}", response_model=APIResponse)
async def get_ticket(ticket_id: str):
    """Get ticket details"""
    if ticket_id not in tickets_db:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket = tickets_db[ticket_id]
    resolution = resolutions_db.get(ticket_id)

    return APIResponse(
        success=True,
        message="Ticket retrieved successfully",
        data={
            "ticket": ticket.dict(),
            "resolution": resolution
        }
    )


@app.get("/tickets", response_model=APIResponse)
async def list_tickets(limit: int = 10, offset: int = 0):
    """List all tickets"""
    all_tickets = list(tickets_db.values())
    total = len(all_tickets)

    # Simple pagination
    tickets_page = all_tickets[offset:offset + limit]

    tickets_data = []
    for ticket in tickets_page:
        ticket_data = ticket.dict()
        ticket_data["has_resolution"] = ticket.id in resolutions_db
        tickets_data.append(ticket_data)

    return APIResponse(
        success=True,
        message=f"Retrieved {len(tickets_data)} tickets",
        data={
            "tickets": tickets_data,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    )


@app.post("/tickets/{ticket_id}/feedback", response_model=APIResponse)
async def submit_feedback(ticket_id: str, feedback_data: dict):
    """Submit feedback for a resolution"""
    try:
        if ticket_id not in resolutions_db:
            raise HTTPException(status_code=404,
                                detail="No resolution found for this ticket")

        # Create feedback object
        feedback = LearningFeedback(
            ticket_id=ticket_id,
            resolution_id=resolutions_db[ticket_id].get("ticket_id",
                                                        ticket_id),
            was_helpful=feedback_data["was_helpful"],
            customer_rating=feedback_data.get("customer_rating"),
            feedback_text=feedback_data.get("feedback_text"),
            improvement_suggestions=feedback_data.get(
                "improvement_suggestions")
        )

        # Store feedback
        feedback_db[ticket_id] = feedback

        # Process feedback through learning agent
        ticket = tickets_db[ticket_id]
        resolution_data = resolutions_db[ticket_id]

        # Convert resolution data back to Resolution object for learning agent
        from backend.models.schemas import Resolution
        resolution_obj = Resolution(
            ticket_id=resolution_data["ticket_id"],
            response=resolution_data["response"],
            confidence=resolution_data["confidence"],
            knowledge_articles_used=resolution_data["knowledge_articles_used"],
            agent_type=resolution_data["agent_type"]
        )

        learning_result = await learning_agent.process_feedback(
            feedback, ticket, resolution_obj
        )

        return APIResponse(
            success=True,
            message="Feedback submitted successfully",
            data={
                "feedback": feedback.dict(),
                "learning_insights": learning_result
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Failed to submit feedback: {str(e)}")


@app.post("/tickets/batch", response_model=APIResponse)
async def process_batch_tickets(tickets_data: List[dict]):
    """Process multiple tickets in batch"""
    try:
        tickets = []

        # Create ticket objects
        for ticket_data in tickets_data:
            ticket_id = str(uuid.uuid4())
            ticket = CustomerTicket(
                id=ticket_id,
                customer_id=ticket_data.get("customer_id", "anonymous"),
                subject=ticket_data["subject"],
                message=ticket_data["message"],
                customer_email=ticket_data.get("customer_email"),
                customer_name=ticket_data.get("customer_name"),
                created_at=datetime.now()
            )
            tickets.append(ticket)
            tickets_db[ticket_id] = ticket

        # Process batch
        results = await support_workflow.process_batch(tickets)

        # Store resolutions
        for result in results:
            if "resolution" in result and "ticket" in result:
                ticket_id = result["ticket"].id
                resolutions_db[ticket_id] = result["resolution"]

                # Update ticket status
                ticket = tickets_db[ticket_id]
                if result["workflow_status"] == "escalated":
                    ticket.status = TicketStatus.ESCALATED
                elif result["workflow_status"] == "completed":
                    ticket.status = TicketStatus.RESOLVED
                ticket.updated_at = datetime.now()

        return APIResponse(
            success=True,
            message=f"Processed {len(results)} tickets",
            data={"results": results}
        )

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Failed to process batch: {str(e)}")


@app.get("/analytics/dashboard", response_model=APIResponse)
async def get_analytics_dashboard():
    """Get analytics dashboard data"""
    try:
        total_tickets = len(tickets_db)
        total_resolutions = len(resolutions_db)
        total_feedback = len(feedback_db)

        # Calculate resolution rate
        resolution_rate = (
                    total_resolutions / total_tickets * 100) if total_tickets > 0 else 0

        # Calculate satisfaction rate
        helpful_feedback = sum(
            1 for f in feedback_db.values() if f.was_helpful)
        satisfaction_rate = (
                    helpful_feedback / total_feedback * 100) if total_feedback > 0 else 0

        # Category distribution
        category_counts = {}
        for ticket in tickets_db.values():
            cat = ticket.category.value if ticket.category else "unknown"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        # Priority distribution
        priority_counts = {}
        for ticket in tickets_db.values():
            pri = ticket.priority.value if ticket.priority else "unknown"
            priority_counts[pri] = priority_counts.get(pri, 0) + 1

        # Escalation rate
        escalated_count = sum(1 for ticket in tickets_db.values() if
                              ticket.status == TicketStatus.ESCALATED)
        escalation_rate = (
                    escalated_count / total_tickets * 100) if total_tickets > 0 else 0

        dashboard_data = {
            "overview": {
                "total_tickets": total_tickets,
                "total_resolutions": total_resolutions,
                "resolution_rate": round(resolution_rate, 2),
                "satisfaction_rate": round(satisfaction_rate, 2),
                "escalation_rate": round(escalation_rate, 2)
            },
            "distributions": {
                "categories": category_counts,
                "priorities": priority_counts
            },
            "recent_activity": {
                "last_24h_tickets": total_tickets,  # Simplified for demo
                "avg_resolution_time": "15 minutes",  # Mock data
                "top_categories": list(category_counts.keys())[:3]
            }
        }

        return APIResponse(
            success=True,
            message="Dashboard data retrieved successfully",
            data=dashboard_data
        )

    except Exception as e:
        raise HTTPException(status_code=500,
                            detail=f"Failed to get analytics: {str(e)}")


@app.get("/knowledge/search", response_model=APIResponse)
async def search_knowledge(query: str, category: Optional[str] = None,
                           limit: int = 5):
    """Search knowledge base"""
    try:
        from backend.agents.knowledge_agent import knowledge_agent
        from backend.services.embedding_service import embedding_service

        # Generate query embedding
        query_embedding = await embedding_service.create_query_embedding(query)

        # Search using vector similarity
        if category:
            results = await es_service.search_similar(
                query_embedding=query_embedding,
                category=category,
                top_k=limit
            )
        else:
            results = await es_service.hybrid_search(
                query_text=query,
                query_embedding=query_embedding,
                top_k=limit
            )

        # Convert results to API format
        search_results = []
        for result in results:
            search_results.append({
                "id": result.article.id,
                "title": result.article.title,
                "content": result.article.content[:200] + "..." if len(
                    result.article.content) > 200 else result.article.content,
                "category": result.article.category,
                "score": result.score,
                "relevance": result.relevance
            })

        return APIResponse(
            success=True,
            message=f"Found {len(search_results)} articles",
            data={"results": search_results, "query": query}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.FASTAPI_HOST,
        port=settings.FASTAPI_PORT,
        reload=True,
        log_level="info"
    )