"""
Chatbot logic for handling text and image queries
"""
from typing import List, Dict, Any, Optional
from datetime import datetime
from PIL import Image
import io
import logging

from database import MongoDB
from qdrant_utils import qdrant_manager
from gemini_utils import gemini_manager
from clip_utils import clip_manager
from models import ChatResponse, ChatHistoryItem, ChatHistory
from product_handler import ProductHandler
from enhanced_product_handler import EnhancedProductHandler
import re

logger = logging.getLogger(__name__)


class ChatbotManager:
    """Manager for chatbot operations"""
    
    MAX_HISTORY_LENGTH = 10
    
    def __init__(self):
        """Initialize chatbot manager"""
        self.chat_collection = MongoDB.get_collection("chat_history")
        self.sessions_collection = MongoDB.get_collection("sessions")
        self.products_collection = MongoDB.get_collection("products")
        self.product_handler = ProductHandler()
        self.enhanced_handler = EnhancedProductHandler(self.product_handler)
    
    def _get_chat_history(self, session_id: str) -> List[Dict[str, str]]:
        """
        Retrieve chat history for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of chat messages
        """
        messages = list(
            self.chat_collection.find(
                {"session_id": session_id}
            ).sort("timestamp", -1).limit(self.MAX_HISTORY_LENGTH)
        )
        
        # Reverse to get chronological order
        messages.reverse()
        
        return [
            {
                "role": msg["role"],
                "content": msg["content"]
            }
            for msg in messages
        ]
    
    def _save_chat_message(
        self, 
        session_id: str, 
        role: str, 
        content: str, 
        products: Optional[List[Dict]] = None
    ):
        """
        Save a chat message to history
        
        Args:
            session_id: Session identifier
            role: Message role (user/assistant)
            content: Message content
            products: Optional product list
        """
        message_doc = {
            "session_id": session_id,
            "role": role,
            "content": content,
            "products": products or [],
            "timestamp": datetime.utcnow()
        }
        
        self.chat_collection.insert_one(message_doc)
        
        # Update session last activity
        self.sessions_collection.update_one(
            {"session_id": session_id},
            {"$set": {"last_activity": datetime.utcnow()}}
        )
        
        # Maintain max history length
        message_count = self.chat_collection.count_documents({"session_id": session_id})
        if message_count > self.MAX_HISTORY_LENGTH:
            # Delete oldest messages
            oldest_messages = list(
                self.chat_collection.find(
                    {"session_id": session_id}
                ).sort("timestamp", 1).limit(message_count - self.MAX_HISTORY_LENGTH)
            )
            
            message_ids = [msg["_id"] for msg in oldest_messages]
            self.chat_collection.delete_many({"_id": {"$in": message_ids}})
    
    def _verify_session(self, session_id: str) -> bool:
        """Verify that a session exists and is valid"""
        if not session_id:
            logger.warning("Empty session ID provided")
            return False
            
        session = self.sessions_collection.find_one({"session_id": session_id})
        if not session:
            logger.warning(f"No session found with ID: {session_id}")
            return False
            
        # Optional: Add additional session validation here
        # For example, check if session is expired
        return True
        
    def _get_user_from_session(self, session_id: str) -> Optional[str]:
        """Get user_id from session_id"""
        if not session_id:
            logger.warning("Empty session ID provided")
            return None
            
        session = self.sessions_collection.find_one({"session_id": session_id})
        if not session:
            logger.warning(f"No session found with ID: {session_id}")
            # Debug: Check all sessions
            all_sessions = list(self.sessions_collection.find({}).limit(5))
            logger.info(f"Available sessions: {[str(s.get('session_id', 'no-id')) for s in all_sessions]}")
            return None
            
        user_id = session.get("user_id")
        logger.info(f"Found user_id: {user_id} for session: {session_id}")
        return user_id
        
    def _simple_jewelry_search(self, query: str, user_id: str, limit: int = 5) -> List[Dict]:
        """
        Simple MongoDB text search for jewelry products (bypasses Qdrant)
        
        Args:
            query: Search query
            user_id: User ID for filtering
            limit: Maximum number of results
            
        Returns:
            List of products with relevance scores
        """
        try:
            logger.info(f"Simple jewelry search for: '{query}' (user: {user_id})")
            
            # Create text search query
            search_query = {
                "$and": [
                    {"$text": {"$search": query}},
                    {"created_by": user_id}
                ]
            }
            
            # Execute text search with relevance scoring
            products = list(
                self.products_collection
                .find(search_query)
                .sort([("score", {"$meta": "textScore"})])
                .limit(limit * 2)  # Get more to filter
            )
            
            if not products:
                logger.info("No text search results, trying regex search")
                # Fallback to regex search
                regex_query = {
                    "$and": [
                        {"$or": [
                            {"name": {"$regex": query, "$options": "i"}},
                            {"description": {"$regex": query, "$options": "i"}}
                        ]},
                        {"created_by": user_id}
                    ]
                }
                products = list(self.products_collection.find(regex_query).limit(limit * 2))
            
            # Filter for jewelry products and calculate relevance scores
            jewelry_products = []
            jewelry_keywords = ['jewelry', 'jewellery', 'earrings', 'necklace', 'bracelet', 'ring', 'pendant', 'chain', 'watch', 'jewel', 'gold', 'silver', 'diamond', 'pearl', 'sapphire', 'emerald', 'ruby']
            
            for product in products:
                # Check if it's jewelry
                name_lower = product.get('name', '').lower()
                desc_lower = product.get('description', '').lower()
                category_lower = product.get('category', '').lower()
                
                is_jewelry = any(keyword in name_lower or keyword in desc_lower or keyword in category_lower for keyword in jewelry_keywords)
                
                if is_jewelry:
                    # Calculate relevance score based on matches
                    score = 0.0
                    query_lower = query.lower()
                    
                    # Exact name match
                    if query_lower in name_lower:
                        score += 0.8
                    
                    # Word overlap
                    query_words = set(query_lower.split())
                    name_words = set(name_lower.split())
                    desc_words = set(desc_lower.split())
                    
                    word_matches = len(query_words.intersection(name_words)) * 0.3
                    desc_matches = len(query_words.intersection(desc_words)) * 0.2
                    score += word_matches + desc_matches
                    
                    # Category bonus
                    if any(keyword in category_lower for keyword in jewelry_keywords):
                        score += 0.1
                    
                    # Ensure minimum score
                    score = max(0.1, min(1.0, score))
                    
                    # Format product for response
                    formatted_product = {
                        'product_id': str(product.get('_id', '')),
                        'name': product.get('name', ''),
                        'description': product.get('description', ''),
                        'price': product.get('price', 0.0),
                        'category': product.get('category', ''),
                        'image_url': product.get('image_url', ''),
                        'image_path': product.get('image_path', ''),
                        'score': score,
                        'in_stock': product.get('in_stock', True),
                        'created_by': product.get('created_by', user_id)
                    }
                    
                    jewelry_products.append(formatted_product)
            
            # Sort by score and limit results
            jewelry_products.sort(key=lambda x: x['score'], reverse=True)
            final_results = jewelry_products[:limit]
            
            logger.info(f"Simple jewelry search found {len(final_results)} products")
            return final_results
            
        except Exception as e:
            logger.error(f"Simple jewelry search failed: {str(e)}")
            return []

    def _generate_jewelry_response(self, products: List[Dict], original_query: str) -> str:
        """
        Generate a natural language response for jewelry products
        
        Args:
            products: List of jewelry products
            original_query: Original user query
            
        Returns:
            Natural language response
        """
        if not products:
            return f"I couldn't find any jewelry matching '{original_query}'. Please try a different search term."
        
        # Create a personalized response based on the query and products
        query_lower = original_query.lower()
        
        # Determine response type based on query
        if 'earrings' in query_lower:
            response_intro = f"I found some beautiful earrings matching '{original_query}':"
        elif 'necklace' in query_lower:
            response_intro = f"Here are some elegant necklaces matching '{original_query}':"
        elif 'bracelet' in query_lower:
            response_intro = f"I found these lovely bracelets matching '{original_query}':"
        elif 'ring' in query_lower:
            response_intro = f"Here are some stunning rings matching '{original_query}':"
        elif 'watch' in query_lower:
            response_intro = f"I found these stylish watches matching '{original_query}':"
        elif any(word in query_lower for word in ['gold', 'silver', 'diamond', 'pearl']):
            response_intro = f"I found these beautiful jewelry pieces matching '{original_query}':"
        else:
            response_intro = f"I found these jewelry items matching '{original_query}':"
        
        # Add product highlights
        highlights = []
        for i, product in enumerate(products[:3]):  # Top 3 products
            name = product.get('name', 'Unknown')
            price = product.get('price', 0)
            category = product.get('category', 'jewelry')
            
            # Format price
            if price > 0:
                price_str = f"${price:.2f}"
            else:
                price_str = "Price not available"
            
            highlights.append(f"• {name} ({price_str})")
        
        # Combine response
        response = response_intro + "\n" + "\n".join(highlights)
        
        # Add closing based on number of results
        if len(products) > 3:
            response += f"\n\nAnd {len(products) - 3} more beautiful pieces!"
        
        return response

    def _is_jewelry_query(self, query: str, category: Optional[str] = None) -> bool:
        """
        Check if a query is jewelry-related
        
        Args:
            query: User's search query
            category: Optional category hint
            
        Returns:
            True if this is a jewelry query
        """
        query_lower = query.lower()
        jewelry_keywords = ['jewelry', 'jewellery', 'earrings', 'necklace', 'bracelet', 'ring', 'pendant', 'chain', 'watch', 'jewel', 'gold', 'silver', 'diamond', 'pearl', 'sapphire', 'emerald', 'ruby']
        
        # Check if query contains jewelry terms
        is_jewelry_query = any(keyword in query_lower for keyword in jewelry_keywords)
        
        # Check if category is jewelry
        is_jewelry_category = category and category.lower() in ['jewelry', 'jewellery', 'earrings', 'necklaces', 'bracelets', 'rings']
        
        return is_jewelry_query or is_jewelry_category

    def _enrich_products_with_mongodb(self, products):
        """
        Enrich products with full data from MongoDB
        
        Args:
            products: List of products from Qdrant search
            
        Returns:
            List of products with enriched data from MongoDB
        """
        if not products:
            return products
            
        enriched_products = []
        
        for product in products:
            try:
                # Get the MongoDB product ID from the Qdrant result
                product_id = product.get("product_id")
                if not product_id:
                    logger.warning(f"No product_id found in Qdrant result: {product}")
                    enriched_products.append(product)
                    continue
                
                # Convert to ObjectId if it's a valid ObjectId string
                from bson import ObjectId
                try:
                    if len(product_id) == 24:  # Valid ObjectId length
                        mongo_product_id = ObjectId(product_id)
                    else:
                        mongo_product_id = product_id
                except:
                    mongo_product_id = product_id
                
                # Fetch the full product document from MongoDB
                mongo_product = self.products_collection.find_one({"_id": mongo_product_id})
                
                if mongo_product:
                    # Merge Qdrant data with MongoDB data, prioritizing MongoDB for description
                    enriched_product = {
                        "product_id": product_id,
                        "name": product.get("name", mongo_product.get("name", "")),
                        "category": product.get("category", mongo_product.get("category", "")),
                        "price": product.get("price", mongo_product.get("price", 0.0)),
                        "description": mongo_product.get("description", ""),  # Use MongoDB description
                        "score": product.get("score", 0.0),
                        "image_url": product.get("image_url", mongo_product.get("image_url", "")),
                        "image_path": product.get("image_path", mongo_product.get("image_path", "")),
                        "image": product.get("image", mongo_product.get("image", "")),
                        "payload": product.get("payload", {})
                    }
                    
                    # Add any additional fields from MongoDB
                    for field in ["in_stock", "created_at", "created_by"]:
                        if field in mongo_product:
                            enriched_product[field] = mongo_product[field]
                    
                    enriched_products.append(enriched_product)
                    logger.debug(f"Enriched product {product_id} with MongoDB data")
                else:
                    logger.warning(f"No MongoDB product found for ID: {product_id}")
                    enriched_products.append(product)
                    
            except Exception as e:
                logger.error(f"Error enriching product {product.get('product_id', 'unknown')}: {str(e)}")
                enriched_products.append(product)  # Fall back to original product
        
        return enriched_products
    async def handle_text_query(
        self, 
        session_id: str, 
        query: str, 
        category: Optional[str] = None,
        limit: int = 10
    ) -> ChatResponse:
        """
        Handle text-based query with hybrid search approach
        
        Args:
            session_id: Session identifier
            query: User's search query
            category: Optional product category
            limit: Maximum number of products to return
            
        Returns:
            Chat response with products
        """
        try:
            # Verify session
            if not self._verify_session(session_id):
                raise ValueError("Invalid session ID")
            
            # Get user ID for filtering
            user_id = self._get_user_from_session(session_id)
            
            # Initialize products list to avoid NameError
            products = []
            if not user_id:
                logger.error(f"No user found for session: {session_id}")
                raise ValueError("Invalid user session")
            
            logger.info(f"Found user ID: {user_id} for session: {session_id}")
            
            # Save user message
            logger.debug(f"Saving user message: {query}")
            self._save_chat_message(session_id, "user", query)
            
            # Get query embedding
            logger.debug("Generating query embedding...")
            try:
                # Use CLIP for text embedding to match product embeddings
                query_embedding = clip_manager.get_text_embedding(query)
                if not query_embedding:
                    raise ValueError("Failed to generate query embedding")
                logger.debug("Successfully generated query embedding")
            except Exception as e:
                logger.error(f"Error generating query embedding: {str(e)}")
                raise ValueError("Failed to process your query. Please try again.")
            
            # Check if this is a "similar product" query and extract context from chat history
            search_query = query
            search_context = None
            
            # Detect similar product requests
            similar_product_keywords = ['similar product', 'similar products', 'show similar', 'recommend similar', 'like this', 'anything similar']
            if any(keyword in query.lower() for keyword in similar_product_keywords):
                logger.info("Detected similar product query, extracting context from chat history...")
                chat_history = self._get_chat_history(session_id)
                
                # Look for product mentions in recent chat history
                if chat_history:
                    # Search backwards through chat history for product context
                    for i in range(len(chat_history) - 1, -1, -1):
                        message = chat_history[i]
                        if message.get('role') == 'assistant' and message.get('products'):
                            # Found a previous response with products
                            if message['products']:
                                search_context = message['products'][0]  # Use the first product as context
                                logger.info(f"Found product context from chat history: {search_context.get('name', 'Unknown product')}")
                                # Use the product name as the search query instead of "similar products"
                                search_query = search_context.get('name', query)
                                break
                        elif message.get('role') == 'user' and message.get('content'):
                            # Look for product mentions in user messages
                            user_content = message['content'].lower()
                            # Common product-related keywords
                            product_keywords = ['phone', 'smartphone', 'jewelry', 'ring', 'necklace', 'watch', 'laptop', 'tablet']
                            for keyword in product_keywords:
                                if keyword in user_content:
                                    search_query = keyword
                                    logger.info(f"Found product keyword '{keyword}' in user history, using as search context")
                                    break
                            if search_query != query:
                                break
            
            # Search for similar products
            logger.debug(f"Searching for products with query: '{search_query}' (original: '{query}')")
            try:
                # Get search embedding
                search_embedding = clip_manager.get_text_embedding(search_query)
                
                # Enhanced category detection with comprehensive keywords
                detected_category = category
                query_lower = query.lower()
                
                # Comprehensive category detection
                category_keywords = {
                    'jewelry': ['jewelry', 'jewellery', 'earrings', 'necklace', 'bracelet', 'ring', 'pendant', 'chain', 'watch', 'jewel'],
                    'electronics': ['electronics', 'phone', 'smartphone', 'laptop', 'headphones', 'earbuds', 'computer', 'tablet', 'camera', 'speaker', 'tv', 'monitor', 'mobile'],
                    'clothing': ['shirt', 'tshirt', 't-shirt', 'pants', 'jeans', 'dress', 'skirt', 'jacket', 'coat', 'sweater', 'hoodie', 'clothing', 'clothes', 'shoes', 'boots', 'sneakers', 'apparel'],
                    'home': ['home', 'furniture', 'chair', 'table', 'sofa', 'bed', 'lamp', 'decor', 'household'],
                    'kitchen': ['kitchen', 'cooking', 'utensils', 'appliances', 'refrigerator', 'microwave', 'blender', 'cookware']
                }
                
                # Detect category if not provided
                if not detected_category:
                    for category, keywords in category_keywords.items():
                        if any(keyword in query_lower for keyword in keywords):
                            detected_category = category
                            logger.info(f"Detected category '{category}' from query: '{query}'")
                            break
                
                # Check if this is a jewelry query - use both simple MongoDB and Qdrant for best results
                if self._is_jewelry_query(query, detected_category):
                    logger.info("Detected jewelry query - using hybrid approach (MongoDB + Qdrant)")
                    
                    # First try simple MongoDB search for fast, reliable results
                    simple_products = self._simple_jewelry_search(query, user_id, limit * 2)
                    
                    # Also try Qdrant search for enhanced semantic matching
                    try:
                        qdrant_products = qdrant_manager.search_similar_products(
                            query_embedding=search_embedding,
                            user_id=user_id,
                            category_filter=detected_category,
                            limit=limit * 2,
                            min_score=0.4  # Lower threshold for jewelry to get more variety
                        )
                        
                        if qdrant_products:
                            qdrant_products = self._enrich_products_with_mongodb(qdrant_products)
                            logger.info(f"Qdrant jewelry search found {len(qdrant_products)} products")
                        else:
                            qdrant_products = []
                    except Exception as e:
                        logger.warning(f"Qdrant search failed for jewelry: {str(e)}")
                        qdrant_products = []
                    
                    # Combine results: prioritize simple search results, enhance with Qdrant if available
                    if simple_products:
                        products = simple_products
                        logger.info(f"Using simple MongoDB results ({len(products)} products)")
                        
                        # If we have Qdrant results too, merge them intelligently
                        if qdrant_products:
                            # Add unique Qdrant results that aren't in simple results
                            simple_ids = {p['product_id'] for p in simple_products}
                            additional_products = [p for p in qdrant_products if p['product_id'] not in simple_ids]
                            
                            if additional_products:
                                # Take top additional products and merge
                                additional_products = additional_products[:max(1, limit - len(simple_products))]
                                products.extend(additional_products)
                                logger.info(f"Added {len(additional_products)} unique Qdrant results")
                    
                    elif qdrant_products:
                        # No simple results, use Qdrant results
                        products = qdrant_products
                        logger.info(f"Using Qdrant results only ({len(products)} products)")
                    
                    else:
                        products = []
                    
                    if products:
                        # Sort by score and limit results
                        products.sort(key=lambda x: x.get('score', 0), reverse=True)
                        products = products[:limit]
                        
                        logger.info(f"Hybrid jewelry search final result: {len(products)} products")
                        # Generate natural language response for jewelry products
                        response_text = self._generate_jewelry_response(products, query)
                        
                        # Save assistant message
                        self._save_chat_message(session_id, "assistant", response_text, products)
                        
                        return ChatResponse(
                            response=response_text,
                            products=products,
                            session_id=session_id,
                            success=True
                        )
                    else:
                        logger.info("No jewelry products found with hybrid search, continuing with standard Qdrant")
                        products = []  # Fall through to standard Qdrant search
                
                # PRIORITY 1: Try enhanced search with category filtering first (if category detected)
                if not products and detected_category:
                    logger.info(f"Attempting category-specific enhanced search for '{detected_category}'")
                    
                    enhanced_results = await self.enhanced_handler.search_products_enhanced(
                        query=search_query,
                        user_id=user_id,
                        category=detected_category,
                        min_relevance_score=0.5,  # Higher threshold for category-specific search
                        limit=limit * 2
                    )
                    
                    if enhanced_results and enhanced_results.get('products'):
                        products = enhanced_results['products']
                        logger.info(f"Category-specific search found {len(products)} products")
                        
                        # Verify results are from the correct category
                        valid_products = []
                        for product in products:
                            if product.get('category', '').lower() == detected_category.lower():
                                # Set similarity score from semantic relevance
                                product['score'] = product.get('search_metadata', {}).get('semantic_relevance_score', 0.7)
                                valid_products.append(product)
                        
                        if valid_products:
                            logger.info(f"Found {len(valid_products)} valid products in correct category")
                            # Sort by score and limit
                            valid_products.sort(key=lambda x: x.get('score', 0), reverse=True)
                            products = valid_products[:limit]
                        else:
                            logger.info("No valid products found in correct category, falling back to CLIP search")
                            products = []
                    else:
                        logger.info("No results from category-specific enhanced search")
                        products = []
                
                # PRIORITY 2: If no category-specific results, use CLIP similarity search
                if not products:
                    logger.info("Using CLIP similarity search")
                    
                    # First try with higher score threshold for better precision
                    products = qdrant_manager.search_similar_products(
                        query_embedding=search_embedding,
                        user_id=user_id,
                        category_filter=detected_category,
                        limit=limit * 2,  # Get more results for better filtering
                        min_score=0.65  # Increased threshold for more relevant results
                    )
                    
                    # If no results, try with a medium threshold
                    if not products:
                        logger.info("No results with strict filter, trying with medium threshold")
                        products = qdrant_manager.search_similar_products(
                            query_embedding=search_embedding,
                            user_id=user_id,
                            category_filter=detected_category,
                            limit=limit * 2,
                            min_score=0.5
                        )
                    
                    # Enrich products with MongoDB data if found
                    if products:
                        products = self._enrich_products_with_mongodb(products)
                        
                        # Boost scores for products that match the query category
                        if detected_category:
                            for product in products:
                                product_category = product.get('category', '').lower()
                                if product_category == detected_category.lower():
                                    # Boost score for category match
                                    if 'score' in product:
                                        product['score'] = min(1.0, product['score'] * 1.3)  # 30% boost, capped at 1.0
                        
                        # Sort by relevance score if available
                        if all('score' in p for p in products):
                            products.sort(key=lambda x: x.get('score', 0), reverse=True)
                        
                        # Apply minimum threshold to final results
                        products = [p for p in products if p.get('score', 0) >= 0.6]
                        
                        # Limit to requested number of results
                        products = products[:limit]
                
                # If still no results, try the enhanced product handler as last resort
                if not products:
                    logger.info(f"Using enhanced product handler as fallback for query: '{search_query}'")
                    search_result = await self.enhanced_handler.search_products_enhanced(
                        query=search_query,
                        user_id=user_id,
                        category=detected_category,
                        limit=limit,
                        min_relevance_score=0.4  # Set minimum relevance score for fallback
                    )
                    
                    if search_result and search_result.get('products'):
                        products = search_result['products']
                        logger.info(f"Found {len(products)} enhanced products")
                
            except Exception as e:
                    logger.error(f"Error searching products: {str(e)}")
                    # Fallback to direct Qdrant search if product handler fails
                    try:
                        # Generate embedding for the search query (which might be different from original query)
                        search_embedding = clip_manager.get_text_embedding(search_query)
                        products = qdrant_manager.search_similar_products(
                            query_embedding=search_embedding,
                            user_id=user_id,
                            category_filter=detected_category,
                            limit=limit
                        )
                        products = self._enrich_products_with_mongodb(products)
                        logger.info(f"Fallback: Found {len(products)} products from direct Qdrant search")
                    except Exception as fallback_error:
                        logger.error(f"Fallback search also failed: {str(fallback_error)}")
                        products = []  # Continue with empty product list
            
            # Get chat history
            chat_history = self._get_chat_history(session_id)
            
            # Generate natural language response
            logger.debug("Generating response...")
            try:
                response_text = gemini_manager.generate_response(
                    query=query,
                    products=products,
                    chat_history=chat_history
                )
            except Exception as e:
                logger.error(f"Error generating response: {str(e)}")
                response_text = "I'm sorry, I encountered an error processing your request. Please try again."
            
            # Save assistant response
            self._save_chat_message(session_id, "assistant", response_text, products)
            
            response = ChatResponse(
                session_id=session_id,
                query=query,
                response=response_text,
                products=products,
                timestamp=datetime.utcnow()
            )
            
            logger.info(f"Successfully processed query for session: {session_id}")
            return response
        
        except ValueError as e:
            logger.error(f"Validation error in handle_text_query: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in handle_text_query: {str(e)}", exc_info=True)
            raise
    
    async def handle_image_query(
        self, 
        session_id: str, 
        query: str, 
        image_bytes: bytes,
        category: Optional[str] = None
    ) -> ChatResponse:
        """
        Handle image-based query
        
        Args:
            session_id: Session identifier
            query: User's text query accompanying the image
            image_bytes: Image file bytes
            category: Optional product category
            
        Returns:
            Chat response with products
        """
        try:
            # Verify session
            if not self._verify_session(session_id):
                raise ValueError("Invalid session ID")
            
            # Get user ID for filtering
            user_id = self._get_user_from_session(session_id)
            
            # Enhanced category detection for image queries
            detected_category = category
            query_lower = query.lower() if query else ""
            
            # Comprehensive category detection for image queries
            image_category_keywords = {
                'jewelry': ['jewelry', 'jewellery', 'earrings', 'necklace', 'bracelet', 'ring', 'pendant', 'chain', 'watch', 'jewel', 'gold', 'silver', 'diamond'],
                'electronics': ['electronics', 'phone', 'smartphone', 'laptop', 'headphones', 'earbuds', 'computer', 'tablet', 'camera', 'speaker', 'tv', 'monitor', 'mobile', 'tech'],
                'clothing': ['shirt', 'tshirt', 't-shirt', 'pants', 'jeans', 'dress', 'skirt', 'jacket', 'coat', 'sweater', 'hoodie', 'clothing', 'clothes', 'shoes', 'boots', 'sneakers', 'apparel', 'fashion'],
                'home': ['home', 'furniture', 'chair', 'table', 'sofa', 'bed', 'lamp', 'decor', 'household', 'interior'],
                'kitchen': ['kitchen', 'cooking', 'utensils', 'appliances', 'refrigerator', 'microwave', 'blender', 'cookware', 'food']
            }
            
            # Detect category from query if not provided
            if not detected_category and query:
                for category, keywords in image_category_keywords.items():
                    if any(keyword in query_lower for keyword in keywords):
                        detected_category = category
                        logger.info(f"Detected category '{category}' from image query: '{query}'")
                        break
            
            # Open image
            image = Image.open(io.BytesIO(image_bytes))
            
            # Save user message
            search_type = f"{detected_category or 'general'} image search" if detected_category else "image search"
            user_message = f"{query} [{search_type}]"
            self._save_chat_message(session_id, "user", user_message)
            
            # PRIORITY 1: Try enhanced image search with category filtering first
            if detected_category:
                logger.info(f"Attempting category-specific image search for '{detected_category}'")
                
                enhanced_results = await self.enhanced_handler.search_products(
                    query=query or f"{detected_category} product",
                    user_id=user_id,
                    category=detected_category,
                    min_relevance_score=0.4,
                    limit=limit * 2,
                    search_type="image",
                    image_data=image_bytes,
                    min_semantic_score=0.3
                )
                
                if enhanced_results and enhanced_results.get('products'):
                    products = enhanced_results['products']
                    logger.info(f"Category-specific image search found {len(products)} products")
                    
                    # Verify results are from the correct category
                    valid_products = []
                    for product in products:
                        if product.get('category', '').lower() == detected_category.lower():
                            product['score'] = product.get('search_metadata', {}).get('semantic_relevance_score', 0.6)
                            valid_products.append(product)
                    
                    if valid_products:
                        valid_products.sort(key=lambda x: x.get('score', 0), reverse=True)
                        products = valid_products[:limit]
                        
                        # Generate success response
                        response_text = f"I found {len(products)} {detected_category} items that match your image:"
                        
                        # Save and return response
                        self._save_chat_message(session_id, "assistant", response_text, products)
                        
                        return ChatResponse(
                            session_id=session_id,
                            query=user_message,
                            response=response_text,
                            products=products,
                            timestamp=datetime.utcnow()
                        )
            
            # PRIORITY 2: If no category-specific results, use CLIP image similarity search
            logger.info("Using CLIP image similarity search")
            
            # Get query embedding using CLIP for image and text
            text_embedding = clip_manager.get_text_embedding(query or "product")
            image_embedding = clip_manager.get_image_embedding(image)
            
            # Combine embeddings (60% text, 40% image for better accuracy)
            query_embedding = [
                0.6 * t + 0.4 * i
                for t, i in zip(text_embedding, image_embedding)
            ]
            
            # Try with category filter if detected
            products = qdrant_manager.search_similar_products(
                query_embedding=query_embedding,
                user_id=user_id,
                category_filter=detected_category,
                limit=limit * 2,
                min_score=0.4
            )
            
            # If no results, try without category filter
            if not products and detected_category:
                logger.info("No results with category filter, trying without category filter")
                products = qdrant_manager.search_similar_products(
                    query_embedding=query_embedding,
                    user_id=user_id,
                    limit=limit * 2,
                    min_score=0.3
                )
            
            # Enrich products with MongoDB data
            if products:
                products = self._enrich_products_with_mongodb(products)
                
                # Sort by relevance score
                if all('score' in p for p in products):
                    products.sort(key=lambda x: x.get('score', 0), reverse=True)
                
                # Limit to top results
                products = products[:limit]
            
            # Generate response
            if products:
                category_text = detected_category if detected_category else "product"
                response_text = f"I found {len(products)} {category_text} items that match your image:"
            else:
                response_text = "I couldn't find any matching products for your image. Please try a different image or provide more details."
            
            # Save and return response
            self._save_chat_message(session_id, "assistant", response_text, products)
            
            return ChatResponse(
                session_id=session_id,
                query=user_message,
                response=response_text,
                products=products,
                timestamp=datetime.utcnow()
            )
        
        except Exception as e:
            logger.error(f"Error handling image query: {e}")
            raise
    
    def get_session_history(self, session_id: str) -> ChatHistory:
        """
        Retrieve complete chat history for a session
        
        Args:
            session_id: Session identifier
            
        Returns:
            Chat history with all messages
        """
        try:
            # Verify session
            if not self._verify_session(session_id):
                raise ValueError("Invalid session ID")
            
            # Get all messages
            messages_cursor = self.chat_collection.find(
                {"session_id": session_id}
            ).sort("timestamp", 1)
            
            messages = []
            for msg in messages_cursor:
                messages.append(
                    ChatHistoryItem(
                        role=msg["role"],
                        content=msg["content"],
                        products=msg.get("products"),
                        timestamp=msg["timestamp"]
                    )
                )
            
            return ChatHistory(
                session_id=session_id,
                messages=messages
            )
        
        except Exception as e:
            logger.error(f"Error retrieving chat history: {e}")
            raise


# Global chatbot manager instance
chatbot_manager = ChatbotManager()