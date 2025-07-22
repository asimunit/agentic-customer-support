from typing import List, Optional, Dict, Any
from backend.models.schemas import CustomerTicket, SearchResult, \
    ClassificationResult
from backend.services.elasticsearch_service import es_service
from backend.services.embedding_service import embedding_service
from backend.services.llm_service import llm_service


class KnowledgeAgent:
    """Agent responsible for searching and retrieving relevant knowledge articles"""

    def __init__(self):
        self.name = "Knowledge Agent"
        self.max_articles = 5
        self.min_relevance_score = 0.3

    async def search_knowledge_base(self,
                                    ticket: CustomerTicket,
                                    classification: Optional[
                                        ClassificationResult] = None,
                                    search_type: str = "hybrid") -> List[
        SearchResult]:
        """
        Search for relevant knowledge base articles
        """
        try:
            # Prepare search query
            search_text = self._prepare_search_query(ticket, classification)

            # Generate query embedding
            query_embedding = await embedding_service.create_query_embedding(
                search_text)

            # Determine category filter
            category_filter = None
            if classification and classification.confidence > 0.7:
                category_filter = classification.category.value

            # Perform search based on type
            if search_type == "hybrid":
                results = await es_service.hybrid_search(
                    query_text=search_text,
                    query_embedding=query_embedding,
                    category=category_filter,
                    top_k=self.max_articles
                )
            elif search_type == "semantic":
                results = await es_service.search_similar(
                    query_embedding=query_embedding,
                    category=category_filter,
                    top_k=self.max_articles
                )
            else:  # fallback to hybrid
                results = await es_service.hybrid_search(
                    query_text=search_text,
                    query_embedding=query_embedding,
                    category=category_filter,
                    top_k=self.max_articles
                )

            # Filter results by relevance score
            filtered_results = [
                result for result in results
                if result.score >= self.min_relevance_score
            ]

            # Enhance results with additional context
            enhanced_results = await self._enhance_search_results(
                filtered_results,
                ticket,
                classification
            )

            return enhanced_results

        except Exception as e:
            print(f"Error in knowledge search: {e}")
            return []

    def _prepare_search_query(self,
                              ticket: CustomerTicket,
                              classification: Optional[
                                  ClassificationResult] = None) -> str:
        """
        Prepare an optimized search query from the ticket
        """
        # Start with subject and message
        query_parts = [ticket.subject, ticket.message]

        # Add classification context if available
        if classification:
            query_parts.append(f"category:{classification.category.value}")

        # Extract key phrases using simple heuristics
        combined_text = f"{ticket.subject} {ticket.message}"
        key_phrases = self._extract_key_phrases(combined_text)
        query_parts.extend(key_phrases)

        # Join and clean the query
        search_query = " ".join(query_parts)
        search_query = " ".join(
            search_query.split())  # Remove extra whitespace

        return search_query[:500]  # Limit length

    def _extract_key_phrases(self, text: str) -> List[str]:
        """
        Extract key phrases that are likely to be important for search
        """
        # Simple keyword extraction based on common patterns
        important_words = []

        # Technical terms (often contain specific keywords)
        tech_patterns = ["error", "bug", "issue", "problem", "fail", "crash"]
        for pattern in tech_patterns:
            if pattern in text.lower():
                # Try to capture context around the keyword
                words = text.lower().split()
                for i, word in enumerate(words):
                    if pattern in word:
                        # Capture surrounding context
                        start = max(0, i - 2)
                        end = min(len(words), i + 3)
                        phrase = " ".join(words[start:end])
                        important_words.append(phrase)

        # Common product/feature terms
        feature_indicators = ["how to", "can't", "unable", "doesn't work",
                              "not working"]
        for indicator in feature_indicators:
            if indicator in text.lower():
                important_words.append(indicator)

        return important_words[:5]  # Limit to top 5 phrases

    async def _enhance_search_results(self,
                                      results: List[SearchResult],
                                      ticket: CustomerTicket,
                                      classification: Optional[
                                          ClassificationResult]) -> List[
        SearchResult]:
        """
        Enhance search results with additional context and scoring
        """
        enhanced_results = []

        for result in results:
            # Calculate additional relevance factors
            category_match = (
                    classification and
                    result.article.category == classification.category.value
            )

            # Adjust score based on additional factors
            adjusted_score = result.score

            if category_match:
                adjusted_score *= 1.2  # Boost for category match

            # Boost based on article popularity (resolution count)
            if result.article.resolution_count > 0:
                popularity_boost = min(result.article.resolution_count / 100,
                                       0.2)
                adjusted_score *= (1 + popularity_boost)

            # Boost based on article rating
            if result.article.rating and result.article.rating > 3.0:
                rating_boost = (result.article.rating - 3.0) * 0.1
                adjusted_score *= (1 + rating_boost)

            # Create enhanced result
            enhanced_result = SearchResult(
                article=result.article,
                score=min(adjusted_score, 1.0),  # Cap at 1.0
                relevance=self._calculate_enhanced_relevance(adjusted_score)
            )

            enhanced_results.append(enhanced_result)

        # Sort by adjusted score
        enhanced_results.sort(key=lambda x: x.score, reverse=True)

        return enhanced_results

    def _calculate_enhanced_relevance(self, score: float) -> str:
        """
        Calculate relevance description based on enhanced score
        """
        if score >= 0.9:
            return "Excellent"
        elif score >= 0.75:
            return "Very High"
        elif score >= 0.6:
            return "High"
        elif score >= 0.45:
            return "Medium"
        elif score >= 0.3:
            return "Low"
        else:
            return "Very Low"

    async def get_article_summary(self, search_results: List[SearchResult]) -> \
    Dict[str, Any]:
        """
        Generate a summary of the search results
        """
        if not search_results:
            return {
                "total_results": 0,
                "best_match_score": 0,
                "categories_found": [],
                "summary": "No relevant articles found"
            }

        # Calculate statistics
        scores = [result.score for result in search_results]
        categories = list(
            set(result.article.category for result in search_results))

        # Generate summary
        best_result = search_results[0]
        summary_parts = [
            f"Found {len(search_results)} relevant articles.",
            f"Best match: '{best_result.article.title}' (score: {best_result.score:.2f})"
        ]

        if len(categories) > 1:
            summary_parts.append(
                f"Articles span {len(categories)} categories: {', '.join(categories)}")

        return {
            "total_results": len(search_results),
            "best_match_score": max(scores),
            "average_score": sum(scores) / len(scores),
            "categories_found": categories,
            "summary": " ".join(summary_parts),
            "high_confidence_results": len(
                [r for r in search_results if r.score > 0.7])
        }

    async def suggest_additional_keywords(self,
                                          ticket: CustomerTicket,
                                          search_results: List[
                                              SearchResult]) -> List[str]:
        """
        Suggest additional keywords that might improve search results
        """
        try:
            # Use LLM to suggest related keywords
            keywords = await llm_service.extract_keywords(
                f"{ticket.subject} {ticket.message}"
            )

            # Filter out keywords that might not be helpful
            filtered_keywords = [
                kw for kw in keywords
                if
                len(kw) > 2 and kw.lower() not in ["the", "and", "for", "with"]
            ]

            return filtered_keywords[:10]
        except Exception as e:
            print(f"Error suggesting keywords: {e}")
            return []


# Global knowledge agent instance
knowledge_agent = KnowledgeAgent()