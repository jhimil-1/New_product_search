from datetime import datetime
import logging
from typing import List, Dict, Any
from bson import ObjectId
import requests
from database import MongoDB
from qdrant_utils import qdrant_manager
from clip_utils import clip_manager

logger = logging.getLogger(__name__)

class ProductHandler:
    def __init__(self):
        self.db = MongoDB.get_db()
        self.logger = logging.getLogger(__name__)
        
        # Enhanced category keywords for better detection
        self.category_keywords = {
            "clothing": {
                "primary": ["clothes", "clothing", "dress", "dresses", "apparel", "wear", "outfit", "fashion"],
                "types": ["shirt", "pants", "jeans", "jacket", "coat", "skirt", "blouse", "sweater", "top", "bottom", "trousers", "t-shirt"],
                "attributes": ["casual", "formal", "summer", "winter", "men", "women", "unisex", "kids", "baby"]
            },
            "electronics": {
                "primary": ["electronics", "tech", "gadget", "device", "digital", "technology"],
                "types": ["phone", "smartphone", "laptop", "computer", "tablet", "tv", "camera", "headphones", "speaker", "monitor"],
                "brands": ["apple", "samsung", "sony", "lg", "dell", "hp", "lenovo", "xiaomi", "google"]
            },
            "jewelry": {
                "primary": ["jewelry", "jewellery", "accessories", "accessory"],
                "types": ["necklace", "necklaces", "pendant", "chain", "ring", "rings", "earring", "earrings", "bracelet", "bracelets", "watch", "watches", "anklet", "brooch"],
                "materials": ["gold", "silver", "diamond", "pearl", "platinum", "rose gold", "white gold", "yellow gold", "sterling"]
            }
        }
    
    async def process_product_upload(self, products: List[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        """Process and store uploaded products"""
        try:
            products_to_insert = []
            current_time = datetime.utcnow()
            
            for product in products:
                # Extract fields
                name = product.get("name", "")
                description = product.get("description", "")
                price = product.get("price", 0.0)
                category = product.get("category", "")
                image_data = product.get("image", "")  # Base64 encoded image
                
                # Generate text embedding using CLIP for consistency
                text_content = f"{name} {description} {category}"
                text_embedding = clip_manager.get_text_embedding(text_content)
                
                # Generate image embedding using CLIP if image provided
                image_embedding = None
                if image_data:
                    try:
                        # Handle image URLs from JSON files
                        if image_data.startswith('http'):
                            # Download image from URL
                            import requests
                            response = requests.get(image_data, timeout=10)
                            response.raise_for_status()
                            image_bytes = response.content
                            image_embedding = clip_manager.get_image_embedding(image_bytes)
                        else:
                            # Handle base64 or other formats
                            image_embedding = clip_manager.get_image_embedding(image_data)
                    except Exception as img_error:
                        logger.warning(f"Failed to generate image embedding: {img_error}")
                
                product_doc = {
                    **product,
                    "text_embedding": text_embedding,
                    "image_embedding": image_embedding,
                    "created_at": current_time,
                    "updated_at": current_time,
                    "created_by": user_id,
                    "is_active": True
                }
                products_to_insert.append(product_doc)
            
            # Insert into MongoDB
            if products_to_insert:
                result = self.db.products.insert_many(products_to_insert)
                inserted_ids = [str(id) for id in result.inserted_ids]
                
                # Generate & store embeddings in Qdrant
                await self._generate_and_store_embeddings(products_to_insert, inserted_ids, user_id)
                
                return {
                    "inserted_count": len(inserted_ids),
                    "product_ids": inserted_ids
                }
            
            return {"inserted_count": 0}
        
        except Exception as e:
            logger.error(f"Error in process_product_upload: {str(e)}", exc_info=True)
            raise
    
    async def _generate_and_store_embeddings(self, products: List[Dict[str, Any]], product_ids: List[str], user_id: str):
        """Generate and store vector embeddings for products"""
        try:
            for product, product_id in zip(products, product_ids):
                text = f"{product['name']} {product['description']} {product['category']}"
                
                # Use CLIP embeddings for all products to ensure consistency with Qdrant collection
                embedding = clip_manager.get_text_embedding(text)
                
                # Prepare metadata with image information
                metadata = {
                    "name": product["name"],
                    "price": product["price"],
                    "created_by": user_id
                }
                
                # Include image information if available
                if "image" in product and product["image"]:
                    metadata["image_url"] = product["image"]
                if "image_url" in product and product["image_url"]:
                    metadata["image_url"] = product["image_url"]
                if "image_path" in product and product["image_path"]:
                    metadata["image_path"] = product["image_path"]
                
                qdrant_manager.upsert_product(
                    product_id=product_id,
                    text_embedding=embedding,
                    category=product["category"],
                    metadata=metadata
                )
        except Exception as e:
            logger.error(f"Error generating/storing embeddings: {str(e)}", exc_info=True)
            pass

    def _is_valid_objectid(self, user_id: str) -> bool:
        """Check if user_id is a valid MongoDB ObjectId format"""
        if not user_id or len(user_id) != 24:
            return False
        try:
            int(user_id, 16)  # Check if it's a valid hex string
            return all(c in '0123456789abcdefABCDEF' for c in user_id)
        except ValueError:
            return False

    def _normalize_user_id(self, user_id: str) -> str:
        """Normalize user ID format and handle both UUID and ObjectId"""
        if not user_id:
            return None
            
        # If it's already a UUID format (contains hyphens or is 36 chars), return as-is
        if '-' in user_id or len(user_id) == 36:
            return user_id
            
        # If it looks like an ObjectId, return as-is
        if self._is_valid_objectid(user_id):
            return user_id
            
        # Otherwise, treat as username and return as-is
        return user_id

    def _validate_product_data(self, product: Dict[str, Any]) -> bool:
        """Validate product data integrity"""
        try:
            # Required fields
            if not product.get("_id"):
                logger.warning("Product missing _id field")
                return False
            
            # Validate price
            price = product.get("price", 0)
            if isinstance(price, str):
                try:
                    price = float(price)
                except (ValueError, TypeError):
                    logger.warning(f"Invalid price string: {price}")
                    return False
            if not isinstance(price, (int, float)) or price < 0:
                logger.warning(f"Invalid price value: {price}")
                return False
            
            # Validate name
            name = product.get("name", "")
            if not name or not isinstance(name, str) or len(name.strip()) == 0:
                logger.warning("Product missing or invalid name")
                return False
            
            # Validate category
            category = product.get("category", "")
            if category and not isinstance(category, str):
                logger.warning(f"Invalid category type: {type(category)}")
                return False
            
            # Validate image_url if present
            image_url = product.get("image_url")
            if image_url and not isinstance(image_url, str):
                logger.warning(f"Invalid image_url type: {type(image_url)}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating product data: {e}")
            return False

    def _calculate_relevance_score(self, product: Dict[str, Any], query: str, category: str, similarity_score: float) -> float:
        """Calculate enhanced relevance score based on multiple factors"""
        try:
            base_score = similarity_score * 100  # Base score from vector similarity
            relevance_score = base_score
            
            if not query:
                return base_score
            
            query_lower = query.lower().strip()
            product_name = (product.get("name", "") or "").lower()
            product_description = (product.get("description", "") or "").lower()
            product_category = (product.get("category", "") or "").lower()
            
            # Query-keyword matching bonus
            query_words = query_lower.split()
            name_words = product_name.split()
            description_words = product_description.split()[:50]  # Limit description words
            
            # Name matching (higher weight)
            name_matches = sum(1 for qw in query_words if any(qw in nw for nw in name_words))
            name_match_ratio = name_matches / len(query_words) if query_words else 0
            relevance_score += name_match_ratio * 20
            
            # Description matching (lower weight)
            desc_matches = sum(1 for qw in query_words if any(qw in dw for dw in description_words))
            desc_match_ratio = desc_matches / len(query_words) if query_words else 0
            relevance_score += desc_match_ratio * 10
            
            # Category matching bonus
            if category and category.lower() in product_category:
                relevance_score += 15
            
            # Exact phrase matching (higher bonus)
            if query_lower in product_name:
                relevance_score += 25
            elif query_lower in product_description[:200]:  # Check first 200 chars of description
                relevance_score += 15
            
            # Price reasonableness (products with reasonable prices get slight bonus)
            price = product.get("price", 0)
            try:
                price = float(price) if price is not None else 0
                if 10 <= price <= 10000:  # Reasonable price range
                    relevance_score += 5
            except (ValueError, TypeError):
                # Skip price bonus if price is invalid
                pass
            
            # In-stock bonus
            if product.get("in_stock", True):
                relevance_score += 3
            
            # Normalize final score
            return min(max(0, relevance_score), 100)
            
        except Exception as e:
            logger.error(f"Error calculating relevance score: {e}")
            return similarity_score * 100

    def _detect_category_from_query(self, query: str) -> str:
        """
        Enhanced category detection with comprehensive keyword matching
        
        Args:
            query: The search query to analyze
            
        Returns:
            str: Detected category name or None if no clear match
        """
        if not query:
            logger.debug("No query provided for category detection")
            return None
            
        query_lower = query.lower().strip()
        logger.debug(f"Detecting category from query: {query_lower}")
        
        # Special handling for jewelry-related queries
        jewelry_terms = [
            'jewelry', 'jewellery', 'necklace', 'ring', 'earring', 'bracelet', 
            'pendant', 'chain', 'bangle', 'anklet', 'brooch', 'gemstone',
            'diamond', 'gold', 'silver', 'platinum', 'pearl', 'crystal'
        ]
        
        # Check for jewelry terms first with exact matching
        for term in jewelry_terms:
            if f' {term} ' in f' {query_lower} ':
                logger.debug(f"Detected jewelry term in query: {term}")
                return 'jewelry'
        
        # Score each category based on keyword matches
        category_scores = {}
        
        for category, keywords in self.category_keywords.items():
            score = 0
            
            # Check primary keywords (higher weight)
            for keyword in keywords["primary"]:
                if f' {keyword} ' in f' {query_lower} ':
                    score += 3
                    logger.debug(f"Matched primary keyword '{keyword}' for category '{category}'")
                    
            # Check type keywords (medium weight)
            if "types" in keywords:
                for keyword in keywords["types"]:
                    if f' {keyword} ' in f' {query_lower} ':
                        score += 2
                        logger.debug(f"Matched type keyword '{keyword}' for category '{category}'")
                        
            # Check other keywords (lower weight)
            for key in ["attributes", "brands", "materials"]:
                if key in keywords:
                    for keyword in keywords[key]:
                        if f' {keyword} ' in f' {query_lower} ':
                            score += 1
                            logger.debug(f"Matched {key} keyword '{keyword}' for category '{category}'")
            
            if score > 0:
                category_scores[category] = score
        
        # Log the category scores for debugging
        if category_scores:
            logger.debug(f"Category scores: {category_scores}")
        else:
            logger.debug("No category keywords matched in query")
        
        # Return the category with highest score, or None if no matches
        if not category_scores:
            return None
            
        detected_category = max(category_scores.items(), key=lambda x: x[1])[0]
        logger.debug(f"Detected category: {detected_category}")
        return detected_category

    async def search_jewelry(
        self,
        query: str = None,
        image_bytes: bytes = None,
        user_id: str = None,
        jewelry_type: str = None,
        limit: int = 10,
        min_score: float = 0.2
    ) -> Dict[str, Any]:
        """
        Specialized search for jewelry items with better type filtering.
        
        Args:
            query: Text query (e.g., "gold necklace")
            image_bytes: Image data as bytes
            user_id: User ID for filtering
            jewelry_type: Specific type of jewelry (e.g., "necklace", "ring")
            limit: Maximum number of results
            min_score: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            logger.info(f"Starting jewelry search - Query: '{query}', Type: {jewelry_type}")
            
            # Normalize user ID format
            normalized_user_id = self._normalize_user_id(user_id) if user_id else None
            
            # Enhance query with jewelry context if needed
            enhanced_query = query or ""
            if query and not any(word in query.lower() for word in ["jewelry", "jewellery"]):
                enhanced_query = f"{query} jewelry"
            
            # Generate embeddings
            query_embedding = None
            if enhanced_query and image_bytes:
                # Combine text and image embeddings (60% text, 40% image)
                text_embedding = clip_manager.get_text_embedding(enhanced_query)
                image_embedding = clip_manager.get_image_embedding(image_bytes)
                query_embedding = [0.6 * t + 0.4 * i for t, i in zip(text_embedding, image_embedding)]
            elif enhanced_query:
                query_embedding = clip_manager.get_text_embedding(enhanced_query)
            elif image_bytes:
                query_embedding = clip_manager.get_image_embedding(image_bytes)
            
            if query_embedding is None:
                raise ValueError("Either query text or image must be provided")
            
            # Build filter conditions for jewelry
            filter_conditions = {"category": {"$regex": "jewel(r?y|ies)", "$options": "i"}}
            
            # Add jewelry type filter if specified
            if jewelry_type:
                filter_conditions["name"] = {"$regex": jewelry_type, "$options": "i"}
            
            # Add user filter if specified
            if normalized_user_id:
                filter_conditions["user_id"] = normalized_user_id
            
            # Debug: Check how many jewelry products exist in the database
            jewelry_count = self.db.products.count_documents({"category": {"$regex": "jewel(r?y|ies)", "$options": "i"}})
            logger.info(f"Found {jewelry_count} jewelry products in the database")
            
            # Debug: Log a sample of jewelry products
            if jewelry_count > 0:
                sample_products = list(self.db.products.find(
                    {"category": {"$regex": "jewel(r?y|ies)", "$options": "i"}},
                    {"name": 1, "category": 1, "user_id": 1, "_id": 0}
                ).limit(3))
                logger.info(f"Sample jewelry products: {sample_products}")
            
            logger.info(f"Searching jewelry with filter: {filter_conditions}")
            
            # Log the query embedding for debugging
            logger.info(f"Searching with embedding (first 5 dims): {query_embedding[:5] if query_embedding else 'None'}")
            
            # Make search more lenient by lowering the min_score if it's too high
            effective_min_score = max(0.1, min_score)  # Ensure min_score is not too high
            
            # Temporarily remove user filter to see more results
            user_id_filter = filter_conditions.pop("user_id", None)
            
            # Get user ID for filtering if available
            user_id = filter_conditions.pop("user_id", None)
            
            # Search Qdrant with the embedding using search_similar_products
            # For jewelry, use exact category name instead of regex pattern
            category_filter = None
            if filter_conditions.get("category", {}).get("$regex") == "jewel(r?y|ies)":
                category_filter = "Jewellery"  # Use exact category name for Qdrant (British spelling)
            elif filter_conditions.get("category", {}).get("$regex") == "clothing":
                category_filter = "Clothes"  # Map "clothing" to "Clothes" for Qdrant
            else:
                category_filter = filter_conditions.get("category", {}).get("$regex")
            
            search_results = qdrant_manager.search_similar_products(
                query_embedding=query_embedding,
                user_id=user_id,
                category_filter=category_filter,
                limit=limit * 5,  # Get more results for better filtering
                min_score=effective_min_score
            )
            
            if not isinstance(search_results, list):
                logger.error(f"Unexpected search results type: {type(search_results)}")
                return {
                    "results": [],
                    "query": query or "",
                    "jewelry_type": jewelry_type,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            logger.info(f"Found {len(search_results)} potential matches before filtering")
            
            if not search_results:
                logger.warning("No search results returned from Qdrant")
                return {
                    "results": [],
                    "query": query or "",
                    "jewelry_type": jewelry_type,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            # Get product details from MongoDB for the search results
            product_ids = []
            for item in search_results:
                try:
                    # Handle both dictionary and object access for backward compatibility
                    # Qdrant results have mongo_id in payload
                    if hasattr(item, 'payload'):
                        product_id = item.payload.get('mongo_id')
                    elif isinstance(item, dict) and 'payload' in item:
                        product_id = item['payload'].get('mongo_id')
                    elif hasattr(item, 'id'):
                        product_id = item.id
                    else:
                        product_id = item.get('id')
                    
                    if product_id:
                        product_ids.append(ObjectId(product_id))
                except Exception as e:
                    logger.warning(f"Error processing search result item: {str(e)}")
            
            if not product_ids:
                logger.warning("No valid product IDs found in search results")
                return {
                    "results": [],
                    "query": query or "",
                    "jewelry_type": jewelry_type,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            # Fetch all products in a single query for better performance
            products_map = {
                str(product["_id"]): product 
                for product in self.db.products.find({"_id": {"$in": product_ids}})
            }
            
            # Process and rank results
            results = []
            for item in search_results:
                try:
                    # Handle both dictionary and object access for backward compatibility
                    if hasattr(item, 'payload'):
                        product_id = str(item.payload.get('mongo_id', ''))
                        score = getattr(item, 'score', 0)
                        payload = item.payload
                    elif isinstance(item, dict) and 'payload' in item:
                        product_id = str(item['payload'].get('mongo_id', ''))
                        score = item.get('score', 0)
                        payload = item['payload']
                    elif hasattr(item, 'id'):
                        product_id = str(item.id)
                        score = getattr(item, 'score', 0)
                        payload = getattr(item, 'payload', {})
                    else:
                        product_id = str(item.get('id', ''))
                        score = item.get('score', 0)
                        payload = item.get('payload', {})
                    
                    if not product_id or product_id == 'None':
                        logger.debug("Skipping item with missing or invalid product ID")
                        continue
                        
                    product = products_map.get(product_id)
                    if not product:
                        logger.warning(f"Product not found in MongoDB: {product_id}")
                        continue
                    
                    # Log product details for debugging
                    product_name = product.get('name', 'Unnamed Product')
                    logger.debug(f"Processing product: {product_name} (ID: {product_id})")
                    
                    # Calculate relevance score with bonus for type matches
                    relevance_score = float(score)
                    
                    # Boost score if product name contains the jewelry type
                    if jewelry_type and jewelry_type.lower() in product_name.lower():
                        relevance_score *= 1.5
                        logger.debug(f"Boosted score for {product_name} - New score: {relevance_score}")
                    
                    # Get additional fields from payload if available
                    product_category = payload.get('category', product.get('category', ''))
                    
                    # Add to results
                    results.append({
                        "id": product_id,
                        "name": product_name,
                        "description": product.get("description", ""),
                        "price": float(product.get("price", 0)),
                        "category": product_category,
                        "image_url": product.get("image_url", ""),
                        "similarity_score": float(score),
                        "relevance_score": relevance_score
                    })
                except Exception as e:
                    logger.error(f"Error processing search result: {str(e)}", exc_info=True)
                    continue
            
            # Sort by relevance score (highest first)
            results.sort(key=lambda x: x["relevance_score"], reverse=True)
            
            # Apply limit
            results = results[:limit]
            
            if not results:
                logger.warning("No jewelry items found matching the query after filtering")
                return {
                    "results": [],
                    "query": query or "",
                    "jewelry_type": jewelry_type,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
            
            logger.info(f"Found {len(results)} jewelry items (top score: {results[0]['similarity_score']:.3f})")
            for i, r in enumerate(results[:3], 1):
                logger.info(f"  {i}. {r['name']} (Score: {r['similarity_score']:.3f})")
            
            return {
                "results": results,
                "query": query or "",
                "jewelry_type": jewelry_type,
                "total_results": len(results),
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error in search_jewelry: {str(e)}", exc_info=True)
            raise

    async def search_products(
        self, 
        query: str = None, 
        image_bytes: bytes = None, 
        user_id: str = None,
        category: str = None,
        limit: int = 10,
        min_score: float = 0.2,
        sort_by: str = "relevance"
    ) -> Dict[str, Any]:
        """
        Enhanced search for products using CLIP-based similarity on text and/or image.
        
        Args:
            query: Text query describing the product
            image_bytes: Image data as bytes
            user_id: User ID for filtering results
            category: Product category to filter by
            limit: Maximum number of results to return
            min_score: Minimum similarity score (0.0 to 1.0)
            sort_by: How to sort results ("relevance", "price_asc", "price_desc", "newest")
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            # Define product types and their variations
            product_types = {
                # Jewelry
                'earring': {
                    'keywords': ['earring', 'earrings', 'stud', 'studs', 'hoop', 'hoops', 'dangle'],
                    'category': 'jewelry'
                },
                'ring': {
                    'keywords': ['ring', 'rings', 'band', 'bands', 'wedding ring', 'engagement ring'],
                    'category': 'jewelry'
                },
                'necklace': {
                    'keywords': ['necklace', 'necklaces', 'pendant', 'pendants', 'chain', 'chains', 'choker'],
                    'category': 'jewelry'
                },
                'bracelet': {
                    'keywords': ['bracelet', 'bracelets', 'bangle', 'bangles', 'cuff', 'cuffs'],
                    'category': 'jewelry'
                },
                'watch': {
                    'keywords': ['watch', 'watches', 'timepiece', 'wristwatch'],
                    'category': 'jewelry'
                },
                # Electronics
                'smartphone': {
                    'keywords': ['smartphone', 'phone', 'mobile', 'iphone', 'android', 'cellphone'],
                    'category': 'electronics'
                },
                'laptop': {
                    'keywords': ['laptop', 'notebook', 'macbook', 'ultrabook', 'chromebook'],
                    'category': 'electronics'
                },
                'headphones': {
                    'keywords': ['headphones', 'earbuds', 'earphones', 'airpods', 'headset', 'earpods'],
                    'category': 'electronics'
                },
                'tablet': {
                    'keywords': ['tablet', 'ipad', 'android tablet', 'e-reader', 'kindle'],
                    'category': 'electronics'
                },
                'camera': {
                    'keywords': ['camera', 'dslr', 'mirrorless', 'point and shoot', 'action camera'],
                    'category': 'electronics'
                },
                'tv': {
                    'keywords': ['tv', 'television', 'smart tv', '4k tv', 'led tv', 'oled tv'],
                    'category': 'electronics'
                },
                # Add more categories and product types as needed
            }
            
            # Detect product type from query
            product_type = None
            detected_category = category
            query_lower = query.lower() if query else ""
            
            # Check for product type in query with improved keyword matching
            for p_type, p_data in product_types.items():
                if any(keyword in query_lower for keyword in p_data['keywords']):
                    product_type = p_type
                    if not detected_category:
                        detected_category = p_data['category']
                    break
            
            # Enhance query with product type if found
            enhanced_query = query
            if product_type and not any(word in query_lower for word in [product_type, product_type + 's']):
                enhanced_query = f"{query} {product_type}"
            
            # If this is a jewelry search, use the specialized function
            if detected_category and "jewel" in detected_category.lower() and product_type in ['earring', 'ring', 'necklace', 'bracelet', 'watch']:
                return await self.search_jewelry(
                    query=enhanced_query,
                    image_bytes=image_bytes,
                    user_id=user_id,
                    jewelry_type=product_type,
                    limit=limit,
                    min_score=min_score
                )
            
            logger.info(f"Starting product search - Query: '{enhanced_query}', Category: {detected_category}, Product Type: {product_type}")
            
            # Normalize user ID format
            normalized_user_id = self._normalize_user_id(user_id) if user_id else None
            
            # Generate embeddings based on enhanced query
            query_embedding = None
            
            if enhanced_query and image_bytes:
                # Both text and image provided - combine embeddings
                text_embedding = clip_manager.get_text_embedding(enhanced_query)
                image_embedding = clip_manager.get_image_embedding(image_bytes)
                query_embedding = [0.5 * t + 0.5 * i for t, i in zip(text_embedding, image_embedding)]
                logger.info("Combined text and image embeddings (50/50)")
            elif enhanced_query:
                query_embedding = clip_manager.get_text_embedding(enhanced_query)
                logger.info("Generated text embedding")
            elif image_bytes:
                query_embedding = clip_manager.get_image_embedding(image_bytes)
                logger.info("Generated image embedding")
            
            if query_embedding is None:
                raise ValueError("Either query text or image must be provided")
            
            # Build filter conditions
            filter_conditions = {}
            if detected_category:
                filter_conditions["category"] = detected_category.lower()
            
            # Add user filter if specified
            if normalized_user_id:
                filter_conditions["user_id"] = normalized_user_id
            
            # If we have a specific product type, add it to the filter
            if product_type:
                # For jewelry, use jewelry_type, for others use product_type
                if detected_category and "jewel" in detected_category.lower():
                    filter_conditions["jewelry_type"] = product_type
                else:
                    filter_conditions["product_type"] = product_type
            
            logger.info(f"Searching with filter: {filter_conditions}")
            
            # Get category filter if specified
            category_filter = filter_conditions.get("category")
            
            # Map detected categories to Qdrant format (case-sensitive)
            if category_filter == "clothing":
                category_filter = "Clothes"
            elif category_filter == "jewelry":
                category_filter = "Jewellery"
            
            # Search Qdrant with the embedding using search_similar_products
            search_results = qdrant_manager.search_similar_products(
                query_embedding=query_embedding,
                user_id=normalized_user_id,
                category_filter=category_filter,
                jewelry_type=product_type if category and "jewel" in category.lower() else None,  # Pass jewelry type to the search
                limit=limit * 2,  # Get more results for better filtering
                min_score=min_score
            )
            
            if not search_results:
                return {
                    "results": [],
                    "query": query or "",
                    "category": category,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            # Get product details from MongoDB for the search results
            product_ids = [ObjectId(item.get("product_id")) for item in search_results if item.get("product_id")]
            
            if not product_ids:
                return {
                    "results": [],
                    "query": query or "",
                    "category": category,
                    "total_results": 0,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
            # Fetch all products in a single query for better performance
            products_map = {
                str(product["_id"]): product 
                for product in self.db.products.find({"_id": {"$in": product_ids}})
            }
            
            # Process and rank results
            results = []
            for item in search_results:
                try:
                    product_id = str(item.get("product_id"))
                    if not product_id or product_id == 'None':
                        continue
                        
                    product = products_map.get(product_id)
                    if not product:
                        logger.warning(f"Product not found in MongoDB: {product_id}")
                        continue
                    
                    # Log product details for debugging
                    logger.debug(f"Processing product: {product.get('name')} (ID: {product_id})")
                    
                    # Calculate relevance score
                    relevance_score = self._calculate_relevance_score(
                        product=product,
                        query=query or "",
                        category=category or "",
                        similarity_score=item.get("score", 0)
                    )
                    
                    # Add to results
                    results.append({
                        "id": product_id,
                        "name": product.get("name", ""),
                        "description": product.get("description", ""),
                        "price": float(product.get("price", 0)),
                        "category": product.get("category", ""),
                        "image_url": product.get("image_url", ""),
                        "similarity_score": float(item.get("score", 0)),
                        "relevance_score": relevance_score
                    })
                except Exception as e:
                    logger.error(f"Error processing search result: {str(e)}", exc_info=True)
                    continue
            
            # Process the results after collecting them
            logger.info(f"After category filtering: {len(results)} products")
            
            # Apply intelligent filtering - only show products with significant relevance
            if results:
                # Sort results by relevance score
                results.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)
                
                # If we have more than one result, analyze score gaps
                if len(results) > 1:
                    # Calculate score gaps between consecutive products
                    score_gaps = []
                    for i in range(1, min(len(results), 5)):  # Look at top 5 gaps
                        gap = results[i-1].get('relevance_score', 0) - results[i].get('relevance_score', 0)
                        score_gaps.append(gap)
                    
                    logger.info(f"Score gaps: {score_gaps}")
                    
                    # Find the largest gap in top results
                    if score_gaps and max(score_gaps) > 10:  # If there's a significant gap (>10 points)
                        gap_index = score_gaps.index(max(score_gaps))
                        results = results[:gap_index + 1]  # Cut off at the gap
                        logger.info(f"Filtered results to {len(results)} products due to significant score gap of {max(score_gaps):.1f}")
                    else:
                        # If no significant gaps, only show products above 70% relevance
                        high_relevance_products = [p for p in results if p.get('relevance_score', 0) >= 70]
                        logger.info(f"High relevance products (>=70%): {len(high_relevance_products)}")
                        
                        if high_relevance_products:
                            results = high_relevance_products
                            logger.info(f"Filtered to {len(results)} high-relevance products (>=70%)")
                        else:
                            # If no high relevance products, show top 3 maximum
                            results = results[:3]
                            logger.info("Limited to top 3 products due to low overall relevance")
                
                # Log final results
                logger.info(f"After intelligent filtering: {len(results)} products")
                logger.info(f"Search completed. Found {len(results)} results")
                
                if results:
                    logger.debug(f"Top result: {results[0].get('name', 'N/A')} "
                                f"(Relevance: {results[0].get('relevance_score', 0):.1f}, "
                                f"Similarity: {results[0].get('similarity_score', 0):.2f})")
                
                # Calculate search statistics
                avg_relevance = sum(p.get('relevance_score', 0) for p in results) / len(results) if results else 0
                avg_similarity = sum(p.get('similarity_score', 0) for p in results) / len(results) if results else 0
                
                # Prepare final response
                response = {
                    "status": "success",
                    "count": len(results),
                    "query": query or "",
                    "category": category,
                    "sort_by": sort_by,
                    "results": results,
                    "metadata": {
                        "avg_relevance": round(avg_relevance, 2),
                        "avg_similarity": round(avg_similarity, 4),
                        "has_query": bool(query),
                        "has_image": bool(image_bytes),
                        "filtered_by_category": bool(category),
                        "user_id": user_id,
                        "normalized_user_id": normalized_user_id,
                        "timestamp": datetime.utcnow().isoformat(),
                        "search_stats": {
                            "total_found": len(results),
                            "average_relevance_score": round(avg_relevance, 2),
                            "average_similarity_score": round(avg_similarity, 3),
                            "min_relevance_score": min([p.get('relevance_score', 0) for p in results], default=0) if results else 0,
                            "max_relevance_score": max([p.get('relevance_score', 0) for p in results], default=0) if results else 0
                        }
                    }
                }
                
                return response
            else:
                # No results found
                return {
                    "status": "success",
                    "count": 0,
                    "query": query or "",
                    "category": category,
                    "sort_by": sort_by,
                    "results": [],
                    "metadata": {
                        "avg_relevance": 0,
                        "avg_similarity": 0,
                        "has_query": bool(query),
                        "has_image": bool(image_bytes),
                        "filtered_by_category": bool(category),
                        "user_id": user_id,
                        "normalized_user_id": normalized_user_id,
                        "timestamp": datetime.utcnow().isoformat(),
                        "search_stats": {
                            "total_found": 0,
                            "average_relevance_score": 0,
                            "average_similarity_score": 0,
                            "min_relevance_score": 0,
                            "max_relevance_score": 0
                        }
                    }
                }
                
        except Exception as e:
            error_msg = f"Error in search_products: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "error",
                "message": "An error occurred while processing your search",
                "error": error_msg,
                "results": []
            }

    async def search_jewelry_by_image_and_category(
        self,
        query_text: str = None,
        query_image: str = None,
        category: str = None,
        limit: int = 10,
        min_score: float = 0.1,  # Lowered from 0.3 to get more results
        user_id: str = None
    ) -> Dict[str, Any]:
        """
        Search for jewelry using CLIP-based similarity on both image and category.
        
        Args:
            query_text: Text query describing the jewelry
            query_image: Base64 encoded image data
            category: Filter by jewelry category (e.g., 'earrings', 'rings')
            limit: Maximum number of results to return
            min_score: Minimum similarity score (0.0 to 1.0)
            
        Returns:
            Dictionary with search results
        """
        logger.info(f"Starting image search - Category: {category}, Min Score: {min_score}, Has Text: {query_text is not None}, Has Image: {query_image is not None}")
        try:
            # Initialize variables
            text_embedding = None
            image_embedding = None
            
            # Check if we need to extract category from query text
            query_lower = (query_text or "").lower()
            jewelry_categories = ["earrings", "bracelets", "necklaces", "rings", "bangles", "watches"]
            
            # If no explicit category is provided, try to extract from query text
            if not category:
                for cat in jewelry_categories:
                    if cat in query_lower:
                        category = cat  # Set the category to the matched one
                        logger.info(f"Extracted category from query: {category}")
                        break
            
            # Generate text embedding if query_text is provided
            if query_text:
                text_embedding = clip_manager.get_text_embedding(query_text)
            
            # Generate image embedding if query_image is provided
            if query_image:
                image_embedding = clip_manager.get_image_embedding(query_image)
            
            # Determine which embedding to use for search
            if text_embedding is not None and image_embedding is not None:
                # Weighted combination (70% text, 30% image for jewelry)
                search_embedding = [
                    0.7 * t + 0.3 * i
                    for t, i in zip(text_embedding, image_embedding)
                ]
                query_type = "image_and_text"
            elif text_embedding is not None:
                search_embedding = text_embedding
                query_type = "text"
            elif image_embedding is not None:
                search_embedding = image_embedding
                query_type = "image"
            else:
                raise ValueError("Either query_text or query_image must be provided")
            
            # Search in Qdrant with category filter and strict user scoping when provided
            logger.info(f"Searching with embedding size: {len(search_embedding)}")
            search_results = qdrant_manager.search_similar_products(
                query_embedding=search_embedding,
                user_id=user_id,
                category_filter=category,
                limit=limit,
                min_score=min_score
            )
            logger.info(f"Raw search results count: {len(search_results)}")
            
            # Log top 3 results for debugging
            for i, result in enumerate(search_results[:3]):
                # Support both dict results from search_similar_products and prior format
                rid = result.get('id') or result.get('product_id')
                rscore = result.get('score', 0)
                rcat = result.get('category', 'N/A')
                logger.info(f"Result {i+1} - ID: {rid}, Score: {rscore:.4f}, Category: {rcat}")
            
            # Get product details from MongoDB
            # Use a dictionary to store unique products by their ID
            unique_product_ids = {}
            for hit in search_results:
                product_id = hit.get("product_id") or hit.get("id")
                # Keep the highest score for each product
                if product_id not in unique_product_ids or hit.get("score", 0) > unique_product_ids[product_id].get("score", 0):
                    unique_product_ids[product_id] = {"id": product_id, "score": hit.get("score", 0)}
            
            if not unique_product_ids:
                return {
                    "status": "success",
                    "message": "No jewelry found matching your criteria",
                    "results": [],
                    "count": 0,
                    "query_type": "image_and_text" if text_embedding and image_embedding else ("text" if text_embedding else "image"),
                    "category_filter": category
                }
            
            # Filter out invalid ObjectIds and get unique product IDs
            valid_ids = []
            for pid in unique_product_ids:
                try:
                    valid_ids.append(ObjectId(pid))
                except:
                    logger.warning(f"Invalid ObjectId: {pid}")
                    continue
            
            if not valid_ids:
                return {
                    "status": "success",
                    "message": "No valid jewelry items found",
                    "results": [],
                    "count": 0,
                    "query_type": "image_and_text" if text_embedding and image_embedding else ("text" if text_embedding else "image"),
                    "category_filter": category
                }
            
            # Get products from MongoDB
            products_cursor = self.db.products.find(
                {"_id": {"$in": valid_ids}}
            )
            
            # Create a list of products with their scores
            products = []
            for product in products_cursor:  # Use regular for loop since it's not async
                product_id = str(product["_id"])
                if product_id in unique_product_ids:
                    product["_id"] = product_id
                    product["similarity_score"] = unique_product_ids[product_id]["score"]
                    products.append(product)
            
            # Sort by score in descending order
            products.sort(key=lambda x: x.get("similarity_score", 0), reverse=True)
            
            # Limit to the requested number of results
            products = products[:limit]
            
            return {
                "status": "success",
                "message": f"Found {len(products)} jewelry items",
                "results": products,
                "count": len(products),
                "query_type": "image_and_text" if text_embedding and image_embedding else ("text" if text_embedding else "image"),
                "category_filter": category
            }
        
        except Exception as e:
            logger.error(f"Error searching jewelry by image and category: {str(e)}", exc_info=True)
            raise


# ✅ Global instance
product_handler = ProductHandler()
