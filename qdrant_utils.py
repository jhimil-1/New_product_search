# qdrant_utils.py
# gemini_utils.py
import os
from dotenv import load_dotenv
load_dotenv()  # 
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from config import (
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME
)

logger = logging.getLogger(__name__)

class QdrantManager:
    """Manager for Qdrant vector database operations"""
    
    def __init__(self):
        """Initialize Qdrant client"""
        self.client = QdrantClient(
            url=QDRANT_URL,
            api_key=QDRANT_API_KEY
        )
        self.collection_name = QDRANT_COLLECTION_NAME
        self._ensure_collection_exists()
    
    def _ensure_collection_exists(self, vector_size: int = 512):
        """Ensure the collection exists, create if it doesn't"""
        try:
            collections = self.client.get_collections()
            collection_names = [collection.name for collection in collections.collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                # Check if existing collection has correct vector size
                collection_info = self.client.get_collection(self.collection_name)
                existing_size = collection_info.config.params.vectors.size
                if existing_size != vector_size:
                    logger.warning(f"Collection {self.collection_name} has wrong vector size {existing_size}, expected {vector_size}. Recreating collection...")
                    self.client.delete_collection(self.collection_name)
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=models.VectorParams(
                            size=vector_size,
                            distance=models.Distance.COSINE
                        )
                    )
                    logger.info(f"Recreated collection: {self.collection_name} with correct vector size")
                else:
                    logger.info(f"Using existing collection: {self.collection_name}")
                
        except UnexpectedResponse as e:
            logger.error(f"Error creating Qdrant collection: {e}")
            raise
    
    def recreate_collection(self, vector_size: int = 512):
        """Recreate the collection with the specified vector size"""
        try:
            # Delete existing collection if it exists
            try:
                self.client.delete_collection(self.collection_name)
                logger.info(f"Deleted existing collection: {self.collection_name}")
            except Exception:
                # Collection might not exist, which is fine
                pass
            
            # Create new collection
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=vector_size,
                    distance=models.Distance.COSINE
                )
            )
            logger.info(f"Created collection: {self.collection_name} with vector size {vector_size}")
            
        except Exception as e:
            logger.error(f"Error recreating collection: {e}")
            raise
    
    def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 10,
        category_filter: Optional[str] = None,
        min_score: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Search for similar vectors in Qdrant with optional category filtering"""
        try:
            # Build filter query if category is specified
            query_filter = None
            if category_filter:
                # Create payload index for category if it doesn't exist
                try:
                    self.client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name="category",
                        field_schema=models.PayloadSchemaType.KEYWORD
                    )
                except Exception:
                    # Index might already exist, which is fine
                    pass
                
                # Try exact match first, then fallback to case-insensitive match
                query_filter = models.Filter(
                    must=[
                        models.FieldCondition(
                            key="category",
                            match=models.MatchValue(value=category_filter)
                        )
                    ]
                )
            
            # Try search with exact category match first
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=limit,
                score_threshold=min_score
            )
            
            # If no results and category filter is applied, try case-insensitive variations
            if not search_results and category_filter:
                # Try different case variations
                case_variations = [
                    category_filter.capitalize(),  # rings -> Rings
                    category_filter.lower(),       # RINGS -> rings
                    category_filter.upper()        # rings -> RINGS
                ]
                
                for variation in case_variations:
                    if variation == category_filter:
                        continue  # Skip if same as original
                    
                    alt_filter = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="category",
                                match=models.MatchValue(value=variation)
                            )
                        ]
                    )
                    
                    search_results = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=query_embedding,
                        query_filter=alt_filter,
                        limit=limit,
                        score_threshold=min_score
                    )
                    
                    if search_results:
                        logger.info(f"Found results using case variation: {variation}")
                        break
            
            results = []
            for hit in search_results:
                try:
                    # Skip results without required fields
                    if not hit.payload:
                        continue
                        
                    # Get product ID, preferring mongo_id if available
                    product_id = hit.payload.get("mongo_id") or str(hit.id)
                    if not product_id:
                        continue
                    
                    # Get product's jewelry type if available
                    product_jewelry_type = hit.payload.get("jewelry_type", "").lower()
                    
                    # Calculate base relevance score (inverted distance, higher is better)
                    # Scale to 0-1 range where 1 is perfect match
                    relevance_score = float(hit.score) if hit.score is not None else 0.0
                    
                    # Boost score for exact matches on important fields
                    if category_filter and hit.payload.get("category", "").lower() == category_filter.lower():
                        relevance_score = min(1.0, relevance_score * 1.1)  # 10% boost for exact category match
                    
                    # Boost score for exact jewelry type matches
                    if product_jewelry_type:
                        relevance_score = min(1.0, relevance_score * 1.2)  # 20% boost for exact jewelry type match
                    
                    result = {
                        "id": product_id,
                        "score": float(hit.score) if hit.score is not None else 0.0,
                        "relevance_score": relevance_score,
                        "payload": hit.payload
                    }
                    
                    # Add any additional fields from payload
                    for field in ["name", "description", "category", "jewelry_type", "image_url"]:
                        if field in hit.payload:
                            result[field] = hit.payload[field]
                    
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing search result: {str(e)}", exc_info=True)
                    continue
            
            # Sort by relevance score (highest first)
            results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            
            # Limit results after all processing
            results = results[:limit]
            
            logger.info(f"Found {len(results)} matching products")
            return results
            
        except Exception as e:
            logger.error(f"Error in search_similar: {str(e)}", exc_info=True)
            # Return empty list instead of raising to prevent breaking the search
            return []
    
    def search_similar_products(
        self, 
        query_embedding: List[float], 
        user_id: Optional[str] = None,
        category_filter: Optional[str] = None,
        jewelry_type: Optional[str] = None,
        limit: int = 10,  # Increased default limit
        min_score: float = 0.05  # Lowered minimum score threshold for better recall
    ) -> List[Dict[str, Any]]:
        """
        Search for similar products using vector similarity with user filtering
        
        Args:
            query_embedding: Query vector embedding
            user_id: Optional user ID to filter results (username)
            category_filter: Optional category to filter results
            jewelry_type: Optional jewelry type to filter by (e.g., 'ring', 'necklace')
            limit: Maximum number of results
            min_score: Minimum similarity score threshold
            
        Returns:
            List of similar products with scores
        """
        try:
            # Build filter for user-specific and category search
            query_filter = None
            filter_conditions = []
            category_should_conditions = []
            jewelry_type_conditions = []
            
            # Only filter by user_id if provided, but don't make it required
            if user_id:
                try:
                    # Check if created_by index exists, create if not
                    try:
                        self.client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name="created_by",
                            field_schema=models.PayloadSchemaType.KEYWORD
                        )
                        logger.info(f"Created payload index for 'created_by' field")
                    except Exception as e:
                        # Index might already exist, which is fine
                        logger.debug(f"Payload index for 'created_by' already exists or error: {str(e)}")
                    
                    filter_conditions.append(
                        models.FieldCondition(
                            key="created_by",
                            match=models.MatchValue(value=user_id)
                        )
                    )
                    logger.info(f"Filtering by user_id: {user_id}")
                except Exception as e:
                    logger.warning(f"Error filtering by user_id: {str(e)} - falling back to all users")
                    # Continue without user filter if there's an error
            
            if category_filter:
                try:
                    # Try to create payload index for category (will fail if exists, which is fine)
                    try:
                        self.client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name="category",
                            field_schema=models.PayloadSchemaType.KEYWORD
                        )
                        logger.info(f"Created payload index for 'category' field")
                    except Exception as e:
                        logger.debug(f"Payload index for 'category' already exists or error: {str(e)}")
                    
                    # Add category filter - try exact match first, then case variations
                    category_variations = [
                        category_filter,                    # Original
                        category_filter.lower(),          # lowercase
                        category_filter.capitalize(),     # Capitalized
                        category_filter.upper()           # UPPERCASE
                    ]
                    
                    # Use Should condition to match any of the variations
                    category_conditions = []
                    for variation in category_variations:
                        category_conditions.append(
                            models.FieldCondition(
                                key="category",
                                match=models.MatchValue(value=variation)
                            )
                        )
                    
                    # Store category conditions for later combination
                    category_should_conditions = category_conditions
                    logger.info(f"Filtering by category: {category_filter}")
                except Exception as e:
                    logger.warning(f"Error filtering by category: {str(e)} - falling back to all categories")
                    # Continue without category filter if there's an error
            
            # Add jewelry type filter if specified
            if jewelry_type:
                try:
                    # Create payload index for jewelry_type if it doesn't exist
                    try:
                        self.client.create_payload_index(
                            collection_name=self.collection_name,
                            field_name="jewelry_type",
                            field_schema=models.PayloadSchemaType.KEYWORD
                        )
                        logger.info("Created payload index for 'jewelry_type' field")
                    except Exception as e:
                        logger.debug(f"Payload index for 'jewelry_type' already exists or error: {str(e)}")
                    
                    # Add jewelry type filter - try exact match first, then case variations
                    jewelry_variations = [
                        jewelry_type,                    # Original
                        jewelry_type.lower(),           # lowercase
                        jewelry_type.capitalize(),      # Capitalized
                        jewelry_type.upper()            # UPPERCASE
                    ]
                    
                    # Add jewelry type conditions
                    for variation in jewelry_variations:
                        jewelry_type_conditions.append(
                            models.FieldCondition(
                                key="jewelry_type",
                                match=models.MatchValue(value=variation)
                            )
                        )
                    
                    logger.info(f"Filtering by jewelry type: {jewelry_type}")
                except Exception as e:
                    logger.warning(f"Error filtering by jewelry type: {str(e)} - falling back to all types")
            
            # Build final filter combining must and should conditions
            if filter_conditions or category_should_conditions or jewelry_type_conditions:
                all_must_conditions = []
                
                # Add user_id filter conditions if they exist
                if filter_conditions:
                    all_must_conditions.extend(filter_conditions)
                
                # Add category filter conditions if they exist
                if category_should_conditions:
                    # For category, we need to use should conditions within a must clause
                    # to match any of the category variations
                    category_values = [condition.match.value for condition in category_should_conditions]
                    all_must_conditions.append(
                        models.FieldCondition(
                            key="category",
                            match=models.MatchAny(any=category_values)
                        )
                    )
                
                # Add jewelry type conditions if they exist
                if jewelry_type_conditions:
                    # For jewelry_type, we need to use should conditions within a must clause
                    # to match any of the jewelry type variations
                    jewelry_values = [condition.match.value for condition in jewelry_type_conditions]
                    all_must_conditions.append(
                        models.FieldCondition(
                            key="jewelry_type",
                            match=models.MatchAny(any=jewelry_values)
                        )
                    )
                
                query_filter = models.Filter(must=all_must_conditions)
            else:
                query_filter = None
            
            # Log search parameters
            logger.info(f"Searching with params: limit={limit}, min_score={min_score}, filters={query_filter}")
            
            try:
                # Always honor user isolation when user_id is provided.
                search_results = self.client.search(
                    collection_name=self.collection_name,
                    query_vector=query_embedding,
                    query_filter=query_filter,
                    limit=limit,
                    score_threshold=min_score,
                    with_payload=True,
                    with_vectors=False
                )

                # If no results and a user_id is provided, relax only the score threshold but keep the user filter.
                if user_id and not search_results:
                    logger.info("No results; retrying with relaxed threshold while keeping user filter")
                    relaxed_must_conditions = [
                        models.FieldCondition(
                            key="created_by",
                            match=models.MatchValue(value=user_id)
                        )
                    ]
                    # Keep category/jewelry constraints if they existed originally
                    if category_filter:
                        category_values = [category_filter, category_filter.lower(), category_filter.capitalize(), category_filter.upper()]
                        relaxed_must_conditions.append(
                            models.FieldCondition(
                                key="category",
                                match=models.MatchAny(any=category_values)
                            )
                        )
                    if jewelry_type:
                        jewelry_values = [jewelry_type, jewelry_type.lower(), jewelry_type.capitalize(), jewelry_type.upper()]
                        relaxed_must_conditions.append(
                            models.FieldCondition(
                                key="jewelry_type",
                                match=models.MatchAny(any=jewelry_values)
                            )
                        )
                    relaxed_filter = models.Filter(must=relaxed_must_conditions)
                    search_results = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=query_embedding,
                        query_filter=relaxed_filter,
                        limit=limit,
                        score_threshold=min_score * 0.5,
                        with_payload=True,
                        with_vectors=False
                    )
            except Exception as e:
                logger.error(f"Error during search: {str(e)}")
                # Return empty results instead of falling back to unfiltered search
                search_results = []
            
            # If no results and category filter is applied, try case-insensitive variations
            if not search_results and category_filter:
                # Try different case variations
                case_variations = [
                    category_filter.capitalize(),  # laptops -> Laptops
                    category_filter.lower(),       # Laptops -> laptops
                    category_filter.upper()        # laptops -> LAPTOPS
                ]
                
                for variation in case_variations:
                    if variation == category_filter:
                        continue  # Skip if same as original
                    
                    # Build alternative filter with case variation
                    alt_filter_conditions = []
                    
                    if user_id:
                        alt_filter_conditions.append(
                            models.FieldCondition(
                                key="created_by",
                                match=models.MatchValue(value=user_id)
                            )
                        )
                    
                    alt_filter_conditions.append(
                        models.FieldCondition(
                            key="category",
                            match=models.MatchValue(value=variation)
                        )
                    )
                    
                    alt_filter = models.Filter(must=alt_filter_conditions)
                    
                    # Try search with case variation
                    search_results = self.client.search(
                        collection_name=self.collection_name,
                        query_vector=query_embedding,
                        query_filter=alt_filter,
                        limit=limit,
                        score_threshold=min_score,
                        with_payload=True,
                        with_vectors=False
                    )
                    
                    if search_results:
                        logger.info(f"Found results using case variation: {variation}")
                        break
            
            # Format results and remove duplicates
            products = []
            seen_product_ids = set()  # Track seen product IDs to avoid duplicates
            
            for result in search_results:
                product_id = result.payload.get("mongo_id", str(result.id))
                
                # Skip if we've already seen this product
                if product_id in seen_product_ids:
                    continue
                    
                product = {
                    "product_id": product_id,
                    "name": result.payload.get("name", ""),
                    "category": result.payload.get("category", ""),
                    "price": result.payload.get("price", 0.0),
                    "description": result.payload.get("description", ""),
                    "score": result.score,
                    "image_url": result.payload.get("image_url", ""),
                    "image_path": result.payload.get("image_path", ""),
                    "image": result.payload.get("image", ""),
                    "payload": result.payload  # Include full payload for backward compatibility
                }
                
                products.append(product)
                seen_product_ids.add(product_id)  # Mark this product ID as seen
            
            logger.info(f"Found {len(products)} unique similar products for user {user_id}")
            return products
        
        except Exception as e:
            logger.error(f"Error searching products: {str(e)}")
            return []
    
    def upsert_product(
        self,
        product_id: str,
        text_embedding: List[float],
        image_embedding: Optional[List[float]] = None,
        category: Optional[str] = None,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """Upsert product vector into Qdrant with optional image embedding"""
        try:
            # Convert MongoDB ObjectId string to integer hash for Qdrant point ID
            import hashlib
            point_id = int(hashlib.md5(product_id.encode()).hexdigest(), 16) % (10**18)
            
            # Prepare payload with original MongoDB ID and category
            payload = metadata or {}
            payload["mongo_id"] = product_id
            if category:
                payload["category"] = category
            
            # Use text embedding as primary vector, or combine with image if available
            if image_embedding and text_embedding:
                # Combine text and image embeddings (weighted average)
                combined_vector = [
                    0.7 * t + 0.3 * i 
                    for t, i in zip(text_embedding, image_embedding)
                ]
                vector = combined_vector
            else:
                vector = text_embedding
            
            # Create point
            point = models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
            
            # Upsert the point
            operation_info = self.client.upsert(
                collection_name=self.collection_name,
                points=[point]
            )
            
            logger.info(f"Product upserted successfully: {product_id} (category: {category})")
            return True
            
        except Exception as e:
            logger.error(f"Error upserting product {product_id}: {str(e)}")
            return False


# Initialize a global instance
qdrant_manager = QdrantManager()
