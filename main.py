# main.py - DIAGNOSTIC VERSION to find the root cause

import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv(override=True)
print("Environment variables loaded:", bool(os.getenv("GOOGLE_API_KEY")))

import json 
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Request, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta
import logging
import uvicorn
from database import MongoDB
from product_handler import ProductHandler
from qdrant_utils import QdrantManager
from contextlib import asynccontextmanager
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

# Import auth functions
from auth import (
    get_current_user,
    signup_user,
    login_user,
    create_new_session,
    Token
)

# Import other modules
from database import MongoDB, QdrantManager
from product_handler import product_handler
from enhanced_product_handler import EnhancedProductHandler
from chatbot import chatbot_manager
from gemini_utils import gemini_manager
from models import ChatResponse, ChatHistory

# Initialize enhanced product handler
enhanced_product_handler = EnhancedProductHandler(product_handler)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Pydantic models
class UserSignup(BaseModel):
    username: str
    password: str
    email: str

class UserLogin(BaseModel):
    username: str
    password: str

class ProductCreate(BaseModel):
    name: str
    description: str
    price: float
    category: str
    image_url: str

class IngestRequest(BaseModel):
    products: List[ProductCreate]

class PublicQuery(BaseModel):
    query: Optional[str] = None
    session_id: Optional[str] = None
    category: Optional[str] = None
    limit: int = 10


class ChatQuery(BaseModel):
    query: str
    session_id: str
    category: Optional[str] = None
    limit: int = 10


# Initialize FastAPI app with lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application startup and shutdown events.
    """
    try:
        # Startup: Initialize database connections
        logger.info("Starting up application...")
        
        # Initialize MongoDB connection
        try:
            MongoDB.connect()
            logger.info("Successfully connected to MongoDB")
        except Exception as e:
            logger.warning(f"MongoDB connection failed: {str(e)}. Running without MongoDB.")
        
        # Initialize Qdrant connection
        try:
            qdrant = QdrantManager()
            qdrant.create_collection_if_not_exists()
            logger.info("Successfully connected to Qdrant")
        except Exception as e:
            logger.warning(f"Qdrant connection failed: {str(e)}. Running without Qdrant.")
        
        yield
        
    except Exception as e:
        logger.error(f"Application startup error: {str(e)}")
        raise
    finally:
        # Shutdown: Close database connections
        try:
            MongoDB.close()
            logger.info("Closed MongoDB connection")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {str(e)}")

app = FastAPI(lifespan=lifespan)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Add OPTIONS handler for CORS preflight
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        from fastapi.responses import JSONResponse
        response = JSONResponse(status_code=200, content={"message": "CORS preflight successful"})
    else:
        response = await call_next(request)
    
    # Add CORS headers
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"Request: {request.method} {request.url}")
    response = await call_next(request)
    logger.info(f"Response status: {response.status_code}")
    return response

# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to the E-commerce Product Search API. Visit /docs for API documentation."}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow()}

# Auth endpoints
@app.post("/auth/signup", response_model=dict)
async def signup(user_data: UserSignup):
    try:
        result = await signup_user(
            username=user_data.username,
            password=user_data.password,
            email=user_data.email
        )
        return result
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Signup error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during signup"
        )

@app.post("/auth/login", response_model=dict)
async def login(user_credentials: UserLogin):
    try:
        result = await login_user(
            username=user_credentials.username,
            password=user_credentials.password
        )
        if not result:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        return result
    except HTTPException as he:
        raise
    except Exception as e:
        logger.error(f"Login error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error during login"
        )

# Session creation endpoint
@app.post("/chat/sessions", response_model=dict, status_code=201)
async def create_session_endpoint(current_user: dict = Depends(get_current_user)):
    """
    Create a new chat session for the authenticated user.
    """
    try:
        if not current_user or 'username' not in current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing user information"
            )
            
        try:
            db = MongoDB.get_db()
            db.command('ping')
            sessions_collection = db["sessions"]
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection error: {str(e)}"
            )
        
        actual_user_id = current_user.get("user_id", current_user["username"])
        
        existing_session = sessions_collection.find_one({
            "user_id": actual_user_id,
            "last_activity": {"$gt": datetime.utcnow() - timedelta(hours=1)}
        }, sort=[("last_activity", -1)])

        if existing_session:
            session_id = existing_session["session_id"]
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"last_activity": datetime.utcnow()}}
            )
            message = "Using existing active session"
        else:
            session_id = str(uuid.uuid4())
            new_session = {
                "session_id": session_id,
                "user_id": actual_user_id,
                "created_at": datetime.utcnow(),
                "last_activity": datetime.utcnow()
            }
            sessions_collection.insert_one(new_session)
            message = "New session created"

        return {"session_id": session_id, "message": message}
    
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Session creation error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating session: " + str(e)
        )

# Upload products endpoint
@app.post("/products/upload", response_model=dict)
async def upload_products(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a JSON file containing product data.
    """
    try:
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported"
            )
        
        contents = await file.read()
        try:
            products = json.loads(contents)
            
            if isinstance(products, dict) and "products" in products:
                logger.warning("Received wrapped product format, extracting array")
                products = products["products"]
            
            if not isinstance(products, list):
                raise ValueError(f"Expected JSON array, got {type(products).__name__}")
            
            for product in products:
                ProductCreate(**product)
                
        except ValueError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid product data: {str(e)}"
            )
        
        result = await product_handler.process_product_upload(
            products=products,
            user_id=current_user.get("user_id", current_user.get("username"))
        )
        
        return {
            "status": "success",
            "message": f"Successfully uploaded {len(products)} products",
            "details": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Product upload error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing product upload"
        )

