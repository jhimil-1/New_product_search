# database.py
import os
from typing import Optional
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from config import (
    MONGODB_URL,
    MONGODB_DB_NAME,
    QDRANT_URL,
    QDRANT_API_KEY,
    QDRANT_COLLECTION_NAME
)

logger = logging.getLogger(__name__)

class MongoDB:
    """MongoDB connection manager"""
    
    _client = None
    _db = None
    
    @classmethod
    def connect(cls):
        """Establish MongoDB connection"""
        if cls._client is None:
            try:
                # Add SSL/TLS parameters to handle connection issues
                cls._client = MongoClient(
                    MONGODB_URL,
                    tls=True,
                    tlsAllowInvalidCertificates=True,
                    tlsAllowInvalidHostnames=True,
                    serverSelectionTimeoutMS=30000,
                    connectTimeoutMS=30000,
                    socketTimeoutMS=30000,
                    maxPoolSize=10,
                    retryWrites=True
                )
                # Test the connection
                cls._client.admin.command('ping')
                cls._db = cls._client[MONGODB_DB_NAME]
                logger.info("Connected to MongoDB successfully")
            except ConnectionFailure as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise
    
    @classmethod
    def get_db(cls):
        """Get database instance"""
        if cls._db is None:
            cls.connect()
        return cls._db
    
    @classmethod
    def get_collection(cls, collection_name: str):
        """Get a specific collection from the database"""
        db = cls.get_db()
        return db[collection_name]
    
    @classmethod
    def close(cls):
        """Close MongoDB connection"""
        if cls._client:
            cls._client.close()
            cls._client = None
            cls._db = None
            logger.info("MongoDB connection closed")

class QdrantManager:
    """Qdrant vector database manager"""
    
    _client = None
    
    @classmethod
    def get_client(cls):
        """Get Qdrant client instance"""
        if cls._client is None:
            try:
                cls._client = QdrantClient(
                    url=QDRANT_URL,
                    api_key=QDRANT_API_KEY
                )
                logger.info("Connected to Qdrant successfully")
            except Exception as e:
                logger.error(f"Failed to connect to Qdrant: {e}")
                raise
        return cls._client
    
    @classmethod
    def create_collection_if_not_exists(cls, collection_name: str = None, vector_size: int = 768):
        """Create collection if it doesn't exist"""
        collection_name = collection_name or QDRANT_COLLECTION_NAME
        client = cls.get_client()
        
        try:
            collections = client.get_collections()
            collection_names = [collection.name for collection in collections.collections]
            
            if collection_name not in collection_names:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {collection_name}")
            else:
                logger.info(f"Using existing collection: {collection_name}")
                
        except UnexpectedResponse as e:
            logger.error(f"Error creating Qdrant collection: {e}")
            raise

# Initialize database connections when module is imported
try:
    MongoDB.connect()
    qdrant_manager = QdrantManager()
    qdrant_manager.create_collection_if_not_exists()
    logger.info("Database connections initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database connections: {e}")
    raise