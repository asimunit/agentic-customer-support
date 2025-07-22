from sentence_transformers import SentenceTransformer
import numpy as np
from typing import List, Union
import asyncio
from config.settings import settings


class EmbeddingService:
    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL
        self.model = None
        self._load_model()

    def _load_model(self):
        """Load the mxbai embedding model"""
        try:
            self.model = SentenceTransformer(self.model_name)
            print(f"Successfully loaded embedding model: {self.model_name}")
        except Exception as e:
            print(f"Error loading embedding model: {e}")
            # Fallback to a smaller model if mxbai fails
            try:
                self.model = SentenceTransformer('all-MiniLM-L6-v2')
                print("Loaded fallback embedding model: all-MiniLM-L6-v2")
            except Exception as fallback_error:
                raise Exception(
                    f"Failed to load any embedding model: {fallback_error}")

    async def encode_text(self, text: str) -> List[float]:
        """Generate embeddings for a single text"""
        if not self.model:
            raise Exception("Embedding model not loaded")

        try:
            # Run in thread to avoid blocking
            embedding = await asyncio.to_thread(
                self.model.encode,
                text,
                convert_to_numpy=True
            )
            return embedding.tolist()
        except Exception as e:
            raise Exception(f"Error generating embedding: {str(e)}")

    async def encode_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts"""
        if not self.model:
            raise Exception("Embedding model not loaded")

        try:
            # Run in thread to avoid blocking
            embeddings = await asyncio.to_thread(
                self.model.encode,
                texts,
                convert_to_numpy=True,
                batch_size=8  # Process in small batches
            )
            return embeddings.tolist()
        except Exception as e:
            raise Exception(f"Error generating batch embeddings: {str(e)}")

    def cosine_similarity(self,
                          embedding1: List[float],
                          embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings"""
        try:
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)

            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
        except Exception as e:
            print(f"Error calculating cosine similarity: {e}")
            return 0.0

    async def prepare_text_for_embedding(self, text: str) -> str:
        """Clean and prepare text for embedding generation"""
        # Remove excessive whitespace
        text = " ".join(text.split())

        # Truncate if too long (models have token limits)
        max_length = 500  # Adjust based on model requirements
        if len(text) > max_length:
            text = text[:max_length] + "..."

        return text

    async def create_query_embedding(self, query: str) -> List[float]:
        """Create embedding specifically for search queries"""
        # Add prefix to help with retrieval performance
        prepared_query = f"search query: {query}"
        prepared_query = await self.prepare_text_for_embedding(prepared_query)
        return await self.encode_text(prepared_query)

    async def create_document_embedding(self, document: str) -> List[float]:
        """Create embedding specifically for documents"""
        # Add prefix for document context
        prepared_doc = f"knowledge article: {document}"
        prepared_doc = await self.prepare_text_for_embedding(prepared_doc)
        return await self.encode_text(prepared_doc)

    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings produced by the model"""
        if self.model:
            return self.model.get_sentence_embedding_dimension()
        return settings.EMBEDDING_DIMENSION


# Global embedding service instance
embedding_service = EmbeddingService()