# JSON ingestion API (for programmatic ingestion)
@app.post("/api/ingest/products", response_model=dict)
async def ingest_products(
    payload: IngestRequest,
    current_user: dict = Depends(get_current_user)
):
    try:
        products = [p.dict() for p in payload.products]
        result = await product_handler.process_product_upload(
            products=products,
            user_id=current_user.get("user_id", current_user.get("username"))
        )
        return {
            "status": "success",
            "message": f"Ingested {len(products)} products",
            "details": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ingestion error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error ingesting products")

# DIAGNOSTIC TEXT SEARCH - Shows exactly what's happening
@app.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    chat_data: ChatQuery,
    current_user: dict = Depends(get_current_user)
):
    """
    DIAGNOSTIC VERSION - Shows detailed search process
    """
    try:
        if not chat_data.query or not chat_data.query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query cannot be empty"
            )

        logger.info("=" * 80)
        logger.info(f"🔍 SEARCH QUERY: '{chat_data.query}'")
        logger.info(f"📂 Category filter: {chat_data.category}")
        logger.info(f"📊 Requested limit: {chat_data.limit}")
        logger.info("=" * 80)

        # Call product handler
        search_results = await product_handler.search_products(
            query=chat_data.query,
            image_bytes=None,
            category=chat_data.category,
            limit=50,
            min_score=0.1,  # Very low to see everything
            user_id=current_user.get("user_id", current_user.get("username"))
        )

        results = search_results.get("results", [])
        
        logger.info(f"📦 RAW RESULTS FROM HANDLER: {len(results)} products")
        logger.info("-" * 80)
        
        # Show detailed info for each result
        for idx, item in enumerate(results[:15], 1):
            logger.info(f"{idx}. '{item.get('name', 'N/A')}'")
            logger.info(f"   Category: {item.get('category', 'N/A')}")
            logger.info(f"   Similarity: {item.get('similarity_score', 0):.4f}")
            logger.info(f"   Description: {item.get('description', 'N/A')[:60]}...")
            logger.info("")
        
        logger.info("=" * 80)

        # Apply keyword-based filtering
        query_lower = chat_data.query.lower()
        # Remove generic/stop words so broad queries don't over-filter
        stop_words = {
            "product", "products", "item", "items", "show", "find", "get", "list",
            "the", "a", "an", "in", "for", "of", "to", "and", "or", "please",
            "category", "categories", "with", "without"
        }
        query_words = set(w for w in query_lower.split() if w and w not in stop_words)
        
        logger.info(f"🔎 Query keywords: {query_words}")
        
        filtered_results = []
        # If there are no meaningful keywords left, skip keyword filtering entirely
        skip_keyword_filter = len(query_words) == 0
        for item in results:
            name_lower = item.get("name", "").lower()
            desc_lower = item.get("description", "").lower()
            cat_lower = item.get("category", "").lower()
            
            if skip_keyword_filter:
                # Accept all results if no meaningful keywords
                item["keyword_match"] = True
                item["match_reason"] = "No specific keywords; using semantic results"
                filtered_results.append(item)
                continue

            # Check for keyword matches
            name_match = any(word in name_lower for word in query_words)
            desc_match = any(word in desc_lower for word in query_words)
            cat_match = any(word in cat_lower for word in query_words)
            
            # Special handling for "dress" queries
            if "dress" in query_lower or "dresses" in query_lower:
                if "dress" in name_lower or "dress" in desc_lower:
                    item["keyword_match"] = True
                    item["match_reason"] = "Contains 'dress'"
                    filtered_results.append(item)
                    logger.info(f"✅ MATCHED: '{item.get('name')}' - Contains 'dress'")
                    continue
            
            # General keyword matching
            if name_match or desc_match or cat_match:
                item["keyword_match"] = True
                match_parts = []
                if name_match: match_parts.append("name")
                if desc_match: match_parts.append("desc")
                if cat_match: match_parts.append("category")
                item["match_reason"] = f"Matched in: {', '.join(match_parts)}"
                filtered_results.append(item)
                logger.info(f"✅ MATCHED: '{item.get('name')}' - {item['match_reason']}")
            else:
                logger.info(f"❌ FILTERED OUT: '{item.get('name')}' - No keyword match")

        logger.info(f"\n📊 AFTER KEYWORD FILTERING: {len(filtered_results)} products")
        
        # Fallback: if keyword filtering removed everything, keep top semantic results
        if not filtered_results and results:
            logger.info("No keyword matches; falling back to top semantic results")
            filtered_results = sorted(
                results,
                key=lambda x: x.get("similarity_score", 0),
                reverse=True
            )[:chat_data.limit]
        logger.info("=" * 80)

        # Sort by similarity score
        filtered_results = sorted(
            filtered_results,
            key=lambda x: x.get("similarity_score", 0),
            reverse=True
        )[:chat_data.limit]

        # Generate response
        if filtered_results:
            response_msg = f"Found {len(filtered_results)} products matching '{chat_data.query}'"
        else:
            response_msg = f"❌ No products found matching '{chat_data.query}'. The search returned {len(results)} results but none matched your keywords."

        response = ChatResponse(
            session_id=chat_data.session_id,
            query=chat_data.query,
            response=response_msg,
            products=[{
                "id": str(item.get("id", item.get("_id", ""))),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "price": str(item.get("price", "")),
                "category": item.get("category", ""),
                "image_url": item.get("image_url", ""),
                "similarity_score": float(item.get("similarity_score", 0.0))
            } for item in filtered_results],
            timestamp=datetime.utcnow().isoformat(),
            status="success"
        )

        return response

    except Exception as e:
        logger.error(f"❌ ERROR in chat_query: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred: {str(e)}"
        )

