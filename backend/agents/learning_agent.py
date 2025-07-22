from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from backend.models.schemas import (
    CustomerTicket, Resolution, LearningFeedback,
    KnowledgeArticle, TicketCategory
)
from backend.services.llm_service import llm_service
from backend.services.embedding_service import embedding_service
from backend.services.elasticsearch_service import es_service


class LearningAgent:
    """Agent responsible for learning from resolutions and improving the knowledge base"""

    def __init__(self):
        self.name = "Learning Agent"
        self.feedback_threshold = 0.7  # Minimum rating to consider positive
        self.learning_batch_size = 10

    async def process_feedback(self,
                               feedback: LearningFeedback,
                               ticket: CustomerTicket,
                               resolution: Resolution) -> Dict[str, Any]:
        """
        Process customer feedback and extract learning insights
        """
        try:
            learning_insights = {
                "feedback_processed": True,
                "feedback_type": "positive" if feedback.was_helpful else "negative",
                "actions_taken": [],
                "recommendations": []
            }

            if feedback.was_helpful and feedback.customer_rating and feedback.customer_rating >= 4:
                # Positive feedback - reinforce successful patterns
                await self._process_positive_feedback(
                    feedback, ticket, resolution, learning_insights
                )
            else:
                # Negative feedback - identify improvement opportunities
                await self._process_negative_feedback(
                    feedback, ticket, resolution, learning_insights
                )

            # Generate improvement suggestions
            if feedback.feedback_text:
                suggestions = await self._generate_improvement_suggestions(
                    feedback.feedback_text, ticket, resolution
                )
                learning_insights["ai_suggestions"] = suggestions

            return learning_insights

        except Exception as e:
            return {
                "feedback_processed": False,
                "error": str(e),
                "actions_taken": [],
                "recommendations": ["Manual review recommended"]
            }

    async def _process_positive_feedback(self,
                                         feedback: LearningFeedback,
                                         ticket: CustomerTicket,
                                         resolution: Resolution,
                                         insights: Dict[str, Any]):
        """
        Process positive feedback to reinforce successful patterns
        """
        # Boost knowledge articles that were used successfully
        for article_id in resolution.knowledge_articles_used:
            await self._boost_article_rating(article_id,
                                             feedback.customer_rating)
            insights["actions_taken"].append(
                f"Boosted rating for article {article_id}")

        # If no knowledge articles were used but resolution was successful,
        # consider creating a new knowledge article
        if not resolution.knowledge_articles_used and feedback.customer_rating >= 4:
            new_article_candidate = await self._create_article_candidate(
                ticket, resolution
            )
            if new_article_candidate:
                insights["recommendations"].append(
                    "Consider creating new knowledge article")
                insights["new_article_candidate"] = new_article_candidate

        # Learn from successful resolution patterns
        success_pattern = await self._extract_success_pattern(
            ticket, resolution, feedback
        )
        insights["success_pattern"] = success_pattern

    async def _process_negative_feedback(self,
                                         feedback: LearningFeedback,
                                         ticket: CustomerTicket,
                                         resolution: Resolution,
                                         insights: Dict[str, Any]):
        """
        Process negative feedback to identify improvement opportunities
        """
        # Analyze what went wrong
        failure_analysis = await self._analyze_resolution_failure(
            ticket, resolution, feedback
        )
        insights["failure_analysis"] = failure_analysis

        # Suggest knowledge base improvements
        if resolution.knowledge_articles_used:
            for article_id in resolution.knowledge_articles_used:
                improvement_suggestions = await self._suggest_article_improvements(
                    article_id, ticket, feedback.feedback_text or ""
                )
                insights["recommendations"].extend(improvement_suggestions)

        # Check if escalation should have occurred
        if resolution.agent_type == "ai" and feedback.customer_rating and feedback.customer_rating <= 2:
            insights["recommendations"].append(
                "Consider updating escalation rules for similar cases"
            )
            insights["escalation_review_needed"] = True

    async def _boost_article_rating(self, article_id: str,
                                    customer_rating: Optional[int]):
        """
        Update article rating based on positive feedback
        """
        if not customer_rating:
            return

        try:
            # Simple rating update - in production, you'd want more sophisticated logic
            rating_boost = (
                                       customer_rating - 3) * 0.1  # Convert 1-5 scale to boost

            # Update in Elasticsearch (simplified - you'd want proper rating aggregation)
            await es_service.async_client.update(
                index=es_service.index_name,
                id=article_id,
                body={
                    "script": {
                        "source": """
                        if (ctx._source.rating == null) {
                            ctx._source.rating = params.new_rating;
                        } else {
                            ctx._source.rating = (ctx._source.rating + params.new_rating) / 2;
                        }
                        """,
                        "params": {"new_rating": customer_rating}
                    }
                }
            )
        except Exception as e:
            print(f"Error updating article rating: {e}")

    async def _create_article_candidate(self,
                                        ticket: CustomerTicket,
                                        resolution: Resolution) -> Optional[
        Dict[str, Any]]:
        """
        Create a candidate for a new knowledge article based on successful resolution
        """
        try:
            # Generate article content using LLM
            article_prompt = f"""
            Based on this successful customer support resolution, create a knowledge base article:

            Customer Issue:
            Subject: {ticket.subject}
            Message: {ticket.message}

            Successful Resolution:
            {resolution.response}

            Create a knowledge article with:
            - Clear, descriptive title
            - Step-by-step solution
            - Common variations of the problem
            - Prevention tips if applicable

            Format as JSON with fields: title, content, tags, category
            """

            article_content = await llm_service.generate_response(
                article_prompt)

            # Try to parse as JSON, fallback to structured text
            try:
                import json
                parsed_article = json.loads(article_content)
                return parsed_article
            except json.JSONDecodeError:
                # Fallback to manual structure
                return {
                    "title": f"Solution for: {ticket.subject}",
                    "content": article_content,
                    "tags": ["auto-generated", "successful-resolution"],
                    "category": "general"
                }
        except Exception as e:
            print(f"Error creating article candidate: {e}")
            return None

    async def _extract_success_pattern(self,
                                       ticket: CustomerTicket,
                                       resolution: Resolution,
                                       feedback: LearningFeedback) -> Dict[
        str, Any]:
        """
        Extract patterns from successful resolutions
        """
        return {
            "ticket_characteristics": {
                "subject_length": len(ticket.subject),
                "message_length": len(ticket.message),
                "category": getattr(ticket, 'category', 'unknown')
            },
            "resolution_characteristics": {
                "response_length": len(resolution.response),
                "confidence": resolution.confidence,
                "kb_articles_used": len(resolution.knowledge_articles_used),
                "agent_type": resolution.agent_type
            },
            "outcome": {
                "customer_rating": feedback.customer_rating,
                "was_helpful": feedback.was_helpful
            }
        }

    async def _analyze_resolution_failure(self,
                                          ticket: CustomerTicket,
                                          resolution: Resolution,
                                          feedback: LearningFeedback) -> Dict[
        str, Any]:
        """
        Analyze why a resolution failed to help the customer
        """
        analysis = {
            "potential_causes": [],
            "confidence_vs_outcome": {
                "predicted_confidence": resolution.confidence,
                "actual_success": feedback.was_helpful
            }
        }

        # Check for confidence mismatch
        if resolution.confidence > 0.7 and not feedback.was_helpful:
            analysis["potential_causes"].append("Overconfident AI prediction")

        # Check knowledge base usage
        if not resolution.knowledge_articles_used:
            analysis["potential_causes"].append(
                "No relevant knowledge articles found")
        elif len(resolution.knowledge_articles_used) > 3:
            analysis["potential_causes"].append(
                "Too many knowledge articles used - may be confusing")

        # Analyze feedback text for specific issues
        if feedback.feedback_text:
            feedback_lower = feedback.feedback_text.lower()
            if "wrong" in feedback_lower or "incorrect" in feedback_lower:
                analysis["potential_causes"].append(
                    "Incorrect information provided")
            if "unclear" in feedback_lower or "confusing" in feedback_lower:
                analysis["potential_causes"].append(
                    "Response was unclear or confusing")
            if "not helpful" in feedback_lower:
                analysis["potential_causes"].append(
                    "Response didn't address the actual problem")

        return analysis

    async def _suggest_article_improvements(self,
                                            article_id: str,
                                            ticket: CustomerTicket,
                                            feedback_text: str) -> List[str]:
        """
        Suggest improvements to knowledge articles based on negative feedback
        """
        suggestions = []

        try:
            # Get the article content
            article_response = await es_service.async_client.get(
                index=es_service.index_name,
                id=article_id
            )
            article_content = article_response["_source"]["content"]

            # Generate improvement suggestions using LLM
            improvement_prompt = f"""
            A knowledge article was used but didn't satisfy the customer. Suggest improvements:

            Original Article Content:
            {article_content[:500]}...

            Customer Issue:
            {ticket.subject} - {ticket.message}

            Customer Feedback:
            {feedback_text}

            Suggest 2-3 specific improvements to make this article more helpful.
            """

            improvements = await llm_service.generate_response(
                improvement_prompt)
            suggestions.append(f"Article {article_id}: {improvements}")

        except Exception as e:
            suggestions.append(
                f"Could not analyze article {article_id}: {str(e)}")

        return suggestions

    async def _generate_improvement_suggestions(self,
                                                feedback_text: str,
                                                ticket: CustomerTicket,
                                                resolution: Resolution) -> \
    List[str]:
        """
        Generate general improvement suggestions based on feedback
        """
        try:
            suggestion_prompt = f"""
            Based on this customer feedback, suggest specific improvements to our support system:

            Customer Issue: {ticket.subject}
            Our Response: {resolution.response[:200]}...
            Customer Feedback: {feedback_text}

            Provide 2-3 actionable suggestions for improvement.
            """

            suggestions_text = await llm_service.generate_response(
                suggestion_prompt)

            # Split into individual suggestions
            suggestions = [
                s.strip() for s in suggestions_text.split('\n')
                if s.strip() and len(s.strip()) > 10
            ]

            return suggestions[:3]  # Limit to 3 suggestions

        except Exception as e:
            return [f"Error generating suggestions: {str(e)}"]

    async def analyze_learning_trends(self,
                                      feedback_data: List[LearningFeedback],
                                      time_period_days: int = 30) -> Dict[
        str, Any]:
        """
        Analyze learning trends over a time period
        """
        cutoff_date = datetime.now() - timedelta(days=time_period_days)

        # Filter recent feedback
        recent_feedback = [
            f for f in feedback_data
            # Assuming feedback has a timestamp field
        ]

        if not recent_feedback:
            return {"message": "No recent feedback data available"}

        # Calculate metrics
        total_feedback = len(recent_feedback)
        positive_feedback = sum(1 for f in recent_feedback if f.was_helpful)
        avg_rating = sum(f.customer_rating for f in recent_feedback if
                         f.customer_rating) / len(
            [f for f in recent_feedback if f.customer_rating])

        # Identify common improvement themes
        improvement_themes = await self._identify_improvement_themes(
            recent_feedback)

        return {
            "period_days": time_period_days,
            "total_feedback": total_feedback,
            "satisfaction_rate": round(
                (positive_feedback / total_feedback) * 100, 2),
            "average_rating": round(avg_rating, 2),
            "improvement_themes": improvement_themes,
            "trend_analysis": "Positive" if positive_feedback / total_feedback > 0.7 else "Needs attention"
        }

    async def _identify_improvement_themes(self,
                                           feedback_data: List[
                                               LearningFeedback]) -> List[
        Dict[str, Any]]:
        """
        Identify common themes in improvement suggestions
        """
        # Collect all feedback text
        feedback_texts = [
            f.feedback_text for f in feedback_data
            if f.feedback_text and not f.was_helpful
        ]

        if not feedback_texts:
            return []

        try:
            # Use LLM to identify themes
            theme_prompt = f"""
            Analyze these customer feedback comments and identify the top 3 common themes or issues:

            Feedback Comments:
            {chr(10).join(feedback_texts[:20])}  # Limit to first 20 comments

            Return the themes as a JSON array with theme name and frequency estimate.
            """

            themes_response = await llm_service.generate_response(theme_prompt)

            # Try to parse as JSON
            import json
            try:
                themes = json.loads(themes_response)
                return themes if isinstance(themes, list) else []
            except json.JSONDecodeError:
                # Fallback to simple theme extraction
                return [{"theme": "Manual analysis needed",
                         "frequency": "unknown"}]

        except Exception as e:
            return [
                {"theme": f"Analysis error: {str(e)}", "frequency": "unknown"}]


# Global learning agent instance
learning_agent = LearningAgent()