import google.generativeai as genai
from typing import Dict, Any, Optional
import json
import asyncio
from config.settings import settings


class GeminiLLMService:
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(settings.GEMINI_MODEL)

    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate response using Gemini model"""
        try:
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=kwargs.get('temperature',
                                           settings.TEMPERATURE),
                    max_output_tokens=kwargs.get('max_tokens',
                                                 settings.MAX_TOKENS),
                )
            )
            return response.text
        except Exception as e:
            raise Exception(f"Error generating response: {str(e)}")

    async def classify_ticket(self, subject: str, message: str) -> Dict[
        str, Any]:
        """Classify ticket category and priority"""
        prompt = f"""
        Analyze the following customer support ticket and classify it:

        Subject: {subject}
        Message: {message}

        Please classify this ticket with:
        1. Category: technical, billing, general, product, or account
        2. Priority: low, medium, high, or critical
        3. Confidence score (0.0 to 1.0)
        4. Brief reasoning

        Return ONLY a JSON object with these fields:
        {{
            "category": "category_name",
            "priority": "priority_level", 
            "confidence": 0.85,
            "reasoning": "brief explanation"
        }}
        """

        response = await self.generate_response(prompt)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # Fallback classification
            return {
                "category": "general",
                "priority": "medium",
                "confidence": 0.5,
                "reasoning": "Unable to parse LLM response"
            }

    async def check_escalation(self, ticket_data: Dict[str, Any]) -> Dict[
        str, Any]:
        """Determine if ticket should be escalated"""
        prompt = f"""
        Analyze this customer support ticket to determine if it needs escalation:

        Subject: {ticket_data.get('subject', '')}
        Message: {ticket_data.get('message', '')}
        Category: {ticket_data.get('category', '')}
        Priority: {ticket_data.get('priority', '')}

        Consider escalation if:
        - Customer is angry/frustrated
        - Technical issue is complex
        - Billing/payment issues
        - Legal threats
        - Request for manager/supervisor
        - High-value customer concerns

        Return ONLY a JSON object:
        {{
            "should_escalate": true/false,
            "reason": "explanation",
            "escalation_type": "technical/billing/management/legal",
            "priority_level": "standard/urgent",
            "confidence": 0.85
        }}
        """

        response = await self.generate_response(prompt)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            return {
                "should_escalate": False,
                "reason": "Unable to analyze escalation need",
                "escalation_type": None,
                "priority_level": "standard",
                "confidence": 0.5
            }

    async def generate_resolution(self,
                                  ticket_data: Dict[str, Any],
                                  knowledge_articles: list) -> str:
        """Generate response based on ticket and knowledge articles"""
        articles_text = "\n\n".join([
            f"Article {i + 1}: {article.get('title', 'No title')}\n{article.get('content', 'No content')}"
            for i, article in enumerate(knowledge_articles[:3])
            # Limit to top 3
        ])

        prompt = f"""
        You are a professional customer support agent writing an email response. Generate a helpful, professional email response to this customer ticket:

        Customer Ticket:
        Subject: {ticket_data.get('subject', '')}
        Message: {ticket_data.get('message', '')}

        Relevant Knowledge Base Articles:
        {articles_text if articles_text.strip() else "No relevant articles found"}

        Guidelines:
        - Write in professional email format (but don't include "Subject:" or "Dear [Name]" - that will be added automatically)
        - Be empathetic and acknowledge the customer's concern
        - Provide clear, step-by-step solutions when possible
        - Reference knowledge base information when relevant
        - If no complete solution is available, acknowledge this and suggest next steps
        - Use a helpful, professional tone
        - End with an offer for additional assistance
        - Do not include email signature (will be added automatically)

        Generate the email body content only (starting with acknowledgment/empathy):
        """

        return await self.generate_response(prompt)

    async def extract_keywords(self, text: str) -> list:
        """Extract relevant keywords from text"""
        prompt = f"""
        Extract the most important keywords and phrases from this customer support text:

        Text: {text}

        Return ONLY a JSON array of keywords/phrases (5-10 items max):
        ["keyword1", "keyword2", "phrase with spaces", ...]
        """

        response = await self.generate_response(prompt)
        try:
            return json.loads(response.strip())
        except json.JSONDecodeError:
            # Fallback: simple keyword extraction
            words = text.lower().split()
            return [word for word in words if len(word) > 3][:10]


# Global LLM service instance
llm_service = GeminiLLMService()