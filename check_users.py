import pymongo
from pprint import pprint

def check_users():
    try:
        # Connect to MongoDB
        client = pymongo.MongoClient("mongodb://localhost:27017/")
        db = client.get_database('ecommerce')
        
        # Get all users
        users = list(db.users.find({}, {'username': 1, 'hashed_password': 1, '_id': 1}))
        
        print("\n=== Users in Database ===")
        if not users:
            print("No users found in the database.")
        else:
            for user in users:
                print(f"\nUsername: {user.get('username')}")
                print(f"User ID: {user.get('_id')}")
                print(f"Has Password: {'Yes' if 'hashed_password' in user else 'No'}")
        
        # Try to find testuser specifically
        test_user = db.users.find_one({"username": "testuser"})
        
        print("\n=== Test User Details ===")
        if test_user:
            print(f"Test user exists!")
            print(f"Username: {test_user.get('username')}")
            print(f"User ID: {test_user.get('_id')}")
            print(f"Has Password: {'Yes' if 'hashed_password' in test_user else 'No'}")
            
            # Try to verify the password
            if 'hashed_password' in test_user:
                from passlib.context import CryptContext
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
                password_correct = pwd_context.verify("testpass123", test_user['hashed_password'])
                print(f"Password verification: {'SUCCESS' if password_correct else 'FAILED'}")
        else:
            print("Test user 'testuser' not found!")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    check_users()
