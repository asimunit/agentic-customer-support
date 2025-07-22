from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.models.schemas import (
    CustomerTicket, ClassificationResult, SearchResult,
    EscalationDecision, Resolution
)
from backend.services.llm_service import llm_service
from backend.services.elasticsearch_service import es_service


class ResolutionAgent:
    """Agent responsible for generating responses to customer tickets"""

    def __init__(self):
        self.name = "Resolution Agent"
        self.max_response_length = 1000
        self.min_confidence_threshold = 0.3

    async def generate_resolution(self,
                                  ticket: CustomerTicket,
                                  classification: ClassificationResult,
                                  search_results: List[SearchResult],
                                  escalation_decision: EscalationDecision) -> Resolution:
        """
        Generate a comprehensive resolution for the customer ticket
        """
        try:
            if escalation_decision.should_escalate:
                return await self._generate_escalation_response(
                    ticket, escalation_decision
                )
            else:
                return await self._generate_ai_resolution(
                    ticket, classification, search_results
                )
        except Exception as e:
            # Fallback resolution
            return Resolution(
                ticket_id=ticket.id or "unknown",
                response=self._get_fallback_response(ticket),
                confidence=0.2,
                knowledge_articles_used=[],
                agent_type="ai_fallback"
            )

    async def _generate_ai_resolution(self,
                                      ticket: CustomerTicket,
                                      classification: ClassificationResult,
                                      search_results: List[
                                          SearchResult]) -> Resolution:
        """
        Generate AI-powered resolution using knowledge base
        """
        # Prepare knowledge articles for LLM
        relevant_articles = []
        article_ids = []

        for result in search_results[:3]:  # Use top 3 results
            relevant_articles.append({
                "title": result.article.title,
                "content": result.article.content,
                "score": result.score
            })
            article_ids.append(result.article.id)

        # Generate response using LLM
        response_text = await llm_service.generate_resolution(
            {
                "subject": ticket.subject,
                "message": ticket.message,
                "category": classification.category.value,
                "priority": classification.priority.value
            },
            relevant_articles
        )

        # Calculate confidence based on multiple factors
        confidence = self._calculate_resolution_confidence(
            classification, search_results, len(response_text)
        )

        # Post-process response
        final_response = self._post_process_response(
            response_text, ticket, classification
        )

        # Update article usage statistics
        for article_id in article_ids:
            await es_service.update_article_stats(article_id,
                                                  increment_resolution=True)

        return Resolution(
            ticket_id=ticket.id or "generated",
            response=final_response,
            confidence=confidence,
            knowledge_articles_used=article_ids,
            agent_type="ai"
        )

    async def _generate_escalation_response(self,
                                            ticket: CustomerTicket,
                                            escalation_decision: EscalationDecision) -> Resolution:
        """
        Generate response for escalated tickets
        """
        escalation_messages = {
            "technical": {
                "acknowledgment": "I understand you're experiencing a technical issue that is impacting your operations.",
                "action": "I've immediately escalated this ticket to our senior engineering team who specialize in complex technical integrations and system issues.",
                "next_steps": "A senior technical specialist will contact you within the next 15-30 minutes to begin immediate troubleshooting."
            },
            "billing": {
                "acknowledgment": "Thank you for contacting us about your billing concern.",
                "action": "I want to ensure this is handled properly, so I'm transferring you to our billing specialists who can access your account details and process any necessary adjustments.",
                "next_steps": "A billing specialist will review your account and contact you within 30-45 minutes."
            },
            "management": {
                "acknowledgment": "I understand your concern and want to ensure you receive the best possible service.",
                "action": "I'm connecting you with a customer success manager who can give your issue the personal attention it deserves.",
                "next_steps": "A customer success manager will contact you within 45-60 minutes to address your concerns directly."
            },
            "legal": {
                "acknowledgment": "Thank you for bringing this matter to our attention.",
                "action": "Due to the nature of your inquiry, I'm routing this to our specialized legal affairs team who handles these types of matters.",
                "next_steps": "A member of our legal affairs team will contact you within 2-4 hours to discuss this matter properly."
            },
            "security": {
                "acknowledgment": "I take security concerns very seriously and understand the urgency of this situation.",
                "action": "I'm immediately connecting you with our security team who can investigate and address this matter with the highest priority.",
                "next_steps": "Our security team will contact you immediately to begin the investigation process."
            }
        }

        # Get message template
        message_template = escalation_messages.get(
            escalation_decision.escalation_type,
            escalation_messages["technical"]
        )

        # Create proper email greeting with customer name
        customer_name = getattr(ticket, 'customer_name', None)
        if customer_name:
            # Extract first name if full name is provided
            first_name = customer_name.split()[
                0] if customer_name else customer_name
            greeting = f"Subject: Re: {ticket.subject}\n\nDear {first_name},"
        else:
            greeting = f"Subject: Re: {ticket.subject}\n\nDear Valued Customer,"

        # Add urgency and priority context
        priority_context = ""
        if escalation_decision.priority_level == "urgent":
            priority_context = " This has been marked as urgent and will be prioritized accordingly."

        # Get ticket reference
        ticket_ref = ticket.id or f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Create professional email response
        email_body = f"""{greeting}

Thank you for reaching out to us. {message_template['acknowledgment']} I sincerely apologize for any disruption this is causing.

{message_template['action']}{priority_context}

{message_template['next_steps']}

Your ticket reference number is: {ticket_ref}

If you have any immediate questions or concerns, please don't hesitate to reach out. We appreciate your patience and will ensure this matter receives the attention it deserves.

Best regards,
Customer Support Team
Technical Support Division"""

        return Resolution(
            ticket_id=ticket.id or "generated",
            response=email_body,
            confidence=0.9,  # High confidence for escalations
            knowledge_articles_used=[],
            agent_type="escalation"
        )

    def _calculate_resolution_confidence(self,
                                         classification: ClassificationResult,
                                         search_results: List[SearchResult],
                                         response_length: int) -> float:
        """
        Calculate confidence score for the resolution
        """
        confidence_factors = []

        # Classification confidence
        confidence_factors.append(classification.confidence * 0.3)

        # Knowledge base match quality
        if search_results:
            avg_kb_score = sum(r.score for r in search_results) / len(
                search_results)
            confidence_factors.append(avg_kb_score * 0.4)
        else:
            confidence_factors.append(0.1)  # Low confidence without KB matches

        # Response completeness (based on length)
        if response_length > 200:
            completeness_score = min(response_length / 500, 1.0)
        else:
            completeness_score = 0.3
        confidence_factors.append(completeness_score * 0.2)

        # Category-specific adjustments
        category_confidence = {
            "general": 0.8,
            "product": 0.7,
            "account": 0.75,
            "billing": 0.6,  # Often needs human verification
            "technical": 0.5  # Often complex
        }
        category_factor = category_confidence.get(
            classification.category.value, 0.6)
        confidence_factors.append(category_factor * 0.1)

        # Calculate final confidence
        final_confidence = sum(confidence_factors)
        return min(max(final_confidence, 0.1),
                   0.95)  # Clamp between 0.1 and 0.95

    def _post_process_response(self,
                               response: str,
                               ticket: CustomerTicket,
                               classification: ClassificationResult) -> str:
        """
        Post-process the generated response for quality and consistency
        """
        # Get customer name for personalization
        customer_name = getattr(ticket, 'customer_name', None)

        # Create proper email header and greeting
        if customer_name:
            first_name = customer_name.split()[
                0] if customer_name else customer_name
            email_header = f"Subject: Re: {ticket.subject}\n\nDear {first_name},"
        else:
            email_header = f"Subject: Re: {ticket.subject}\n\nDear Valued Customer,"

        # Check if response already has proper greeting structure
        if not response.lower().startswith(
                ("dear", "hello", "hi", "subject:")):
            # Add email header if not present
            response = f"{email_header}\n\nThank you for contacting us. {response}"

        # Ensure proper closing
        closing_phrases = ["thank you", "please let me know", "feel free to",
                           "if you have", "best regards", "sincerely"]
        has_closing = any(
            phrase in response.lower() for phrase in closing_phrases)

        if not has_closing:
            response += f"\n\nPlease let me know if you need any additional assistance!"

        # Add professional email signature
        if not response.endswith(("Best regards", "Sincerely", "Thank you")):
            response += f"\n\nBest regards,\nCustomer Support Team"

        # Add ticket reference if urgent
        if classification.priority.value in ["high", "critical"]:
            ticket_ref = ticket.id or f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            if ticket_ref not in response:
                response += f"\n\nTicket Reference: {ticket_ref}"

        # Limit response length
        if len(response) > self.max_response_length:
            # Try to trim at sentence boundary
            sentences = response.split('. ')
            trimmed = ""
            for sentence in sentences:
                if len(trimmed + sentence) < self.max_response_length - 3:
                    trimmed += sentence + ". "
                else:
                    break
            response = trimmed.strip()
            if not response.endswith('.'):
                response += "..."

        return response.strip()

    def _get_fallback_response(self, ticket: CustomerTicket) -> str:
        """
        Generate a fallback response when AI resolution fails
        """
        customer_name = getattr(ticket, 'customer_name', None)

        if customer_name:
            first_name = customer_name.split()[
                0] if customer_name else customer_name
            greeting = f"Subject: Re: {ticket.subject}\n\nDear {first_name},"
        else:
            greeting = f"Subject: Re: {ticket.subject}\n\nDear Valued Customer,"

        return f"""{greeting}

Thank you for contacting us. I've received your inquiry and want to ensure you receive the best possible assistance.

Due to the specific nature of your request, I'm connecting you with one of our specialists who can provide more detailed help and ensure your concern is addressed properly.

A team member will contact you shortly to assist with your inquiry. We appreciate your patience and apologize for any inconvenience.

Best regards,
Customer Support Team"""

    async def get_response_alternatives(self,
                                        ticket: CustomerTicket,
                                        classification: ClassificationResult,
                                        search_results: List[SearchResult]) -> \
    List[str]:
        """
        Generate alternative response options
        """
        alternatives = []

        try:
            # Generate a more concise version
            concise_prompt = f"""
            Generate a brief, direct response to this customer ticket:
            Subject: {ticket.subject}
            Message: {ticket.message}

            Keep the response under 200 words and focus on the most essential information.
            """
            concise_response = await llm_service.generate_response(
                concise_prompt)
            alternatives.append(concise_response)

            # Generate a more detailed version if we have good KB matches
            if search_results and search_results[0].score > 0.7:
                detailed_prompt = f"""
                Generate a comprehensive response to this customer ticket using the knowledge base:
                Subject: {ticket.subject}
                Message: {ticket.message}

                Knowledge: {search_results[0].article.content[:500]}

                Provide step-by-step guidance and additional helpful information.
                """
                detailed_response = await llm_service.generate_response(
                    detailed_prompt)
                alternatives.append(detailed_response)

        except Exception as e:
            print(f"Error generating alternatives: {e}")

        return alternatives

    def get_resolution_metrics(self, resolutions: List[Resolution]) -> Dict[
        str, Any]:
        """
        Calculate resolution metrics for reporting
        """
        if not resolutions:
            return {"total": 0}

        total_resolutions = len(resolutions)
        ai_resolutions = sum(1 for r in resolutions if r.agent_type == "ai")
        escalated_resolutions = sum(
            1 for r in resolutions if r.agent_type == "escalation")

        avg_confidence = sum(
            r.confidence for r in resolutions) / total_resolutions

        # Knowledge base usage
        total_kb_articles = sum(
            len(r.knowledge_articles_used) for r in resolutions)
        avg_kb_usage = total_kb_articles / total_resolutions if total_resolutions > 0 else 0

        return {
            "total_resolutions": total_resolutions,
            "ai_resolution_rate": round(
                (ai_resolutions / total_resolutions) * 100, 2),
            "escalation_rate": round(
                (escalated_resolutions / total_resolutions) * 100, 2),
            "average_confidence": round(avg_confidence, 2),
            "average_kb_articles_used": round(avg_kb_usage, 2),
            "high_confidence_resolutions": len(
                [r for r in resolutions if r.confidence > 0.7])
        }


# Global resolution agent instance
resolution_agent = ResolutionAgent()