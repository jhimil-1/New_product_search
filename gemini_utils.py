# gemini_utils.py
import os
import logging
import time
import random
import hashlib
from typing import List, Optional, Dict
import google.generativeai as genai
from dotenv import load_dotenv
import numpy as np
from sentence_transformers import SentenceTransformer

load_dotenv()

logger = logging.getLogger(__name__)

class EmbeddingCache:
    """Simple in-memory cache for embeddings"""
    def __init__(self):
        self.cache: Dict[str, List[float]] = {}
    
    def get(self, text: str) -> Optional[List[float]]:
        key = hashlib.md5(text.encode()).hexdigest()
        return self.cache.get(key)
    
    def set(self, text: str, embedding: List[float]):
        key = hashlib.md5(text.encode()).hexdigest()
        self.cache[key] = embedding

class GeminiManager:
    """Handles interaction with the Google Gemini API with fallback to local model"""
    
    def __init__(self):
        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.cache = EmbeddingCache()
        self.local_model = None
        self.use_local = False
        self.rate_limited_until = 0
        self.initialize_models()

    def initialize_models(self):
        """Initialize both Gemini and local models"""
        # Initialize local model (only if needed)
        try:
            logger.info("Loading local embedding model...")
            self.local_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("Local model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load local model: {e}")

        # Initialize Gemini
        if not self.api_key:
            logger.warning("No Gemini API key found. Using local model only.")
            self.use_local = True
            return

        try:
            genai.configure(api_key=self.api_key)
            logger.info("Gemini API configured successfully")
        except Exception as e:
            logger.error(f"Error initializing Gemini: {e}")
            self.use_local = True

    def get_text_embedding(self, text: str) -> List[float]:
        """Get embedding with automatic fallback to local model"""
        # Check cache first
        cached = self.cache.get(text)
        if cached:
            return cached

        # If we're rate limited or in local-only mode
        if self.use_local or time.time() < self.rate_limited_until:
            return self._get_local_embedding(text)

        # Try Gemini API
        try:
            response = genai.embed_content(
                model="models/embedding-001",
                content=text,
                task_type="retrieval_document"
            )
            embedding = response["embedding"]
            self.cache.set(text, embedding)
            return embedding
        except Exception as e:
            if "quota" in str(e).lower() or "429" in str(e):
                logger.warning("Gemini API rate limit hit. Falling back to local model for 1 hour.")
                self.rate_limited_until = time.time() + 3600  # Block for 1 hour
            else:
                logger.error(f"Gemini API error: {e}")
            return self._get_local_embedding(text)

    def _get_local_embedding(self, text: str) -> List[float]:
        """Get embedding using the local model"""
        try:
            if not self.local_model:
                raise RuntimeError("Local model not available")
            embedding = self.local_model.encode(text, convert_to_numpy=True).tolist()
            self.cache.set(text, embedding)
            return embedding
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            # Return a zero vector as last resort
            return [0.0] * 384  # Default size for all-MiniLM-L6-v2

    def get_query_embedding(self, query: str) -> List[float]:
        """Alias for get_text_embedding with query prefix"""
        return self.get_text_embedding(f"query: {query}")

    def generate_response(self, query: str, products: List[Dict], chat_history: List[Dict] = None) -> str:
        """Generate natural language response for e-commerce queries"""
        try:
            # Handle greetings and simple messages first
            query_lower = query.lower().strip()
            greetings = ['hi', 'hello', 'hey', 'greetings', 'good morning', 'good afternoon', 'good evening']
            
            # Check if it's a greeting or simple message
            is_greeting = any(greeting in query_lower for greeting in greetings) or \
                         query_lower in ['hi', 'hello', 'hey']
            
            # If it's a greeting and we have chat history, respond without products
            if is_greeting and chat_history:
                # Check if this is the first message after login
                if len(chat_history) <= 2:  # First user message after welcome
                    return "Hello! I'm your personal jewellery assistant. How can I help you today?"
                else:
                    return "Hello again! How can I assist you further?"
            
            # If it's a greeting but no chat history (shouldn't happen, but just in case)
            if is_greeting:
                return "Hello! I'm your personal jewellery assistant. How can I help you today?"
                
            # If no products found and it's not a greeting, show appropriate message
            if not products:
                return "I couldn't find any products matching your query. Could you try rephrasing or providing more details?"
            
            # For non-greeting queries with products, use the existing logic
            if not self.api_key or self.use_local:
                return self._generate_local_response(query, products, chat_history)
            
            # Build context from products
            product_context = "Here are some relevant products I found:\n"
            for i, product in enumerate(products[:5], 1):
                name = product.get('name', 'Unknown Product')
                price = product.get('price', 'Price not available')
                category = product.get('category', 'General')
                description = product.get('description', '')[:100]
                
                product_context += f"{i}. {name} - ${price} ({category})\n"
                if description:
                    product_context += f"   {description}...\n"
                product_context += "\n"
            
            # Build conversation history context
            history_context = ""
            if chat_history:
                history_context = "Previous conversation:\n"
                for msg in chat_history[-3:]:  # Last 3 messages
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if len(content) > 100:
                        content = content[:100] + "..."
                    history_context += f"{role}: {content}\n"
                history_context += "\n"
            
            # Create comprehensive prompt for e-commerce
            prompt = f"""You are a helpful e-commerce assistant. Based on the user's query and available products, provide a natural, conversational response.

{history_context}
User's current query: {query}

{product_context}

Please provide a helpful response that:
1. Directly addresses the user's query
2. Mentions relevant products if available
3. Suggests alternatives if no exact matches are found
5. For gift suggestions, consider the occasion and recipient
6. For price inquiries, provide clear information about pricing

If asking about specific items like rings, necklaces, etc., focus on those categories. If no products match, suggest similar alternatives or ask for more details."""

            # Use Gemini API for response generation
            model = genai.GenerativeModel('gemini-2.5-flash')
            response = model.generate_content(prompt)

            if not response.text:
                return self._generate_local_response(query, products, chat_history)
            return response.text.strip()
                
        except Exception as e:
            logger.error(f"Error generating Gemini response: {e}")
            return self._generate_local_response(query, products, chat_history)
    
    def _generate_local_response(self, query: str, products: List[Dict], chat_history: List[Dict] = None) -> str:
        """Generate simple local response when Gemini is unavailable"""
        query_lower = query.lower()
        
        # Handle different types of e-commerce queries
        if not products:
            if any(word in query_lower for word in ['phone', 'smartphone', 'mobile', 'cell', 'telephone']):
                return "I don't currently have any smartphones, mobile phones, or cell phones in stock. However, I do have several electronics accessories that work great with phones, like power banks, headphones, and smart home devices. Would you like to see some of those options, or are you looking for something specific?"
            elif any(word in query_lower for word in ['gift', 'present', 'birthday', 'anniversary']):
                return "I don't have any specific gift suggestions available right now. Could you tell me more about the occasion or the person's interests? I'd be happy to help you find something perfect!"
            elif any(word in query_lower for word in ['price', 'cost', 'expensive', 'cheap']):
                return "I don't have pricing information for the specific item you're asking about. Could you provide more details about what you're looking for?"
            else:
                return "I couldn't find any products matching your query. Could you try rephrasing your request or provide more specific details about what you're looking for?"
        
        # Generate response based on found products
        if len(products) == 1:
            product = products[0]
            name = product.get('name', 'this product')
            price = product.get('price', 'unknown price')
            category = product.get('category', 'product')
            
            if any(word in query_lower for word in ['price', 'cost', 'expensive', 'cheap']):
                return f"The {name} is priced at ${price}. It's a great {category} option!"
            elif any(word in query_lower for word in ['similar', 'like', 'alternative']):
                return f"I found {name} which might be similar to what you're looking for. It's priced at ${price}."
            else:
                return f"I found {name} for you! It's a {category} priced at ${price}. Would you like to know more about it?"
        
        else:
            # Multiple products found
            product_names = [p.get('name', 'Product') for p in products[:3]]
            price_range = f"${products[0].get('price', '0')} - ${products[-1].get('price', '0')}"
            
            if any(word in query_lower for word in ['gift', 'present']):
                return f"I found several great gift options for you! Here are some top picks: {', '.join(product_names)}. Prices range from {price_range}. Which one catches your eye?"
            elif any(word in query_lower for word in ['show', 'display', 'list']):
                return f"Here are some products I found: {', '.join(product_names)}. Prices range from {price_range}. Let me know if you'd like details about any of them!"
            else:
                return f"I found several options that might interest you: {', '.join(product_names)}. Prices range from {price_range}. Would you like more information about any of these?"

# Global instance
gemini_manager = GeminiManager()