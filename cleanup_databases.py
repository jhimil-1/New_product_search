# cleanup_databases.py
import pymongo
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, ConfigurationError
from qdrant_client import QdrantClient
from qdrant_client.http import models
import os
import shutil
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to import config, fallback to environment variables
try:
    from config import (
        MONGODB_URL,
        MONGODB_DB_NAME,
        QDRANT_URL,
        QDRANT_API_KEY
    )
except ImportError:
    # Fallback to environment variables directly
    MONGODB_URL = os.getenv("MONGODB_URL")
    MONGODB_DB_NAME = os.getenv("MONGODB_DB_NAME")
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Local fallback configurations
MONGODB_URL_LOCAL = "mongodb://localhost:27017/"
MONGODB_DB_NAME_LOCAL = "ecommerce"  # Common local database names
MONGODB_DB_NAME_LOCAL_ALT = "product_chatbot_local"

def clear_mongodb():
    """Clear all collections in MongoDB - tries cloud first, then local"""
    client = None
    db = None
    
    # Try cloud MongoDB first (PRIORITY)
    if MONGODB_URL and MONGODB_DB_NAME:
        try:
            print("[*] Attempting cloud MongoDB connection...")
            connection_options = {
                'serverSelectionTimeoutMS': 15000,
                'connectTimeoutMS': 15000,
                'socketTimeoutMS': 15000,
                'retryWrites': True,
                'w': 'majority',
                'tls': True,
                'tlsAllowInvalidCertificates': False,
                'tlsAllowInvalidHostnames': False,
            }
            client = MongoClient(MONGODB_URL, **connection_options)
            client.admin.command('ping')
            db = client[MONGODB_DB_NAME]
            print(f"[OK] Connected to cloud MongoDB: {MONGODB_DB_NAME}")
        except Exception as cloud_error:
            print(f"[!] Cloud MongoDB connection failed: {str(cloud_error)}")
            print("[*] Trying cloud MongoDB with relaxed SSL settings...")
            try:
                fallback_options = {
                    'serverSelectionTimeoutMS': 10000,
                    'connectTimeoutMS': 10000,
                    'socketTimeoutMS': 10000,
                    'retryWrites': True,
                    'w': 'majority',
                    'tls': True,
                    'tlsAllowInvalidCertificates': True,
                    'tlsAllowInvalidHostnames': True,
                }
                client = MongoClient(MONGODB_URL, **fallback_options)
                client.admin.command('ping')
                db = client[MONGODB_DB_NAME]
                print(f"[OK] Connected to cloud MongoDB (fallback): {MONGODB_DB_NAME}")
            except Exception:
                client = None
                db = None
    
    # Fallback to local MongoDB
    if db is None:
        print("[*] Trying local MongoDB connection...")
        try:
            client = MongoClient(MONGODB_URL_LOCAL, serverSelectionTimeoutMS=5000)
            client.admin.command('ping')
            
            # Try common database names
            for db_name in [MONGODB_DB_NAME_LOCAL, MONGODB_DB_NAME_LOCAL_ALT]:
                try:
                    test_db = client[db_name]
                    collections = test_db.list_collection_names()
                    if collections:
                        db = test_db
                        print(f"[OK] Connected to local MongoDB: {db_name}")
                        break
                except:
                    continue
            
            # If no database found, use the first one
            if db is None:
                db = client[MONGODB_DB_NAME_LOCAL]
                print(f"[OK] Connected to local MongoDB: {MONGODB_DB_NAME_LOCAL}")
        except Exception as local_error:
            print(f"[ERROR] Local MongoDB connection failed: {str(local_error)}")
            print("[ERROR] Could not connect to MongoDB. Please check your connection settings.")
            return
    
    # Clear collections
    try:
        collections = db.list_collection_names()
        
        if not collections:
            print("   No collections found in MongoDB")
            if client:
                client.close()
            return
            
        print(f"\n   Clearing {len(collections)} MongoDB collection(s)...")
        for collection_name in collections:
            count = db[collection_name].count_documents({})
            db[collection_name].delete_many({})
            print(f"   [+] Cleared collection '{collection_name}' ({count} documents)")
            
        print("[OK] MongoDB cleanup completed successfully!")
    except Exception as e:
        print(f"[ERROR] Error cleaning MongoDB: {str(e)}")
    finally:
        if client:
            client.close()

