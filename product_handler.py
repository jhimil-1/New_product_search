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
        """Enhanced category detection with comprehensive keyword matching"""
        if not query:
            return None
            
        query_lower = query.lower().strip()
        
        # Score each category based on keyword matches
        category_scores = {}
        
        for category, keywords in self.category_keywords.items():
            score = 0
            
            # Check primary keywords (higher weight)
            for keyword in keywords["primary"]:
                if keyword in query_lower:
                    score += 3
                    
            # Check type keywords (medium weight)
            if "types" in keywords:
                for keyword in keywords["types"]:
                    if keyword in query_lower:
                        score += 2
                        
            # Check other keywords (lower weight)
            for key in ["attributes", "brands", "materials"]:
                if key in keywords:
                    for keyword in keywords[key]:
                        if keyword in query_lower:
                            score += 1
            
            if score > 0:
                category_scores[category] = score
        
        # Return the category with highest score, or None if no matches
        if category_scores:
            best_category = max(category_scores, key=category_scores.get)
            if category_scores[best_category] >= 2:  # Minimum threshold
                logger.info(f"Auto-detected {best_category} category from query: '{query}' (score: {category_scores[best_category]})")
                return best_category
        
        return None

    async def search_products(
        self, 
        query: str = None, 
        image_bytes: bytes = None, 
        user_id: str = None,
        category: str = None,
        limit: int = 10,
        min_score: float = 0.1,
        sort_by: str = "relevance"
    ) -> Dict[str, Any]:
        """
        Enhanced search for products using CLIP-based similarity on text and/or image.
        
        Args:
            query: Text query describing the product
            image_bytes: Image data as bytes
            user_id: User ID for filtering results (supports UUID, ObjectId, or username)
            category: Product category to filter by (auto-detected if not provided)
            limit: Maximum number of results to return
            min_score: Minimum similarity score (0.0 to 1.0)
            sort_by: How to sort results ("relevance", "price_asc", "price_desc", "newest")
            
        Returns:
            Dictionary with search results and metadata
        """
        try:
            logger.info(f"Starting enhanced product search - Query: '{query}', Category: {category}, User: {user_id}, Limit: {limit}")
            
            # Normalize user ID format
            normalized_user_id = self._normalize_user_id(user_id)
            
            # Auto-detect category from query if not explicitly provided
            if not category and query:
                category = self._detect_category_from_query(query)
            
            # Generate embeddings based on input
            query_embedding = None
            
            if query and image_bytes:
                # Both text and image provided - combine embeddings
                text_embedding = clip_manager.get_text_embedding(query)
                image_embedding = clip_manager.get_image_embedding(image_bytes)
                
                # Weighted combination (60% text, 40% image)
                query_embedding = [
                    0.6 * t + 0.4 * i 
                    for t, i in zip(text_embedding, image_embedding)
                ]
                logger.info("Combined text and image embeddings")
                
            elif query:
                # Text only
                query_embedding = clip_manager.get_text_embedding(query)
                logger.info("Generated text embedding")
                
            elif image_bytes:
                # Image only
                query_embedding = clip_manager.get_image_embedding(image_bytes)
                logger.info("Generated image embedding")
                
            else:
                return {
                    "status": "error", 
                    "message": "Either query text or image must be provided",
                    "results": []
                }
            
            if not query_embedding:
                return {
                    "status": "error",
                    "message": "Failed to generate query embedding",
                    "results": []
                }
            
            logger.info(f"Generated embedding with {len(query_embedding)} dimensions")
            
            # Determine user ID for filtering
            qdrant_user_id = None
            if normalized_user_id:
                try:
                    user = None
                    
                    # Try different user lookup strategies
                    if self._is_valid_objectid(normalized_user_id):
                        # Try ObjectId lookup first
                        user = self.db.users.find_one({"_id": ObjectId(normalized_user_id)})
                        logger.debug(f"Tried ObjectId lookup for {normalized_user_id}: {'found' if user else 'not found'}")
                    
                    if not user and '-' in normalized_user_id:
                        # Try UUID lookup
                        user = self.db.users.find_one({"user_id": normalized_user_id})
                        logger.debug(f"Tried UUID lookup for {normalized_user_id}: {'found' if user else 'not found'}")
                    
                    if not user:
                        # Fallback to username lookup
                        user = self.db.users.find_one({"username": normalized_user_id})
                        logger.debug(f"Tried username lookup for {normalized_user_id}: {'found' if user else 'not found'}")
                    
                    if user:
                        qdrant_user_id = user.get("user_id", str(user.get("_id", normalized_user_id)))
                        logger.info(f"Successfully found user with qdrant_user_id: {qdrant_user_id}")
                    else:
                        logger.warning(f"User not found with any ID format: {normalized_user_id}")
                        
                except Exception as e:
                    logger.error(f"Error finding user with ID {normalized_user_id}: {e}")
                    # Last resort: try direct lookup with the original ID
                    try:
                        user = self.db.users.find_one({"user_id": normalized_user_id})
                        if user:
                            qdrant_user_id = user.get("user_id", str(user.get("_id", normalized_user_id)))
                            logger.info(f"Fallback user lookup successful with qdrant_user_id: {qdrant_user_id}")
                    except Exception as fallback_error:
                        logger.error(f"Fallback user lookup also failed: {fallback_error}")
            
            # Search in Qdrant with user filtering and category filtering
            logger.info(f"Searching Qdrant with user: {qdrant_user_id}, category: {category}, limit: {limit}")
            
            try:
                search_results = qdrant_manager.search_similar_products(
                    query_embedding=query_embedding,
                    user_id=qdrant_user_id,
                    category_filter=category,
                    limit=limit * 2,  # Get more results to filter further
                    min_score=min_score
                )
                
                logger.info(f"Qdrant search returned {len(search_results)} results")
                if search_results:
                    logger.info(f"First result score: {search_results[0].get('score', 0):.2f}")
                    logger.info(f"First result type: {type(search_results[0])}")
                    logger.info(f"First result keys: {list(search_results[0].keys()) if isinstance(search_results[0], dict) else 'not a dict'}")
                
                if not search_results and category:
                    # Try without category filter if no results
                    logger.info("No results with category filter, trying without category")
                    search_results = qdrant_manager.search_similar_products(
                        query_embedding=query_embedding,
                        user_id=qdrant_user_id,
                        limit=limit,
                        min_score=min_score * 0.8  # Slightly lower threshold
                    )
                    
                    if search_results:
                        logger.info(f"Found {len(search_results)} results without category filter")
            
            except Exception as e:
                logger.error(f"Error in Qdrant search: {str(e)}", exc_info=True)
                return {
                    "status": "error",
                    "message": "Error performing search",
                    "results": []
                }
            
            # Retrieve product documents from MongoDB
            if not search_results:
                return {
                    "status": "success",
                    "message": "No matching products found",
                    "results": []
                }
                
            try:
                # Extract product IDs from search results
                product_ids = []
                for hit in search_results:
                    if isinstance(hit, dict) and "product_id" in hit:
                        product_ids.append(hit["product_id"])
                        logger.info(f"Extracted product_id: {hit['product_id']}")
                    else:
                        logger.warning(f"Unexpected search result format: {hit}")
                
                logger.info(f"Total product IDs extracted: {len(product_ids)}")
                logger.info(f"First few product IDs: {product_ids[:3]}")
                
                if not product_ids:
                    return {
                        "status": "success",
                        "message": "No valid product IDs found in search results",
                        "results": []
                    }
                
                logger.info(f"Retrieving {len(product_ids)} products from MongoDB")
                
                # Convert string IDs to ObjectIds for MongoDB query
                object_ids = []
                invalid_ids = []
                for pid in product_ids:
                    try:
                        object_ids.append(ObjectId(pid))
                        logger.info(f"Converted {pid} to ObjectId")
                    except Exception as e:
                        invalid_ids.append(pid)
                        logger.warning(f"Invalid product ID format: {pid} - {str(e)}")
                
                logger.info(f"Valid ObjectIds: {len(object_ids)}, Invalid IDs: {len(invalid_ids)}")
                
                if not object_ids and invalid_ids:
                    logger.error(f"All product IDs were invalid: {invalid_ids}")
                    return {
                        "status": "error",
                        "message": "Invalid product references found",
                        "results": []
                    }
                
                # Get products from MongoDB
                try:
                    logger.info(f"Querying MongoDB with ObjectIds: {object_ids}")
                    products_cursor = self.db.products.find(
                        {"_id": {"$in": object_ids}}
                    ).hint("_id_")  # Use _id index for better performance
                    
                    # Create a dictionary to store products by ID for efficient lookup
                    products_by_id = {}
                    product_count = 0
                    for product in products_cursor:
                        try:
                            product_id = str(product.get("_id"))
                            if product_id:
                                products_by_id[product_id] = product
                                product_count += 1
                                logger.info(f"Found product in MongoDB: {product_id}")
                            else:
                                logger.warning("Product missing _id field")
                        except Exception as e:
                            logger.error(f"Error processing product: {str(e)}")
                    
                    logger.info(f"Total products found in MongoDB: {product_count}")
                    logger.info(f"Products by ID keys: {list(products_by_id.keys())}")
                    
                    # Process search results and prepare response
                    products_dict = {}
                    seen_products = set()  # Track seen product IDs to avoid duplicates
                    
                    for hit in search_results:
                        if not isinstance(hit, dict) or "product_id" not in hit:
                            logger.warning(f"Skipping invalid hit format: {hit}")
                            continue
                            
                        product_id = hit["product_id"]
                        logger.info(f"Processing product_id: {product_id}")
                        
                        # Skip if we've already processed this product
                        if product_id in seen_products:
                            logger.info(f"Skipping duplicate product: {product_id}")
                            continue
                            
                        product = products_by_id.get(product_id)
                        
                        if not product:
                            logger.warning(f"Product not found in MongoDB: {product_id}")
                            continue
                        
                        # Mark this product as seen
                        seen_products.add(product_id)
                        
                        # Calculate a normalized score (0-100)
                        raw_score = hit.get("score", 0.0)
                        try:
                            raw_score = float(raw_score) if raw_score is not None else 0.0
                        except (ValueError, TypeError):
                            raw_score = 0.0
                        normalized_score = min(max(0, int(raw_score * 100)), 100)
                        
                        # Get additional metadata from Qdrant payload if available
                        payload = hit.get("payload", {})
                        
                        # Validate product data before processing
                        logger.info(f"Validating product: {product_id}")
                        if not self._validate_product_data(product):
                            logger.warning(f"Skipping invalid product data for ID: {product_id}")
                            continue
                        
                        # Calculate enhanced relevance score
                        relevance_score = self._calculate_relevance_score(
                            product, query, category, raw_score
                        )
                        logger.info(f"Product {product_id} relevance score: {relevance_score}")
                        
                        # Create result dictionary
                        result = {
                            "id": str(product.get("_id", "")),
                            "name": payload.get("name") or product.get("name", "Unnamed Product"),
                            "description": payload.get("description") if payload.get("description") is not None else product.get("description", ""),
                            "price": float(payload.get("price") if payload.get("price") is not None else product.get("price", 0.0)),
                            "category": payload.get("category") if payload.get("category") is not None else product.get("category", "other"),
                            "image_url": payload.get("image_url") if payload.get("image_url") is not None else product.get("image_url", ""),
                            "similarity_score": raw_score,
                            "match_percentage": normalized_score,
                            "relevance_score": relevance_score,
                            "in_stock": product.get("in_stock", True),
                            "created_at": product.get("created_at", ""),
                            "created_by": product.get("created_by", ""),
                            "metadata": {
                                "source": "vector_search",
                                "has_image": bool(payload.get("image_url") or product.get("image_url")),
                                "category_matched": bool(category and category.lower() in (payload.get("category", "") or "").lower()),
                                "validation_passed": True
                            }
                        }
                        
                        # Add any additional fields from the payload
                        for key, value in payload.items():
                            if key not in result and key not in ["text_embedding", "image_embedding"]:
                                result[key] = value
                        
                        products_dict[product_id] = result
                    
                    logger.info(f"Products processed into dict: {len(products_dict)} items")
                    logger.info(f"Products dict keys: {list(products_dict.keys())}")
                    
                    if not products_dict:
                        logger.warning("No valid products found after processing search results")
                        return {
                            "status": "success",
                            "message": "No matching products found",
                            "results": []
                        }
                    
                    # Convert to list and sort by enhanced relevance score
                    products = list(products_dict.values())
                    
                    # Log relevance scores before filtering
                    logger.info(f"Products before filtering - count: {len(products)}")
                    for i, p in enumerate(products[:5]):  # Log first 5 products
                        logger.info(f"Product {i+1}: {p.get('name', 'Unknown')} - relevance_score: {p.get('relevance_score', 0)}")
                    
                    # Sort based on the specified sort criteria
                    if sort_by == "relevance":
                        products.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
                    elif sort_by == "price_asc":
                        products.sort(key=lambda x: x.get("price", 0))
                    elif sort_by == "price_desc":
                        products.sort(key=lambda x: x.get("price", 0), reverse=True)
                    elif sort_by == "newest":
                        products.sort(key=lambda x: x.get("created_at", ""), reverse=True)
                    else:
                        # Default to relevance score
                        products.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
                    
                    logger.info(f"After sorting: {len(products)} products")
                    
                    # Apply additional filtering based on minimum relevance score
                    logger.info(f"Before min_score filtering: {len(products)} products, min_score: {min_score}, threshold: {min_score * 100}")
                    if min_score > 0:
                        products = [p for p in products if p.get("relevance_score", 0) >= min_score * 100]
                        logger.info(f"After min_score filtering: {len(products)} products remaining")
                    else:
                        logger.info(f"No min_score filtering applied (min_score = 0)")
                    
                    # Apply category filter if specified (additional filtering)
                    if category:
                        logger.info(f"Applying category filter: {category}")
                        logger.info(f"Products before category filter:")
                        for i, p in enumerate(products[:3]):  # Show first 3 products
                            logger.info(f"  Product {i+1}: {p.get('name')} - Category: '{p.get('category', 'No category')}'")
                        # More flexible category matching - handle common variations
                        category_lower = category.lower()
                        products = [p for p in products if 
                            category_lower in p.get("category", "").lower() or  # Original substring match
                            (category_lower == "clothing" and p.get("category", "").lower() == "clothes") or  # Handle clothing/clothes
                            (category_lower == "clothes" and p.get("category", "").lower() == "clothing") or  # Handle clothes/clothing
                            (category_lower == "jewelry" and p.get("category", "").lower() == "jewellery") or  # Handle jewelry/jewellery
                            (category_lower == "jewellery" and p.get("category", "").lower() == "jewelry") or  # Handle jewellery/jewelry
                            p.get("category", "").lower().replace(" ", "") == category_lower.replace(" ", "")  # Exact match ignoring spaces
                        ]
                        logger.info(f"After category filtering: {len(products)} products")
                    
                    # Apply intelligent filtering - only show products with significant relevance
                    logger.info(f"Before intelligent filtering: {len(products)} products")
                    if len(products) > 1:
                        # Calculate score gaps between consecutive products
                        score_gaps = []
                        for i in range(1, min(len(products), 5)):  # Look at top 5 gaps
                            gap = products[i-1].get('relevance_score', 0) - products[i].get('relevance_score', 0)
                            score_gaps.append(gap)
                        
                        logger.info(f"Score gaps: {score_gaps}")
                        
                        # Find the largest gap in top results
                        if score_gaps and max(score_gaps) > 10:  # If there's a significant gap (>10 points)
                            gap_index = score_gaps.index(max(score_gaps))
                            products = products[:gap_index + 1]  # Cut off at the gap
                            logger.info(f"Filtered results to {len(products)} products due to significant score gap of {max(score_gaps):.1f}")
                        else:
                            # If no significant gaps, only show products above 70% relevance
                            high_relevance_products = [p for p in products if p.get('relevance_score', 0) >= 70]
                            logger.info(f"High relevance products (>=70%): {len(high_relevance_products)}")
                            if high_relevance_products:
                                products = high_relevance_products
                                logger.info(f"Filtered to {len(products)} high-relevance products (>=70%)")
                            else:
                                # If no high relevance products, show top 3 maximum
                                products = products[:3]
                                logger.info(f"Limited to top 3 products due to low overall relevance")
                    else:
                        # For single or no results, keep as is
                        logger.info(f"Single or no results, keeping as is: {len(products)} products")
                        pass
                    
                    logger.info(f"After intelligent filtering: {len(products)} products")
                    logger.info(f"Search completed. Found {len(products)} results")
                    if products:
                        logger.debug(f"Top result: {products[0]['name']} (Relevance: {products[0]['relevance_score']:.1f}, Similarity: {products[0]['similarity_score']:.2f})")
                    
                    # Calculate search statistics
                    avg_relevance = sum(p.get('relevance_score', 0) for p in products) / len(products) if products else 0
                    avg_similarity = sum(p.get('similarity_score', 0) for p in products) / len(products) if products else 0
                    
                    return {
                        "status": "success",
                        "count": len(products),
                        "query": query,
                        "category": category,
                        "sort_by": sort_by,
                        "results": products,
                        "metadata": {
                            "has_query": bool(query),
                            "has_image": bool(image_bytes),
                            "filtered_by_category": bool(category),
                            "user_id": user_id,
                            "normalized_user_id": normalized_user_id,
                            "qdrant_user_id": qdrant_user_id,
                            "timestamp": datetime.utcnow().isoformat(),
                            "search_stats": {
                                "total_found": len(products),
                                "average_relevance_score": round(avg_relevance, 2),
                                "average_similarity_score": round(avg_similarity, 3),
                                "min_relevance_score": min([p.get('relevance_score', 0) for p in products], default=0) if products else 0,
                                "max_relevance_score": max([p.get('relevance_score', 0) for p in products], default=0) if products else 0
                            },
                            "validation": {
                                "user_lookup_success": bool(qdrant_user_id),
                                "products_validated": len([p for p in products if p.get('metadata', {}).get('validation_passed')]),
                                "invalid_products_skipped": len(invalid_ids) if 'invalid_ids' in locals() else 0
                            }
                        }
                    }
                    
                except Exception as e:
                    logger.error(f"Error processing search results: {str(e)}", exc_info=True)
                    return {
                        "status": "error",
                        "message": "Error processing search results",
                        "results": []
                    }
                        
            except Exception as e:
                logger.error(f"Error in search_products: {str(e)}", exc_info=True)
                return {
                    "status": "error",
                    "message": "An error occurred while processing your search",
                    "results": []
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
        min_score: float = 0.1  # Lowered from 0.3 to get more results
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
            
            # Search in Qdrant with category filter
            logger.info(f"Searching with embedding size: {len(search_embedding)}")
            search_results = qdrant_manager.search_similar(
                query_embedding=search_embedding,
                limit=limit,
                category_filter=category,
                min_score=min_score
            )
            logger.info(f"Raw search results count: {len(search_results)}")
            
            # Log top 3 results for debugging
            for i, result in enumerate(search_results[:3]):
                logger.info(f"Result {i+1} - ID: {result.get('id')}, Score: {result.get('score', 0):.4f}, Category: {result.get('category', 'N/A')}")
            
            # Get product details from MongoDB
            # Use a dictionary to store unique products by their ID
            unique_product_ids = {}
            for hit in search_results:
                product_id = hit["id"]
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
