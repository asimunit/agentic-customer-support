#!/usr/bin/env python3
"""
Script to populate the Elasticsearch knowledge base with sample data.
This script loads the sample knowledge base articles and creates embeddings for them.
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add the project root to the path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

from backend.services.elasticsearch_service import es_service
from backend.services.embedding_service import embedding_service
from backend.models.schemas import KnowledgeArticle


def print_status(message):
    """Print status message"""
    print(f"✅ {message}")


def print_error(message):
    """Print error message"""
    print(f"❌ {message}")


def print_info(message):
    """Print info message"""
    print(f"ℹ️  {message}")


def print_progress(current, total, item_name="items"):
    """Print progress"""
    percent = (current / total) * 100
    print(f"📊 Progress: {current}/{total} {item_name} ({percent:.1f}%)")


async def load_sample_data() -> List[Dict[str, Any]]:
    """Load sample knowledge base data"""
    data_file = project_root / "data" / "sample_knowledge_base.json"

    if not data_file.exists():
        print_error(f"Sample data file not found: {data_file}")
        return []

    try:
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print_status(f"Loaded {len(data)} sample articles")
        return data

    except Exception as e:
        print_error(f"Failed to load sample data: {e}")
        return []


async def test_services():
    """Test that required services are available"""
    print_info("Testing services...")

    # Test Elasticsearch connection
    try:
        es_connected = await es_service.initialize()
        if not es_connected:
            print_error("Could not connect to Elasticsearch")
            print_info(
                "Make sure Elasticsearch is running on http://localhost:9200")
            return False
        print_status("Elasticsearch connection OK")
    except Exception as e:
        print_error(f"Elasticsearch connection failed: {e}")
        return False

    # Test embedding service
    try:
        # Try to encode a simple test text
        test_embedding = await embedding_service.encode_text("test")
        if not test_embedding:
            print_error("Embedding service failed")
            return False
        print_status(
            f"Embedding service OK (dimension: {len(test_embedding)})")
    except Exception as e:
        print_error(f"Embedding service failed: {e}")
        return False

    return True


async def create_knowledge_article(
        article_data: Dict[str, Any]) -> KnowledgeArticle:
    """Create a KnowledgeArticle object from raw data"""
    return KnowledgeArticle(
        id=article_data["id"],
        title=article_data["title"],
        content=article_data["content"],
        category=article_data["category"],
        tags=article_data.get("tags", []),
        created_at=datetime.fromisoformat(article_data["created_at"]),
        updated_at=datetime.fromisoformat(
            article_data["updated_at"]) if article_data.get(
            "updated_at") else None,
        resolution_count=article_data.get("resolution_count", 0),
        rating=article_data.get("rating")
    )


async def generate_embeddings_batch(articles: List[KnowledgeArticle],
                                    batch_size: int = 5) -> List[List[float]]:
    """Generate embeddings for articles in batches"""
    embeddings = []

    for i in range(0, len(articles), batch_size):
        batch = articles[i:i + batch_size]
        print_progress(min(i + batch_size, len(articles)), len(articles),
                       "embeddings")

        batch_texts = []
        for article in batch:
            # Combine title and content for better embeddings
            full_text = f"{article.title}. {article.content}"
            prepared_text = await embedding_service.prepare_text_for_embedding(
                full_text)
            batch_texts.append(prepared_text)

        try:
            batch_embeddings = await embedding_service.encode_batch(
                batch_texts)
            embeddings.extend(batch_embeddings)
        except Exception as e:
            print_error(
                f"Failed to generate embeddings for batch {i // batch_size + 1}: {e}")
            # Generate individual embeddings as fallback
            for text in batch_texts:
                try:
                    embedding = await embedding_service.encode_text(text)
                    embeddings.append(embedding)
                except Exception as e2:
                    print_error(
                        f"Failed to generate individual embedding: {e2}")
                    # Use zero vector as last resort
                    zero_embedding = [0.0] * embedding_service.get_embedding_dimension()
                    embeddings.append(zero_embedding)

    return embeddings


async def populate_knowledge_base(articles: List[KnowledgeArticle],
                                  embeddings: List[List[float]]):
    """Populate Elasticsearch with articles and embeddings"""
    print_info("Populating knowledge base...")

    success_count = 0

    for i, (article, embedding) in enumerate(zip(articles, embeddings)):
        try:
            success = await es_service.add_knowledge_article(article,
                                                             embedding)
            if success:
                success_count += 1

            print_progress(i + 1, len(articles), "articles")

        except Exception as e:
            print_error(f"Failed to add article {article.id}: {e}")

    print_status(
        f"Successfully added {success_count}/{len(articles)} articles to knowledge base")
    return success_count


async def verify_knowledge_base():
    """Verify that the knowledge base was populated correctly"""
    print_info("Verifying knowledge base...")

    try:
        # Test search with a simple query
        test_embedding = await embedding_service.create_query_embedding(
            "password reset")
        search_results = await es_service.search_similar(
            query_embedding=test_embedding,
            top_k=3
        )

        if search_results:
            print_status(
                f"Knowledge base verification successful - found {len(search_results)} results for test query")

            # Show top result
            top_result = search_results[0]
            print_info(
                f"Top result: '{top_result.article.title}' (score: {top_result.score:.3f})")

            return True
        else:
            print_error(
                "Knowledge base verification failed - no search results found")
            return False

    except Exception as e:
        print_error(f"Knowledge base verification failed: {e}")
        return False


async def main():
    """Main function"""
    print("📚 Knowledge Base Population Script")
    print("=" * 50)

    # Test services
    if not await test_services():
        print_error("Service tests failed. Please check your setup.")
        sys.exit(1)

    # Load sample data
    sample_data = await load_sample_data()
    if not sample_data:
        print_error("No sample data to process")
        sys.exit(1)

    # Create article objects
    print_info("Creating article objects...")
    articles = []
    for article_data in sample_data:
        try:
            article = await create_knowledge_article(article_data)
            articles.append(article)
        except Exception as e:
            print_error(
                f"Failed to create article {article_data.get('id', 'unknown')}: {e}")

    print_status(f"Created {len(articles)} article objects")

    if not articles:
        print_error("No valid articles to process")
        sys.exit(1)

    # Generate embeddings
    print_info("Generating embeddings...")
    embeddings = await generate_embeddings_batch(articles)

    if len(embeddings) != len(articles):
        print_error(
            f"Embedding count mismatch: {len(embeddings)} embeddings for {len(articles)} articles")
        sys.exit(1)

    print_status(f"Generated {len(embeddings)} embeddings")

    # Populate knowledge base
    success_count = await populate_knowledge_base(articles, embeddings)

    if success_count == 0:
        print_error("Failed to populate knowledge base")
        sys.exit(1)

    # Verify knowledge base
    if await verify_knowledge_base():
        print("\n" + "=" * 50)
        print_status("Knowledge base population completed successfully!")
        print("\nYou can now:")
        print(
            "1. Start the FastAPI backend: python -m uvicorn backend.main:app --reload")
        print(
            "2. Start the Streamlit frontend: streamlit run frontend/streamlit_app.py")
        print("3. Test the knowledge search in the web interface")
    else:
        print_error("Knowledge base population completed with errors")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())