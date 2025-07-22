from typing import Dict, Any, List
from backend.models.schemas import CustomerTicket, ClassificationResult, \
    SearchResult, EscalationDecision
from backend.services.llm_service import llm_service
from config.settings import settings


class EscalationAgent:
    """Agent responsible for determining if tickets need human escalation"""

    def __init__(self):
        self.name = "Escalation Agent"
        self.escalation_keywords = settings.ESCALATION_KEYWORDS
        self.auto_escalate_categories = ["critical"]

    async def evaluate_escalation(self,
                                  ticket: CustomerTicket,
                                  classification: ClassificationResult,
                                  search_results: List[
                                      SearchResult]) -> EscalationDecision:
        """
        Evaluate whether the ticket should be escalated to human agents
        """
        try:
            # Get LLM evaluation
            llm_decision = await llm_service.check_escalation({
                "subject": ticket.subject,
                "message": ticket.message,
                "category": classification.category.value,
                "priority": classification.priority.value
            })

            # Apply rule-based logic
            rule_based_decision = self._apply_escalation_rules(
                ticket,
                classification,
                search_results
            )

            # Combine decisions
            final_decision = self._combine_decisions(
                llm_decision,
                rule_based_decision
            )

            return EscalationDecision(
                should_escalate=final_decision["should_escalate"],
                reason=final_decision["reason"],
                escalation_type=final_decision.get("escalation_type"),
                priority_level=final_decision["priority_level"],
                confidence=final_decision["confidence"]
            )

        except Exception as e:
            # Conservative fallback - escalate if unsure
            return EscalationDecision(
                should_escalate=True,
                reason=f"Escalation evaluation failed: {str(e)}",
                escalation_type="technical",
                priority_level="standard",
                confidence=0.3
            )

    def _apply_escalation_rules(self,
                                ticket: CustomerTicket,
                                classification: ClassificationResult,
                                search_results: List[SearchResult]) -> Dict[
        str, Any]:
        """
        Apply rule-based escalation logic
        """
        full_text = f"{ticket.subject} {ticket.message}".lower()
        should_escalate = False
        escalation_reasons = []
        escalation_type = "general"
        priority_level = "standard"

        # Rule 1: Critical priority tickets
        if classification.priority.value == "critical":
            should_escalate = True
            escalation_reasons.append("Critical priority ticket")
            priority_level = "urgent"
            escalation_type = "technical"

        # Rule 2: Escalation keywords present
        escalation_keyword_found = any(
            keyword.lower() in full_text
            for keyword in self.escalation_keywords
        )
        if escalation_keyword_found:
            should_escalate = True
            escalation_reasons.append("Customer requesting escalation")
            escalation_type = "management"

        # Rule 3: Security/legal issues
        security_legal_keywords = [
            "legal", "lawsuit", "lawyer", "attorney", "court",
            "hack", "breach", "fraud", "scam", "theft"
        ]
        if any(keyword in full_text for keyword in security_legal_keywords):
            should_escalate = True
            escalation_reasons.append("Security or legal concern")
            priority_level = "urgent"
            escalation_type = "legal" if any(k in full_text for k in
                                             ["legal", "lawsuit",
                                              "lawyer"]) else "security"

        # Rule 4: Complex technical issues (no good knowledge base matches)
        if (classification.category.value == "technical" and
                classification.priority.value in ["high", "critical"] and
                (not search_results or search_results[0].score < 0.6)):
            should_escalate = True
            escalation_reasons.append(
                "Complex technical issue with no clear solution")
            escalation_type = "technical"

        # Rule 5: Billing issues above certain threshold
        billing_high_value_keywords = [
            "refund", "cancel", "subscription", "charge", "payment failed"
        ]
        if (classification.category.value == "billing" and
                any(keyword in full_text for keyword in
                    billing_high_value_keywords)):
            should_escalate = True
            escalation_reasons.append("High-impact billing issue")
            escalation_type = "billing"

        # Rule 6: Customer frustration indicators
        frustration_keywords = [
            "angry", "frustrated", "disappointed", "terrible", "worst",
            "unacceptable", "ridiculous", "pathetic", "hate"
        ]
        frustration_count = sum(
            1 for keyword in frustration_keywords if keyword in full_text)
        if frustration_count >= 2:
            should_escalate = True
            escalation_reasons.append("Customer showing high frustration")
            escalation_type = "management"

        # Rule 7: Multiple previous attempts mentioned
        retry_indicators = [
            "tried multiple times", "several attempts", "contacted before",
            "still not working", "again", "repeatedly"
        ]
        if any(indicator in full_text for indicator in retry_indicators):
            should_escalate = True
            escalation_reasons.append("Multiple failed resolution attempts")

        # Calculate confidence based on rule strength
        confidence = 0.5  # Base confidence
        if len(escalation_reasons) > 2:
            confidence = 0.9
        elif len(escalation_reasons) == 2:
            confidence = 0.8
        elif len(escalation_reasons) == 1:
            confidence = 0.7

        return {
            "should_escalate": should_escalate,
            "reason": "; ".join(
                escalation_reasons) if escalation_reasons else "No escalation needed",
            "escalation_type": escalation_type,
            "priority_level": priority_level,
            "confidence": confidence
        }

    def _combine_decisions(self,
                           llm_decision: Dict[str, Any],
                           rule_decision: Dict[str, Any]) -> Dict[str, Any]:
        """
        Combine LLM and rule-based decisions into final decision
        """
        # If either system says escalate, we escalate (conservative approach)
        should_escalate = (
                llm_decision.get("should_escalate", False) or
                rule_decision.get("should_escalate", False)
        )

        # Combine reasons
        reasons = []
        if llm_decision.get("reason"):
            reasons.append(f"AI: {llm_decision['reason']}")
        if rule_decision.get("reason") and rule_decision[
            "reason"] != "No escalation needed":
            reasons.append(f"Rules: {rule_decision['reason']}")

        # Choose escalation type (prioritize rule-based)
        escalation_type = (
                rule_decision.get("escalation_type") or
                llm_decision.get("escalation_type") or
                "general"
        )

        # Choose priority level (highest wins)
        priority_levels = {"standard": 1, "urgent": 2}
        rule_priority = rule_decision.get("priority_level", "standard")
        llm_priority = llm_decision.get("priority_level", "standard")

        priority_level = (
            rule_priority if priority_levels.get(rule_priority,
                                                 1) >= priority_levels.get(
                llm_priority, 1)
            else llm_priority
        )

        # Average confidence scores
        confidence = (
                             rule_decision.get("confidence", 0.5) +
                             llm_decision.get("confidence", 0.5)
                     ) / 2

        return {
            "should_escalate": should_escalate,
            "reason": "; ".join(
                reasons) if reasons else "No escalation needed",
            "escalation_type": escalation_type,
            "priority_level": priority_level,
            "confidence": confidence
        }

    async def get_escalation_routing(self,
                                     escalation_decision: EscalationDecision) -> \
    Dict[str, Any]:
        """
        Determine the appropriate escalation routing
        """
        if not escalation_decision.should_escalate:
            return {"routing": "ai_resolution", "department": None}

        # Route based on escalation type
        routing_map = {
            "technical": {
                "department": "Technical Support",
                "skill_level": "senior" if escalation_decision.priority_level == "urgent" else "standard",
                "estimated_wait": "15-30 minutes" if escalation_decision.priority_level == "urgent" else "1-2 hours"
            },
            "billing": {
                "department": "Billing Support",
                "skill_level": "standard",
                "estimated_wait": "30-45 minutes"
            },
            "management": {
                "department": "Customer Success",
                "skill_level": "manager",
                "estimated_wait": "45-60 minutes"
            },
            "legal": {
                "department": "Legal Affairs",
                "skill_level": "specialist",
                "estimated_wait": "2-4 hours"
            },
            "security": {
                "department": "Security Team",
                "skill_level": "specialist",
                "estimated_wait": "Immediate" if escalation_decision.priority_level == "urgent" else "30-60 minutes"
            }
        }

        routing = routing_map.get(escalation_decision.escalation_type,
                                  routing_map["technical"])
        routing["routing"] = "human_agent"
        routing["escalation_type"] = escalation_decision.escalation_type
        routing["priority"] = escalation_decision.priority_level

        return routing

    def get_escalation_metrics(self, decisions: List[EscalationDecision]) -> \
    Dict[str, Any]:
        """
        Calculate escalation metrics for reporting
        """
        if not decisions:
            return {"total": 0, "escalation_rate": 0}

        total_tickets = len(decisions)
        escalated_tickets = sum(1 for d in decisions if d.should_escalate)
        escalation_rate = escalated_tickets / total_tickets

        # Group by escalation type
        escalation_types = {}
        for decision in decisions:
            if decision.should_escalate and decision.escalation_type:
                escalation_types[
                    decision.escalation_type] = escalation_types.get(
                    decision.escalation_type, 0) + 1

        return {
            "total_tickets": total_tickets,
            "escalated_tickets": escalated_tickets,
            "escalation_rate": round(escalation_rate * 100, 2),
            "escalation_types": escalation_types,
            "average_confidence": round(
                sum(d.confidence for d in decisions) / total_tickets, 2
            )
        }


# Global escalation agent instance
escalation_agent = EscalationAgent()