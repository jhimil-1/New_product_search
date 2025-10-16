"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, EmailStr, Field, HttpUrl
from typing import Optional, List
from datetime import datetime


# ===== Authentication Models =====
class UserSignup(BaseModel):
    """User signup request model"""
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class UserLogin(BaseModel):
    """User login request model"""
    username: str
    password: str


class Token(BaseModel):
    """JWT token response model"""
    access_token: str
    token_type: str = "bearer"
    session_id: str


class TokenData(BaseModel):
    """Token payload data"""
    user_id: str
    email: str


# ===== Session Models =====
class SessionCreate(BaseModel):
    """Session creation response"""
    session_id: str
    user_id: str
    created_at: datetime


# ===== Product Models =====
class Product(BaseModel):
    """Product data model"""
    product_id: str
    name: str
    category: str
    price: str
    description: str
    image_url: HttpUrl


class ProductUploadResponse(BaseModel):
    """Product upload response"""
    message: str
    products_uploaded: int
    user_id: str


# ===== Chat Models =====
class TextQuery(BaseModel):
    """Text-based chat query"""
    session_id: str
    query: str
    category: Optional[str] = None
    limit: int = 5


class ImageQueryResponse(BaseModel):
    """Image query metadata"""
    session_id: str
    filename: str


class ChatResponse(BaseModel):
    """Chat response with product recommendations"""
    session_id: str
    query: str
    response: str
    products: List[dict]
    timestamp: datetime


class ChatHistoryItem(BaseModel):
    """Single chat history entry"""
    role: str  # 'user' or 'assistant'
    content: str
    products: Optional[List[dict]] = None
    timestamp: datetime


class ChatHistory(BaseModel):
    """Chat history response"""
    session_id: str
    messages: List[ChatHistoryItem]


# ===== Product Search Result =====
class ProductSearchResult(BaseModel):
    """Product search result from Qdrant"""
    product_id: str
    name: str
    category: str
    price: str
    description: str
    image_url: str
    score: float