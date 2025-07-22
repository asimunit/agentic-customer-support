from elasticsearch import Elasticsearch, AsyncElasticsearch
from typing import List, Dict, Any, Optional
import json
from datetime import datetime
from config.settings import settings
from backend.models.schemas import KnowledgeArticle, SearchResult


class ElasticsearchService:
    def __init__(self):
        self.es_url = settings.ELASTICSEARCH_URL
        self.index_name = settings.ELASTICSEARCH_INDEX
        self.embedding_dim = settings.EMBEDDING_DIMENSION
        self.client = None
        self.async_client = None

    async def initialize(self):
        """Initialize Elasticsearch connection"""
        try:
            # Use synchronous client for initialization
            self.client = Elasticsearch([self.es_url])
            self.async_client = AsyncElasticsearch([self.es_url])

            # Check connection
            info = self.client.info()
            print(f"Connected to Elasticsearch: {info['version']['number']}")

            # Create index if it doesn't exist
            await self.create_index()
            return True
        except Exception as e:
            print(f"Error connecting to Elasticsearch: {e}")
            return False

    async def create_index(self):
        """Create the knowledge base index with vector search capabilities"""
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "standard"
                    },
                    "category": {"type": "keyword"},
                    "tags": {"type": "keyword"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "resolution_count": {"type": "integer"},
                    "rating": {"type": "float"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": self.embedding_dim,
                        "index": True,
                        "similarity": "cosine"
                    }
                }
            },
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            }
        }

        try:
            if not self.client.indices.exists(index=self.index_name):
                self.client.indices.create(index=self.index_name, body=mapping)
                print(f"Created index: {self.index_name}")
            else:
                print(f"Index {self.index_name} already exists")
        except Exception as e:
            print(f"Error creating index: {e}")

    async def add_knowledge_article(self,
                                    article: KnowledgeArticle,
                                    embedding: List[float]) -> bool:
        """Add a knowledge article with its embedding to the index"""
        try:
            doc = {
                "id": article.id,
                "title": article.title,
                "content": article.content,
                "category": article.category,
                "tags": article.tags,
                "created_at": article.created_at.isoformat(),
                "updated_at": article.updated_at.isoformat() if article.updated_at else None,
                "resolution_count": article.resolution_count,
                "rating": article.rating,
                "embedding": embedding
            }

            await self.async_client.index(
                index=self.index_name,
                id=article.id,
                body=doc
            )
            print(f"Added article: {article.title}")
            return True
        except Exception as e:
            print(f"Error adding article: {e}")
            return False

    async def search_similar(self,
                             query_embedding: List[float],
                             category: Optional[str] = None,
                             top_k: int = 5) -> List[SearchResult]:
        """Search for similar articles using vector similarity"""
        try:
            # Build the query
            query = {
                "knn": {
                    "field": "embedding",
                    "query_vector": query_embedding,
                    "k": top_k,
                    "num_candidates": 100
                }
            }

            # Add category filter if specified
            if category:
                query["filter"] = {
                    "term": {"category": category}
                }

            response = await self.async_client.search(
                index=self.index_name,
                body={
                    "query": query,
                    "size": top_k,
                    "_source": ["id", "title", "content", "category", "tags",
                                "created_at", "resolution_count", "rating"]
                }
            )

            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]

                # Create KnowledgeArticle object
                article = KnowledgeArticle(
                    id=source["id"],
                    title=source["title"],
                    content=source["content"],
                    category=source["category"],
                    tags=source.get("tags", []),
                    created_at=datetime.fromisoformat(source["created_at"]),
                    resolution_count=source.get("resolution_count", 0),
                    rating=source.get("rating")
                )

                # Create SearchResult
                result = SearchResult(
                    article=article,
                    score=hit["_score"],
                    relevance=self._get_relevance_description(hit["_score"])
                )
                results.append(result)

            return results
        except Exception as e:
            print(f"Error searching similar articles: {e}")
            return []

    async def hybrid_search(self,
                            query_text: str,
                            query_embedding: List[float],
                            category: Optional[str] = None,
                            top_k: int = 5) -> List[SearchResult]:
        """Perform hybrid search combining text and vector search"""
        try:
            # Text search part
            text_query = {
                "multi_match": {
                    "query": query_text,
                    "fields": ["title^2", "content", "tags"],
                    "type": "best_fields"
                }
            }

            # Vector search part
            vector_query = {
                "knn": {
                    "field": "embedding",
                    "query_vector": query_embedding,
                    "k": top_k,
                    "num_candidates": 100
                }
            }

            # Combine queries
            combined_query = {
                "bool": {
                    "should": [
                        {"match": text_query["multi_match"]},
                        vector_query
                    ],
                    "minimum_should_match": 1
                }
            }

            # Add category filter if specified
            if category:
                combined_query["bool"]["filter"] = {
                    "term": {"category": category}
                }

            response = await self.async_client.search(
                index=self.index_name,
                body={
                    "query": combined_query,
                    "size": top_k,
                    "_source": ["id", "title", "content", "category", "tags",
                                "created_at", "resolution_count", "rating"]
                }
            )

            results = []
            for hit in response["hits"]["hits"]:
                source = hit["_source"]

                article = KnowledgeArticle(
                    id=source["id"],
                    title=source["title"],
                    content=source["content"],
                    category=source["category"],
                    tags=source.get("tags", []),
                    created_at=datetime.fromisoformat(source["created_at"]),
                    resolution_count=source.get("resolution_count", 0),
                    rating=source.get("rating")
                )

                result = SearchResult(
                    article=article,
                    score=hit["_score"],
                    relevance=self._get_relevance_description(hit["_score"])
                )
                results.append(result)

            return results
        except Exception as e:
            print(f"Error in hybrid search: {e}")
            return []

    async def update_article_stats(self, article_id: str,
                                   increment_resolution: bool = True):
        """Update article statistics (resolution count, etc.)"""
        try:
            if increment_resolution:
                await self.async_client.update(
                    index=self.index_name,
                    id=article_id,
                    body={
                        "script": {
                            "source": "ctx._source.resolution_count += 1"
                        }
                    }
                )
        except Exception as e:
            print(f"Error updating article stats: {e}")

    def _get_relevance_description(self, score: float) -> str:
        """Convert numeric score to relevance description"""
        if score >= 0.8:
            return "Very High"
        elif score >= 0.6:
            return "High"
        elif score >= 0.4:
            return "Medium"
        elif score >= 0.2:
            return "Low"
        else:
            return "Very Low"

    async def close(self):
        """Close Elasticsearch connections"""
        if self.async_client:
            await self.async_client.close()


# Global Elasticsearch service instance
es_service = ElasticsearchService()