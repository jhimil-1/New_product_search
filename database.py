# database.py - Improved MongoDB connection with SSL/TLS fixes
import os
import ssl
from typing import Optional
import logging
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, ConfigurationError
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

# Local MongoDB configuration for testing
MONGODB_URL_LOCAL = "mongodb://localhost:27017/"
MONGODB_DB_NAME_LOCAL = "product_chatbot_local"

logger = logging.getLogger(__name__)

class MongoDB:
    """MongoDB connection manager"""
    
    _client = None
    _db = None
    
    @classmethod
    def connect(cls):
        """Establish MongoDB connection with improved SSL/TLS handling - CLOUD PRIORITY"""
        if cls._client is None:
            try:
                # Try cloud connection first (PRIORITY)
                logger.info("🔄 Attempting cloud MongoDB connection...")
                from config import MONGODB_URL, MONGODB_DB_NAME
                
                # Enhanced connection options for MongoDB Atlas
                connection_options = {
                    'serverSelectionTimeoutMS': 15000,
                    'connectTimeoutMS': 15000,
                    'socketTimeoutMS': 15000,
                    'retryWrites': True,
                    'w': 'majority',
                    'maxPoolSize': 10,
                    'minPoolSize': 1,
                    'maxIdleTimeMS': 30000,
                    # SSL/TLS settings
                    'tls': True,
                    'tlsAllowInvalidCertificates': False,
                    'tlsAllowInvalidHostnames': False,
                }
                
                logger.info(f"Connecting to cloud MongoDB with enhanced SSL settings...")
                cls._client = MongoClient(MONGODB_URL, **connection_options)
                
                # Test connection
                logger.info("Testing cloud MongoDB connection...")
                cls._client.admin.command('ping')
                cls._db = cls._client[MONGODB_DB_NAME]
                logger.info("✅ Connected to cloud MongoDB successfully")
                
            except (ConnectionFailure, ServerSelectionTimeoutError, ConfigurationError) as cloud_error:
                logger.error(f"❌ Cloud MongoDB connection failed: {cloud_error}")
                logger.error(f"Error type: {type(cloud_error).__name__}")
                
                # Try one more time with relaxed SSL settings (fallback)
                logger.info("Trying cloud MongoDB with relaxed SSL settings...")
                try:
                    fallback_options = {
                        'serverSelectionTimeoutMS': 10000,
                        'connectTimeoutMS': 10000,
                        'socketTimeoutMS': 10000,
                        'retryWrites': True,
                        'w': 'majority',
                        # Relaxed SSL settings for compatibility
                        'tls': True,
                        'tlsAllowInvalidCertificates': True,
                        'tlsAllowInvalidHostnames': True,
                    }
                    
                    cls._client = MongoClient(MONGODB_URL, **fallback_options)
                    cls._client.admin.command('ping')
                    cls._db = cls._client[MONGODB_DB_NAME]
                    logger.info("✅ Connected to cloud MongoDB with fallback SSL settings")
                    
                except Exception as final_error:
                    logger.error(f"❌ All cloud MongoDB connection attempts failed: {final_error}")
                    logger.warning("⚠️  Trying local MongoDB as final fallback...")
                    try:
                        # Final fallback to local MongoDB
                        logger.info("Trying local MongoDB connection...")
                        cls._client = MongoClient(MONGODB_URL_LOCAL, serverSelectionTimeoutMS=5000)
                        cls._client.admin.command('ping')
                        cls._db = cls._client[MONGODB_DB_NAME_LOCAL]
                        logger.info("✅ Connected to local MongoDB successfully")
                    except Exception as local_error:
                        logger.error(f"❌ Local MongoDB connection also failed: {local_error}")
                        logger.error("❌ All MongoDB connection attempts failed")
                        cls._client = None
                        cls._db = None
    
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
            # Try cloud connection first (PRIORITY)
            logger.info("🔄 Attempting cloud Qdrant connection...")
            try:
                from config import QDRANT_URL, QDRANT_API_KEY
                cls._client = QdrantClient(
                    url=QDRANT_URL,
                    api_key=QDRANT_API_KEY,
                    timeout=15
                )
                # Test connection
                cls._client.get_collections()
                logger.info("✅ Connected to cloud Qdrant successfully")
            except Exception as cloud_error:
                logger.error(f"❌ Cloud Qdrant connection failed: {cloud_error}")
                logger.info("🔄 Trying local Qdrant connection as fallback...")
                try:
                    # Local connection fallback
                    cls._client = QdrantClient(
                        host="localhost",
                        port=6333,
                        timeout=5
                    )
                    cls._client.get_collections()
                    logger.info("✅ Connected to local Qdrant successfully")
                except Exception as local_error:
                    logger.error(f"❌ Local Qdrant connection also failed: {local_error}")
                    logger.warning("⚠️  Running with limited features (no vector search)")
                    # Return None to indicate Qdrant is not available
                    return None
        return cls._client
    
    @classmethod
    def create_collection_if_not_exists(cls, collection_name: str = None, vector_size: int = 768):
        """Create collection if it doesn't exist"""
        collection_name = collection_name or "products_local"
        client = cls.get_client()
        
        # If Qdrant is not available, skip collection creation
        if client is None:
            logger.warning("Qdrant client not available, skipping collection creation")
            return
        
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
            logger.warning("Qdrant collection creation failed. Vector search features may be limited.")

# Initialize database connections when module is imported
def initialize_databases():
    """Initialize database connections with better error handling"""
    try:
        logger.info("🔄 Initializing database connections...")
        
        # Initialize MongoDB
        MongoDB.connect()
        
        # Initialize Qdrant (this will handle its own failures)
        qdrant_manager = QdrantManager()
        qdrant_manager.create_collection_if_not_exists()
        
        logger.info("✅ Database connections initialized successfully")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize database connections: {e}")
        logger.warning("⚠️  Running without database connections - some features may be limited")
        return False

# Initialize databases when module is imported
initialize_databases()