def clear_qdrant():
    """Clear all collections in Qdrant - tries cloud first, then local"""
    client = None
    
    # Try cloud Qdrant first (PRIORITY)
    if QDRANT_URL and QDRANT_API_KEY:
        try:
            print("\n[*] Attempting cloud Qdrant connection...")
            client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                timeout=15
            )
            client.get_collections()
            print("[OK] Connected to cloud Qdrant")
        except Exception as cloud_error:
            print(f"[!] Cloud Qdrant connection failed: {str(cloud_error)}")
            client = None
    
    # Fallback to local Qdrant
    if client is None:
        print("[*] Trying local Qdrant connection...")
        try:
            client = QdrantClient(
                host="localhost",
                port=6333,
                timeout=5
            )
            client.get_collections()
            print("[OK] Connected to local Qdrant")
        except Exception as local_error:
            print(f"[ERROR] Local Qdrant connection failed: {str(local_error)}")
            print("[ERROR] Could not connect to Qdrant. Please check if Qdrant is running.")
            return
    
    # Clear collections
    try:
        collections = client.get_collections()
        collection_names = [collection.name for collection in collections.collections]
        
        if not collection_names:
            print("   No collections found in Qdrant")
            return
            
        print(f"\n   Clearing {len(collection_names)} Qdrant collection(s)...")
        for collection_name in collection_names:
            # Get collection info to show size
            try:
                info = client.get_collection(collection_name)
                points_count = info.points_count if hasattr(info, 'points_count') else 'N/A'
                client.delete_collection(collection_name)
                print(f"   [+] Deleted collection '{collection_name}' ({points_count} points)")
            except Exception as e:
                print(f"   [!] Error deleting collection '{collection_name}': {str(e)}")
            
        print("[OK] Qdrant cleanup completed successfully!")
    except Exception as e:
        print(f"[ERROR] Error cleaning Qdrant: {str(e)}")

def remove_local_storage():
    """Remove local storage directories"""
    try:
        qdrant_dirs = ["qdrant_storage", "qdrant_data", ".qdrant"]
        removed_any = False
        for dir_name in qdrant_dirs:
            if os.path.exists(dir_name):
                shutil.rmtree(dir_name)
                print(f"   [+] Removed directory: {dir_name}")
                removed_any = True
        
        if removed_any:
            print("[OK] Local storage cleanup completed!")
        else:
            print("   No local storage directories found")
    except Exception as e:
        print(f"[ERROR] Error cleaning local storage: {str(e)}")

if __name__ == "__main__":
    # Set UTF-8 encoding for Windows console compatibility
    import sys
    import io
    import argparse
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Clean up MongoDB and Qdrant databases')
    parser.add_argument('--yes', '-y', action='store_true', 
                        help='Skip confirmation prompt and proceed with cleanup')
    args = parser.parse_args()
    
    print("=" * 60)
    print("DATABASE CLEANUP TOOL")
    print("=" * 60)
    print("\nWARNING: This will DELETE ALL DATA from:")
    print("   - MongoDB (all collections)")
    print("   - Qdrant (all collections)")
    print("   - Local storage directories")
    print("\n" + "=" * 60)
    
    if not args.yes:
        response = input("\nAre you sure you want to continue? (yes/no): ").strip().lower()
        
        if response not in ['yes', 'y']:
            print("\nCleanup cancelled.")
            exit(0)
    else:
        print("\nProceeding with cleanup (--yes flag provided)...")
    
    print("\nStarting database cleanup...\n")
    
    clear_mongodb()
    clear_qdrant()
    remove_local_storage()
    
    print("\n" + "=" * 60)
    print("Cleanup completed! You can now start fresh with your new data.")
    print("=" * 60)