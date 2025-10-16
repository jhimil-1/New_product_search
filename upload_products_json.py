#!/usr/bin/env python3
"""
Script to upload products from a JSON file to the FastAPI server.
Usage: python upload_products_json.py --file sample_jewelry.json
"""

import requests
import json
import argparse
import os

def login(username, password):
    """Login and get access token"""
    try:
        response = requests.post(
            "http://localhost:8000/auth/login",
            json={"username": username, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Login successful as {username}")
            return data["access_token"]
        else:
            print(f"✗ Login failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"✗ Login error: {str(e)}")
        return None

def upload_products_from_json(json_file_path, access_token):
    """Upload products from JSON file"""
    try:
        # Read the JSON file
        with open(json_file_path, 'r', encoding='utf-8') as f:
            products = json.load(f)
        
        print(f"✓ Found {len(products)} products in {json_file_path}")
        
        # Validate that we have a list of products
        if not isinstance(products, list):
            print("✗ JSON file must contain a list of products")
            return False
        
        # Upload the file
        with open(json_file_path, 'rb') as f:
            files = {'file': (os.path.basename(json_file_path), f, 'application/json')}
            headers = {'Authorization': f'Bearer {access_token}'}
            
            print("📤 Uploading products...")
            response = requests.post(
                "http://localhost:8000/products/upload",
                files=files,
                headers=headers
            )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Success! Uploaded {result.get('details', {}).get('inserted_count', 0)} products")
            print(f"📊 Product IDs: {result.get('details', {}).get('product_ids', [])}")
            return True
        else:
            print(f"✗ Upload failed: {response.status_code} - {response.text}")
            return False
            
    except FileNotFoundError:
        print(f"✗ File not found: {json_file_path}")
        return False
    except json.JSONDecodeError as e:
        print(f"✗ Invalid JSON file: {str(e)}")
        return False
    except Exception as e:
        print(f"✗ Upload error: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Upload jewelry products from JSON file")
    parser.add_argument("--file", "-f", required=True, help="Path to JSON file containing products")
    parser.add_argument("--username", "-u", default="test_user2", help="Username for authentication")
    parser.add_argument("--password", "-p", default="test123", help="Password for authentication")
    
    args = parser.parse_args()
    
    print(f"🚀 Starting bulk product upload from {args.file}")
    
    # Step 1: Login
    print("\n🔐 Step 1: Authenticating...")
    access_token = login(args.username, args.password)
    if not access_token:
        return
    
    # Step 2: Upload products
    print("\n📦 Step 2: Uploading products...")
    success = upload_products_from_json(args.file, access_token)
    
    if success:
        print(f"\n✅ Bulk upload completed successfully!")
        print("You can now search for these products using the jewelry search endpoint.")
    else:
        print(f"\n❌ Bulk upload failed!")

if __name__ == "__main__":
    main()