# Lightweight query API (for widget)
@app.post("/api/query", response_model=ChatResponse)
async def public_query(
    data: PublicQuery,
    current_user: dict = Depends(get_current_user)
):
    try:
        if (not data.query or not data.query.strip()) and not data.category:
            raise HTTPException(status_code=400, detail="Query or category is required")

        search_results = await product_handler.search_products(
            query=data.query,
            image_bytes=None,
            category=data.category,
            limit=max(1, min(50, data.limit)),
            min_score=0.2,
            user_id=current_user.get("user_id", current_user.get("username"))
        )

        results = search_results.get("results", [])

        # Strict post-filtering based on category and key terms to avoid irrelevant results
        query_text = (data.query or "").lower()
        stop_words = {"the","a","an","and","or","for","to","of","me","only","show","find","search","similar","product","products"}
        words = [w for w in query_text.split() if w and w not in stop_words]
        word_set = set(words)

        # Enforce explicit category if provided
        if data.category:
            wanted_cat = data.category.lower()
            results = [r for r in results if str(r.get("category","")) .lower() == wanted_cat]

        apparel_terms = {"dress","dresses","gown","maxi","shirt","shirts","jeans","tshirt","t-shirt","top","skirt"}
        color_terms = {"black","white","red","blue","green","gold","silver","pink","purple","yellow","brown","beige","grey","gray"}

        def contains_any(text: str, terms: set) -> bool:
            return any(t in text for t in terms)

        if word_set:
            filtered_tmp = []
            for r in results:
                name_l = str(r.get("name","")) .lower()
                desc_l = str(r.get("description","")) .lower()
                cat_l = str(r.get("category","")) .lower()

                # Apparel specificity controls
                dress_terms = {"dress","dresses","gown","maxi"}
                shirt_terms = {"shirt","shirts","tshirt","t-shirt"}
                mentioned_dress = any(t in word_set for t in dress_terms)
                mentioned_shirt = any(t in word_set for t in shirt_terms)

                # If apparel terms mentioned at all, require apparel presence
                if any(t in word_set for t in apparel_terms):
                    if not (contains_any(name_l, apparel_terms) or contains_any(desc_l, apparel_terms)):
                        continue

                # If query asks for dresses and not shirts, exclude shirts and require dress-like match
                if mentioned_dress and not mentioned_shirt:
                    if not (contains_any(name_l, dress_terms) or contains_any(desc_l, dress_terms)):
                        continue
                    if contains_any(name_l, shirt_terms) or contains_any(desc_l, shirt_terms):
                        continue

                # If query asks for shirts and not dresses, exclude dresses and require shirt-like match
                if mentioned_shirt and not mentioned_dress:
                    if not (contains_any(name_l, shirt_terms) or contains_any(desc_l, shirt_terms)):
                        continue
                    # optionally exclude dresses
                    if contains_any(name_l, dress_terms) or contains_any(desc_l, dress_terms):
                        continue

                # If color mentioned, require presence in name/desc
                needed_colors = {c for c in color_terms if c in word_set}
                if needed_colors and not (contains_any(name_l, needed_colors) or contains_any(desc_l, needed_colors)):
                    continue

                # If query doesn't mention electronics and no explicit category, exclude electronics
                mentions_electronics = any(k in word_set for k in {"phone","iphone","galaxy","electronics","mobile","smartphone"})
                if not data.category and not mentions_electronics and cat_l == "electronics":
                    continue

                filtered_tmp.append(r)

            if filtered_tmp:
                results = filtered_tmp

        # Sort by similarity and cap to limit
        results = sorted(
            results,
            key=lambda x: x.get("similarity_score", 0),
            reverse=True
        )[:max(1, min(50, data.limit))]

        return ChatResponse(
            session_id=data.session_id or str(uuid.uuid4()),
            query=data.query or "",
            response=f"Found {len(results)} products",
            products=[{
                "id": str(item.get("id", item.get("_id", ""))),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "price": str(item.get("price", "")),
                "category": item.get("category", ""),
                "image_url": item.get("image_url", ""),
                "similarity_score": float(item.get("similarity_score", 0.0))
            } for item in results],
            timestamp=datetime.utcnow().isoformat(),
            status="success"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Public query error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing query")

# IMAGE SEARCH (keep simple for now)
@app.post("/chat/image-query", response_model=ChatResponse)
async def image_search(
    session_id: str = Form(...),
    query: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Image search endpoint
    """
    try:
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid image type. Allowed: {', '.join(allowed_types)}"
            )
        
        image_bytes = await image.read()
        
        search_results = await product_handler.search_products(
            query=query,
            image_bytes=image_bytes,
            category=category,
            limit=15,
            min_score=0.2,
            user_id=current_user.get("user_id", current_user.get("username"))
        )
        
        results = search_results.get("results", [])
        
        response = ChatResponse(
            session_id=session_id,
            query=query or "Image search",
            response=f"Found {len(results)} similar products",
            products=[{
                "id": str(item.get("id", item.get("_id", ""))),
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "price": str(item.get("price", "")),
                "category": item.get("category", ""),
                "image_url": item.get("image_url", ""),
                "similarity_score": float(item.get("similarity_score", 0.0))
            } for item in results],
            timestamp=datetime.utcnow().isoformat(),
            status="success"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Image search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing image search"
        )

# Protected route
@app.get("/protected-route")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello {current_user['username']}, this is a protected route"}

# Chat history
@app.get("/chat/history/{session_id}", response_model=ChatHistory)
async def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    try:
        history = chatbot_manager.get_session_history(session_id)
        return history
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Chat history error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error retrieving chat history"
        )

# General product search
@app.post("/products/search", response_model=dict)
async def product_similarity_search(
    query: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    limit: int = Form(15),
    current_user: dict = Depends(get_current_user)
):
    try:
        if not query and not image:
            raise HTTPException(
                status_code=400,
                detail="Either query text or image must be provided"
            )
        
        image_bytes = None
        if image:
            allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
            if image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid image type. Allowed: {', '.join(allowed_types)}"
                )
            image_bytes = await image.read()
        
        results = await product_handler.search_products(
            query=query,
            image_bytes=image_bytes,
            category=category,
            limit=limit,
            min_score=0.2,
            user_id=current_user.get("user_id", current_user.get("username"))
        )
        
        return results
        
    except Exception as e:
        logger.error(f"Product search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing product similarity search"
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)