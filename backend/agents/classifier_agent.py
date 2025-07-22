from typing import Dict, Any
from backend.models.schemas import CustomerTicket, ClassificationResult, \
    TicketCategory, TicketPriority
from backend.services.llm_service import llm_service
from config.settings import settings


class ClassifierAgent:
    """Agent responsible for categorizing and prioritizing customer tickets"""

    def __init__(self):
        self.name = "Classifier Agent"
        self.high_priority_keywords = settings.HIGH_PRIORITY_KEYWORDS

    async def classify_ticket(self,
                              ticket: CustomerTicket) -> ClassificationResult:
        """
        Classify the ticket into category and priority
        """
        try:
            # Get LLM classification
            llm_result = await llm_service.classify_ticket(
                ticket.subject,
                ticket.message
            )

            # Apply rule-based adjustments
            adjusted_result = self._apply_classification_rules(
                ticket,
                llm_result
            )

            # Create classification result
            classification = ClassificationResult(
                category=TicketCategory(adjusted_result["category"]),
                priority=TicketPriority(adjusted_result["priority"]),
                confidence=adjusted_result["confidence"],
                reasoning=adjusted_result["reasoning"]
            )

            return classification

        except Exception as e:
            # Fallback classification
            return ClassificationResult(
                category=TicketCategory.GENERAL,
                priority=TicketPriority.MEDIUM,
                confidence=0.3,
                reasoning=f"Classification failed: {str(e)}"
            )

    def _apply_classification_rules(self,
                                    ticket: CustomerTicket,
                                    llm_result: Dict[str, Any]) -> Dict[
        str, Any]:
        """
        Apply rule-based adjustments to LLM classification
        """
        category = llm_result.get("category", "general")
        priority = llm_result.get("priority", "medium")
        confidence = llm_result.get("confidence", 0.5)
        reasoning = llm_result.get("reasoning", "")

        # Combine subject and message for keyword analysis
        full_text = f"{ticket.subject} {ticket.message}".lower()

        # Check for high priority keywords
        high_priority_found = any(
            keyword.lower() in full_text
            for keyword in self.high_priority_keywords
        )

        if high_priority_found:
            if priority in ["low", "medium"]:
                priority = "high"
                confidence = min(confidence + 0.2, 1.0)
                reasoning += " (Elevated due to urgent keywords)"

        # Category-specific priority adjustments
        category_priority_rules = {
            "billing": {
                "keywords": ["payment", "charge", "bill", "invoice"],
                "min_priority": "medium"
            },
            "technical": {
                "keywords": ["bug", "error", "crash", "broken"],
                "min_priority": "medium"
            }
        }

        if category in category_priority_rules:
            rules = category_priority_rules[category]
            keyword_found = any(
                keyword in full_text
                for keyword in rules["keywords"]
            )

            if keyword_found and self._priority_level(
                    priority) < self._priority_level(rules["min_priority"]):
                priority = rules["min_priority"]
                reasoning += f" (Elevated for {category} category)"

        # Security/breach detection
        security_keywords = ["hack", "breach", "security", "fraud", "phishing"]
        if any(keyword in full_text for keyword in security_keywords):
            priority = "critical"
            category = "technical"
            confidence = min(confidence + 0.3, 1.0)
            reasoning += " (Security issue detected)"

        return {
            "category": category,
            "priority": priority,
            "confidence": confidence,
            "reasoning": reasoning
        }

    def _priority_level(self, priority: str) -> int:
        """Convert priority to numeric level for comparison"""
        levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        return levels.get(priority.lower(), 2)

    async def get_classification_insights(self, ticket: CustomerTicket) -> \
    Dict[str, Any]:
        """
        Get additional insights about the ticket classification
        """
        full_text = f"{ticket.subject} {ticket.message}".lower()

        # Extract potential categories based on keywords
        category_indicators = {
            "technical": ["bug", "error", "crash", "problem", "issue",
                          "broken"],
            "billing": ["payment", "charge", "bill", "invoice",
                        "subscription"],
            "account": ["login", "password", "access", "profile", "settings"],
            "product": ["feature", "how to", "usage", "functionality"],
            "general": ["question", "help", "support", "information"]
        }

        detected_categories = []
        for category, keywords in category_indicators.items():
            matches = [kw for kw in keywords if kw in full_text]
            if matches:
                detected_categories.append({
                    "category": category,
                    "keywords_matched": matches,
                    "strength": len(matches)
                })

        # Sort by strength
        detected_categories.sort(key=lambda x: x["strength"], reverse=True)

        return {
            "text_length": len(ticket.message),
            "subject_length": len(ticket.subject),
            "detected_categories": detected_categories,
            "has_urgency_indicators": any(
                kw in full_text for kw in self.high_priority_keywords
            ),
            "estimated_complexity": self._estimate_complexity(full_text)
        }

    def _estimate_complexity(self, text: str) -> str:
        """Estimate the complexity of the issue based on text analysis"""
        complexity_indicators = {
            "high": ["multiple", "several", "complex", "complicated",
                     "various"],
            "medium": ["issue", "problem", "help", "support"],
            "low": ["simple", "quick", "easy", "just", "only"]
        }

        scores = {}
        for level, keywords in complexity_indicators.items():
            scores[level] = sum(1 for kw in keywords if kw in text.lower())

        # Determine complexity based on highest score
        max_score = max(scores.values())
        if max_score == 0:
            return "medium"

        for level, score in scores.items():
            if score == max_score:
                return level

        return "medium"


# Global classifier agent instance
classifier_agent = ClassifierAgent()