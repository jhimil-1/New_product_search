# main.py

# At the very top of main.py
import os
from dotenv import load_dotenv

# Load environment variables first
load_dotenv(override=True)  # Add override=True to ensure it reloads
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
import uvicorn

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
logging.basicConfig(level=logging.INFO)
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


class ChatQuery(BaseModel):
    query: str
    session_id: str
    category: Optional[str] = None
    limit: int = 5


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
    
    Returns:
        dict: Contains the session ID and status message
        
    Example Response:
        {
            "session_id": "507f1f77bcf86cd799439011",
            "message": "Using existing active session"
        }
    """
    try:
        # Ensure current_user is valid
        if not current_user or 'username' not in current_user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing user information"
            )
            
        # Get MongoDB collection
        try:
            db = MongoDB.get_db()
            # Test the connection by checking server info
            db.command('ping')
            sessions_collection = db["sessions"]
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Database connection error: {str(e)}"
            )
        
        # Get the actual user_id for consistent filtering
        actual_user_id = current_user.get("user_id", current_user["username"])
        
        # Check for existing active session (synchronous operation)
        existing_session = sessions_collection.find_one({
            "user_id": actual_user_id,
            "last_activity": {"$gt": datetime.utcnow() - timedelta(hours=1)}  # Active within last hour
        }, sort=[("last_activity", -1)])

        if existing_session:
            # Update last activity for existing session
            session_id = existing_session["session_id"]
            sessions_collection.update_one(
                {"session_id": session_id},
                {"$set": {"last_activity": datetime.utcnow()}}
            )
            message = "Using existing active session"
        else:
            # Create new session
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
# Add the upload_products endpoint (make sure it's properly indented)
@app.post("/products/upload", response_model=dict)
async def upload_products(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Upload a JSON file containing product data.
    
    The file should be a JSON array of product objects.
    """
    try:
        # Check file type
        if not file.filename.endswith('.json'):
            raise HTTPException(
                status_code=400,
                detail="Only JSON files are supported"
            )
        
        # Read and validate the file
        contents = await file.read()
        try:
            # Parse JSON content
            products = json.loads(contents)
            
            # Check if it's wrapped in an object with "products" key (frontend format)
            if isinstance(products, dict) and "products" in products:
                logger.warning("Received wrapped product format, extracting array")
                products = products["products"]
            
            # Ensure it's a list
            if not isinstance(products, list):
                raise ValueError(f"Expected JSON array, got {type(products).__name__}")
            
            # Validate each product matches our schema
            for product in products:
                ProductCreate(**product)
                
        except ValueError as e:  # Handles both JSONDecodeError and validation errors
            raise HTTPException(
                status_code=400,
                detail=f"Invalid product data: {str(e)}"
            )
        
        # Process the products
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
@app.post("/chat/query", response_model=ChatResponse)
async def chat_query(
    chat_data: ChatQuery,
    current_user: dict = Depends(get_current_user)
):
    """
    Process a text-based product search query.
    
    - **query**: Text query describing what you're looking for
    - **session_id**: Active session identifier
    """
    try:
        if not chat_data.query or not chat_data.query.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Query cannot be empty"
            )

        # Process the query using the chatbot manager
        response = await chatbot_manager.handle_text_query(
            session_id=chat_data.session_id,
            query=chat_data.query,
            category=chat_data.category,
            limit=chat_data.limit
        )

        # Ensure the response has the expected format
        if not hasattr(response, 'products'):
            response.products = []

        return response

    except ValueError as e:
        logger.error(f"Validation error in chat_query: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error in chat_query: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your request"
        )

@app.post("/chat/image-query", response_model=ChatResponse)
async def image_search(
    session_id: str = Form(...),
    query: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    image: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for products using an image and optional text query.
    
    - **session_id**: Active session identifier
    - **query**: (Optional) Text query to refine the search
    - **category**: (Optional) Filter by product category
    - **image**: Upload an image file (JPG, PNG, WEBP)
    """
    try:
        # Validate image file
        allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
        if image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid image type. Allowed: {', '.join(allowed_types)}"
            )
        
        # Read image content
        image_bytes = await image.read()
        
        # Detect jewelry-specific searches
        is_jewelry_search = False
        jewelry_terms = ["necklace", "necklaces", "pendant", "chain", "ring", "rings", 
                         "earring", "earrings", "bracelet", "bracelets", "jewelry"]
        
        if query and any(term in query.lower() for term in jewelry_terms):
            is_jewelry_search = True
            if "necklace" in query.lower() or "pendant" in query.lower() or "chain" in query.lower():
                category = "necklaces"
            elif "ring" in query.lower():
                category = "rings"
            elif "earring" in query.lower():
                category = "earrings"
            elif "bracelet" in query.lower():
                category = "bracelets"
            else:
                category = "jewelry"
            logger.info(f"Detected jewelry search from query: '{query}', setting category to '{category}'")
        elif category and category.lower() in ["necklaces", "rings", "earrings", "bracelets", "jewelry"]:
            is_jewelry_search = True
            logger.info(f"Explicit jewelry category search: {category}")
        
        # Log image processing
        logger.info(f"Processing image search - Size: {len(image_bytes)} bytes, Category: {category}, Query: '{query}'")
        
        # For jewelry searches, use the specialized jewelry search method
        if is_jewelry_search:
            search_results = await enhanced_product_handler.search_jewelry_by_image_and_category(
                text_query=query,
                image_bytes=image_bytes,
                category=category,
                limit=10,
                min_score=0.2 # Higher threshold for only highly relevant jewelry results
            )
        else:
            # Process the image query using enhanced product handler for better relevance
            search_results = await enhanced_product_handler.search_products(
                query=query,
                image_data=image_bytes,
                category=category,
                limit=10,
                min_relevance_score=0.2,  # Higher threshold for only highly relevant results
                search_type="image",
                user_id=current_user.get("user_id", current_user.get("username"))
            )
        
        # Log search results
        logger.info(f"Search results count: {search_results.get('count', 0)}")
        if search_results.get('results'):
            logger.info(f"Top result: {search_results['results'][0].get('name', 'N/A')} (Score: {search_results['results'][0].get('similarity_score', 0):.2f})")
        
        # Get current timestamp in ISO format
        from datetime import datetime
        
        # Format the response to match ChatResponse model
        results = search_results.get("results", [])
        response = ChatResponse(
            session_id=session_id,
            query=query or "",
            response=f"Found {len(results)} results matching your image search" + 
                       (f" in category '{category}'" if category else ""),
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing image search"
        )

# Protected route example
@app.get("/protected-route")
async def protected_route(current_user: dict = Depends(get_current_user)):
    return {"message": f"Hello {current_user['username']}, this is a protected route"}

# Chat history endpoint
@app.get("/chat/history/{session_id}", response_model=ChatHistory)
async def get_chat_history(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Retrieve chat history for a session.
    
    - **session_id**: Session identifier
    """
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

# General product similarity search endpoint
@app.post("/products/search", response_model=dict)
async def product_similarity_search(
    query: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    limit: int = Form(10),
    current_user: dict = Depends(get_current_user)
):
    """
    Search for products using CLIP-based similarity on category and image.
    
    - **query**: (Optional) Text query describing the product
    - **category**: (Optional) Filter by product category (e.g., "electronics", "clothing", "home")
    - **image**: (Optional) Upload an image of product to find similar items
    - **limit**: Maximum number of results to return
    """
    try:
        # Validate inputs
        if not query and not image:
            raise HTTPException(
                status_code=400,
                detail="Either query text or image must be provided"
            )
        
        # Handle image upload if provided
        image_data = None
        if image:
            allowed_types = ["image/jpeg", "image/png", "image/jpg", "image/webp"]
            if image.content_type not in allowed_types:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Invalid image type. Allowed: {', '.join(allowed_types)}"
                )
            
            # Read image content as raw bytes
            image_data = await image.read()
        
        # Perform product similarity search using enhanced handler for better relevance
        results = await enhanced_product_handler.search_products(
            query=query,
            image_data=image_data,
            category=category,
            limit=limit,
            min_relevance_score=0.4,  # Higher threshold for only highly relevant results
            search_type="image",
            user_id=current_user.get("user_id", current_user.get("username"))
        )
        
        # Return the results directly (already in correct format)
        return results
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Jewelry search error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Error processing jewelry similarity search"
        )

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)