import streamlit as st
import requests
import json
import uuid
from PIL import Image
import io
import base64
from typing import List, Dict, Any, Optional

# Page configuration
st.set_page_config(
    page_title="Jewelry API Tester",
    page_icon="💎",
    layout="wide"
)

# Initialize session state
if 'access_token' not in st.session_state:
    st.session_state.access_token = None
if 'user_info' not in st.session_state:
    st.session_state.user_info = None
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'products_uploaded' not in st.session_state:
    st.session_state.products_uploaded = False

# API Configuration
API_BASE_URL = "http://localhost:8000"

# Helper functions
def login(username, password):
    """Login and get access token"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/login",
            json={"username": username, "password": password}
        )
        if response.status_code == 200:
            data = response.json()
            st.session_state.access_token = data["access_token"]
            st.session_state.user_info = data.get("user", {})
            return True, "Login successful!"
        else:
            return False, f"Login failed: {response.text}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def register(username, email, password, full_name):
    """Register new user"""
    try:
        response = requests.post(
            f"{API_BASE_URL}/auth/signup",
            json={
                "username": username,
                "email": email,
                "password": password
            }
        )
        if response.status_code == 200:
            return True, "Registration successful! Please login."
        else:
            return False, f"Registration failed: {response.text}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def search_jewelry_text(query, category=None):
    """Search jewelry by text"""
    try:
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        data = {"query": query}
        if category:
            data["category"] = category
            
        response = requests.post(
            f"{API_BASE_URL}/products/search",
            data=data,
            headers=headers
        )
        return response
    except Exception as e:
        return None, str(e)

def search_jewelry_image(image_file, category=None):
    """Search jewelry by image"""
    try:
        headers = {
            "Authorization": f"Bearer {st.session_state.access_token}",
            "accept": "application/json"
        }
        
        # Prepare form data
        files = {
            'image': (image_file.name, image_file.getvalue(), image_file.type),
        }
        
        data = {
            'session_id': st.session_state.session_id,
        }
        
        if category:
            data['category'] = category
        
        # Make the request to the correct endpoint
        response = requests.post(
            f"{API_BASE_URL}/chat/image-query",
            files=files,
            data=data,
            headers=headers
        )
        
        # Log the response for debugging
        if response.status_code != 200:
            st.error(f"Error: {response.status_code} - {response.text}")
        
        # Log the response data for debugging
        try:
            response_data = response.json()
            print("API Response:", response_data)  # Debug log
            
            # Ensure the response has the expected structure
            if 'products' in response_data and isinstance(response_data['products'], list):
                # Convert to the format expected by the frontend
                response_data['results'] = response_data.pop('products')
                response_data['count'] = len(response_data['results'])
                
                # Update the response with the modified data
                response._content = json.dumps(response_data).encode('utf-8')
                
        except Exception as e:
            print(f"Error processing response: {str(e)}")
            
        return response
    except Exception as e:
        return None, str(e)

def upload_jewelry(name, description, category, price, material, gemstone, image_file):
    """Upload new jewelry"""
    try:
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        files = {"image": image_file}
        data = {
            "name": name,
            "description": description,
            "category": category,
            "price": str(price),
            "material": material,
            "gemstone": gemstone
        }
        
        response = requests.post(
            f"{API_BASE_URL}/jewelry/upload",
            files=files,
            data=data,
            headers=headers
        )
        return response
    except Exception as e:
        return None, str(e)

def chat_with_bot(message: str, image_uploaded: bool = False, image_data: Optional[bytes] = None) -> Dict[str, Any]:
    """
    Chat with jewelry bot with support for both text and image queries
    """
    try:
        headers = {
            "Authorization": f"Bearer {st.session_state.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "query": message,
            "session_id": st.session_state.session_id,
            "is_image_query": image_uploaded
        }
        
        if image_uploaded and image_data:
            # For image queries, send as multipart form data
            files = {
                'image': ('image.jpg', image_data, 'image/jpeg')
            }
            response = requests.post(
                f"{API_BASE_URL}/chat/query",
                files=files,
                data=payload,
                headers={"Authorization": f"Bearer {st.session_state.access_token}"}
            )
        else:
            # For text queries, send as JSON
            response = requests.post(
                f"{API_BASE_URL}/chat/query",
                json=payload,
                headers=headers
            )
            
        if response.status_code == 200:
            return response.json()
        else:
            return {"error": f"Error: {response.status_code} - {response.text}"}
            
    except Exception as e:
        return {"error": f"Connection error: {str(e)}"}

def upload_products_json(json_file) -> Dict[str, Any]:
    """Upload products from JSON file and validate the structure"""
    try:
        # Validate JSON structure
        try:
            products = json.load(json_file)
            if not isinstance(products, list):
                return {"status": "error", "message": "Invalid format: Expected a list of products"}
                
            # Basic validation of product structure
            required_fields = ["name", "description", "image_url", "category", "price"]
            for i, product in enumerate(products):
                if not all(field in product for field in required_fields):
                    return {"status": "error", "message": f"Product at index {i} is missing required fields"}
        except json.JSONDecodeError:
            return {"status": "error", "message": "Invalid JSON file"}
        
        # Reset file pointer after reading
        json_file.seek(0)
        
        # Upload to server
        headers = {"Authorization": f"Bearer {st.session_state.access_token}"}
        files = {"file": (json_file.name, json_file, "application/json")}
        
        response = requests.post(
            f"{API_BASE_URL}/products/upload",
            files=files,
            headers=headers
        )
        
        if response.status_code == 200:
            st.session_state.products_uploaded = True
            return {"status": "success", "data": response.json()}
        else:
            return {"status": "error", "message": f"Upload failed: {response.text}"}
            
    except Exception as e:
        return {"status": "error", "message": f"Error: {str(e)}"}

# Main UI
st.title("💎 Jewelry API Tester")
st.markdown("Test your FastAPI jewelry endpoints with this interactive interface")

# Sidebar for authentication
with st.sidebar:
    st.header("🔐 Authentication")
    
    if st.session_state.access_token:
        st.success(f"✅ Logged in as: {st.session_state.user_info.get('username', 'User')}")
        st.write(f"**Email:** {st.session_state.user_info.get('email', 'N/A')}")
        if st.button("🚪 Logout"):
            st.session_state.access_token = None
            st.session_state.user_info = None
            st.session_state.chat_history = []  # Clear chat history on logout
            st.rerun()
    else:
        st.info("💡 **Quick Login:** Use username: `test_user2` and password: `test123`")
        
        auth_tab1, auth_tab2 = st.tabs(["Login", "Register"])
        
        with auth_tab1:
            with st.form("login_form"):
                username = st.text_input("Username", value="test_user2", placeholder="Enter username")
                password = st.text_input("Password", type="password", placeholder="Enter password")
                submitted = st.form_submit_button("🔑 Login")
                
                if submitted:
                    success, message = login(username, password)
                    if success:
                        st.success(f"✅ {message}")
                        st.rerun()
                    else:
                        st.error(f"❌ {message}")
        
        with auth_tab2:
            with st.form("register_form"):
                reg_username = st.text_input("Username", placeholder="Choose a username")
                reg_email = st.text_input("Email", placeholder="your@email.com")
                reg_password = st.text_input("Password", type="password", placeholder="Choose a password")
                reg_full_name = st.text_input("Full Name", placeholder="Your full name")
                submitted = st.form_submit_button("📝 Register")
                
                if submitted:
                    success, message = register(reg_username, reg_email, reg_password, reg_full_name)
                    if success:
                        st.success(f"✅ {message}")
                    else:
                        st.error(f"❌ {message}")
    
    st.markdown("---")
    st.markdown("### 💡 **How to use:**")
    st.markdown("1. **Login** or **Register**")
    st.markdown("2. **Upload products** (if none exist)")
    st.markdown("3. **Chat with the assistant** to search jewelry")
    st.markdown("4. **Upload images** to find similar items")
    st.markdown("---")
    
    # Quick actions
    st.markdown("### ⚡ Quick Actions")
    if st.button("🔄 Refresh App"):
        st.rerun()
    
    if st.button("🗑️ Clear Chat") and st.session_state.access_token:
        st.session_state.chat_history = []
        st.rerun()
    
    # Status indicators
    st.markdown("---")
    st.markdown("### 📊 Status")
    
    # Server status
    try:
        response = requests.get(f"{API_BASE_URL}/", timeout=2)
        if response.status_code == 200:
            st.success("✅ Server Online")
        else:
            st.error("❌ Server Issue")
    except:
        st.error("❌ Server Offline")
    
    # Authentication status
    if st.session_state.access_token:
        st.success("✅ Authenticated")
    else:
        st.warning("⚠️ Not Authenticated")
    
    # Products status
    if st.session_state.products_uploaded:
        st.success("✅ Products Loaded")
    else:
        st.info("📦 No Products Loaded")

# Main content area
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["🔍 Text Search", "🖼️ Image Search", "⬆️ Upload Jewelry", "📁 Bulk Upload", "💬 Chat Bot", "📊 API Status"])

with tab1:
    st.header("Text-based Jewelry Search")
    
    if not st.session_state.access_token:
        st.warning("Please login first to test the search functionality")
    else:
        with st.form("text_search_form"):
            col1, col2 = st.columns(2)
            with col1:
                query = st.text_input("Search Query", value="simple gold ring", 
                                    help="Enter a description of the jewelry you're looking for")
            with col2:
                category = st.selectbox("Category (optional)", 
                                      ["", "rings", "necklaces", "earrings", "bracelets", "watches"],
                                      help="Filter by jewelry category")
            
            submitted = st.form_submit_button("Search Jewelry")
            
            if submitted:
                with st.spinner("Searching jewelry..."):
                    response = search_jewelry_text(query, category if category else None)
                    
                    if response and response.status_code == 200:
                        data = response.json()
                        st.success(f"Found {data.get('count', 0)} results")
                        
                        if data.get("results"):
                            for idx, item in enumerate(data["results"]):
                                with st.expander(f"{item.get('name', 'Unknown')} - Score: {item.get('similarity_score', 0):.3f}"):
                                    # Check for image data
                                    image_data = None
                                    if item.get('image'):
                                        # Base64 encoded image
                                        image_data = item['image']
                                    elif item.get('image_url'):
                                        # URL image
                                        image_data = item['image_url']
                                    
                                    # Display image if available
                                    if image_data:
                                        try:
                                            if image_data.startswith('data:image'):
                                                # Display base64 image
                                                st.image(image_data, caption=item.get('name', 'Product Image'), width='stretch')
                                            elif image_data.startswith('http'):
                                                # Display URL image
                                                st.image(image_data, caption=item.get('name', 'Product Image'), width='stretch')
                                            else:
                                                # Try to display as base64
                                                import base64
                                                from PIL import Image
                                                import io
                                                image_bytes = base64.b64decode(image_data)
                                                image = Image.open(io.BytesIO(image_bytes))
                                                st.image(image, caption=item.get('name', 'Product Image'), width='stretch')
                                        except Exception as e:
                                            st.warning(f"Could not display image: {str(e)}")
                                    
                                    # Display product details
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.write(f"**Category:** {item.get('category', 'N/A')}")
                                        st.write(f"**Price:** ${item.get('price', 'N/A')}")
                                        st.write(f"**Material:** {item.get('material', 'N/A')}")
                                    with col2:
                                        st.write(f"**Gemstone:** {item.get('gemstone', 'N/A')}")
                                        st.write(f"**Description:** {item.get('description', 'N/A')}")
                    else:
                        st.error(f"Search failed: {response.text if response else 'Unknown error'}")

with tab2:
    st.header("Image-based Jewelry Search")
    
    if not st.session_state.access_token:
        st.warning("Please login first to test the search functionality")
    else:
        with st.form("image_search_form"):
            uploaded_image = st.file_uploader("Upload jewelry image", 
                                              type=['png', 'jpg', 'jpeg'],
                                              help="Upload an image of jewelry to find similar items")
            
            category = st.selectbox("Category (optional)", 
                                  ["", "rings", "necklaces", "earrings", "bracelets", "watches"],
                                  help="Filter by jewelry category")
            
            submitted = st.form_submit_button("Search by Image")
            
            if submitted and uploaded_image:
                with st.spinner("Analyzing image and searching..."):
                    response = search_jewelry_image(uploaded_image, category if category else None)
                    
                    if response and response.status_code == 200:
                        try:
                            data = response.json()
                            print("Response Data:", data)  # Debug log
                            
                            # Show uploaded image
                            st.image(uploaded_image, caption="Uploaded Image", width=300)
                            
                            # Show results
                            if data.get("results"):
                                st.success(f"Found {len(data['results'])} results")
                                
                                # Sort results by similarity score (highest first)
                                results = sorted(data["results"], 
                                              key=lambda x: x.get('similarity_score', 0), 
                                              reverse=True)
                                
                                for idx, item in enumerate(results):
                                    with st.container():
                                        st.markdown("---")
                                        st.subheader(f"{item.get('name', 'Unknown')}")
                                        st.caption(f"Similarity Score: {item.get('similarity_score', 0):.2f}")
                                        
                                        # Create columns for image and details
                                        col1, col2 = st.columns([1, 2])
                                        
                                        with col1:
                                            # Display product image
                                            image_url = item.get('image_url', '')
                                            if image_url:
                                                st.image(image_url, use_container_width=True)
                                            else:
                                                st.warning("No image available")
                                        
                                        with col2:
                                            # Display product details
                                            st.write(f"**Category:** {item.get('category', 'N/A')}")
                                            st.write(f"**Price:** ${item.get('price', 'N/A')}")
                                            st.write(f"**Description:** {item.get('description', 'N/A')}")
                                            
                                            # Additional details if available
                                            if 'material' in item or 'gemstone' in item:
                                                st.write("**Details:**")
                                                if 'material' in item:
                                                    st.write(f"- Material: {item['material']}")
                                                if 'gemstone' in item:
                                                    st.write(f"- Gemstone: {item['gemstone']}")
                            else:
                                st.warning("No results found. Try adjusting your search criteria.")
                                
                        except Exception as e:
                            st.error(f"Error processing response: {str(e)}")
                            st.json(response.json() if hasattr(response, 'json') else {})
                    else:
                        st.error(f"Search failed: {response.text if response else 'Unknown error'}")

with tab3:
    st.header("Upload New Jewelry")
    
    if not st.session_state.access_token:
        st.warning("Please login first to upload jewelry")
    else:
        with st.form("upload_form"):
            name = st.text_input("Jewelry Name", placeholder="e.g., Diamond Solitaire Ring")
            description = st.text_area("Description", placeholder="Beautiful diamond engagement ring...")
            
            col1, col2 = st.columns(2)
            with col1:
                category = st.selectbox("Category", ["rings", "necklaces", "earrings", "bracelets", "watches"])
                price = st.number_input("Price ($)", min_value=0.0, step=0.01, format="%.2f")
            with col2:
                material = st.text_input("Material", placeholder="e.g., 18k white gold")
                gemstone = st.text_input("Gemstone", placeholder="e.g., diamond")
            
            image_file = st.file_uploader("Jewelry Image", type=['png', 'jpg', 'jpeg'])
            
            submitted = st.form_submit_button("Upload Jewelry")
            
            if submitted and name and image_file:
                with st.spinner("Uploading jewelry..."):
                    response = upload_jewelry(name, description, category, price, material, gemstone, image_file)
                    
                    if response and response.status_code == 201:
                        st.success("Jewelry uploaded successfully!")
                        data = response.json()
                        st.json(data)
                    else:
                        st.error(f"Upload failed: {response.text if response else 'Unknown error'}")

with tab4:
    st.header("📁 Bulk Upload Products")
    
    if not st.session_state.access_token:
        st.warning("Please login first to upload products")
    else:
        st.markdown("Upload multiple products at once using a JSON file")
        
        # Show sample JSON format
        with st.expander("📋 JSON File Format Example"):
            sample_data = [
                {
                    "name": "Diamond Solitaire Ring",
                    "description": "Elegant 1-carat diamond solitaire ring in 14k white gold",
                    "price": 2999.99,
                    "category": "rings",
                    "image_url": "https://example.com/diamond-ring.jpg"
                },
                {
                    "name": "Gold Chain Necklace",
                    "description": "Classic 18-inch 14k yellow gold chain necklace",
                    "price": 899.99,
                    "category": "necklaces",
                    "image_url": "https://example.com/gold-chain.jpg"
                }
            ]
            st.json(sample_data)
            st.info("Your JSON file should contain an array of product objects like these.")
        
        # File upload
        uploaded_json = st.file_uploader(
            "Choose a JSON file",
            type=['json'],
            help="Select a JSON file containing product data"
        )
        
        if uploaded_json is not None:
            # Preview the file content
            try:
                content = json.load(uploaded_json)
                st.success(f"✅ Found {len(content)} products in the file")
                
                # Reset file pointer for actual upload
                uploaded_json.seek(0)
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON file: {str(e)}")
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")
        
        # Upload button outside the form
        if uploaded_json is not None and st.button("📤 Upload Products", type="primary"):
            try:
                content = json.load(uploaded_json)
                st.success(f"✅ Found {len(content)} products in the file")
                
                # Reset file pointer for actual upload
                uploaded_json.seek(0)
                
                with st.spinner("Uploading products..."):
                    response = upload_products_json(uploaded_json)
                    
                    if response and response.status_code == 200:
                        data = response.json()
                        st.success(f"✅ Successfully uploaded {data.get('details', {}).get('inserted_count', 0)} products!")
                        
                        # Show uploaded product IDs
                        product_ids = data.get('details', {}).get('product_ids', [])
                        if product_ids:
                            st.info(f"Product IDs: {', '.join(product_ids[:5])}{'...' if len(product_ids) > 5 else ''}")
                    else:
                        st.error(f"Upload failed: {response.text if response else 'Unknown error'}")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON file: {str(e)}")
            except Exception as e:
                st.error(f"Error reading file: {str(e)}")

# Enhanced Chatbot Interface
st.sidebar.title("💎 Jewelry Assistant")

# Add chat mode selector
chat_mode = st.sidebar.selectbox(
    "Search Mode",
    ["Text Search", "Image Search", "Smart Assistant"],
    help="Choose how you want to search for jewelry"
)

# Quick category filters
st.sidebar.markdown("---")
st.sidebar.subheader("Quick Filters")
selected_category = st.sidebar.selectbox(
    "Category",
    ["All Categories", "rings", "necklaces", "earrings", "bracelets", "watches"],
    help="Filter by jewelry category"
)

# Price range filter
price_range = st.sidebar.slider(
    "Price Range ($)",
    min_value=0,
    max_value=10000,
    value=(0, 10000),
    step=100,
    help="Filter by price range"
)

# Main App Flow
st.sidebar.markdown("---")
page = st.sidebar.radio(
    "Go to",
    ["Chat with Assistant", "Upload Products", "Search Tools"],
    index=0
)

if page == "Chat with Assistant":
    st.title("💎 Jewelry Assistant")
    st.markdown("*Your personal jewelry expert - search by text, image, or natural conversation*")
    
    if not st.session_state.access_token:
        st.warning("🔐 Please login first to chat with the assistant")
        st.info("Use the sidebar to login or register")
    else:
        # Chat interface
        chat_container = st.container()
        
        with chat_container:
            # Display chat history
            for message in st.session_state.chat_history:
                with st.chat_message(message["role"]):
                    st.markdown(message["content"])
                    if "image" in message and message["image"]:
                        st.image(message["image"], caption=message.get("caption", ""), width=200)
                    if "results" in message and message["results"]:
                        # Display search results in chat
                        results = message["results"]
                        if results:
                            st.write(f"Found {len(results)} jewelry items:")
                            for idx, item in enumerate(results[:3]):  # Show top 3 results
                                with st.expander(f"💎 {item.get('name', 'Unknown')} - ${item.get('price', 'N/A')}"):
                                    col1, col2 = st.columns([1, 2])
                                    with col1:
                                        if item.get('image_url'):
                                            st.image(item['image_url'], use_container_width=True)
                                    with col2:
                                        st.write(f"**Category:** {item.get('category', 'N/A')}")
                                        st.write(f"**Price:** ${item.get('price', 'N/A')}")
                                        st.write(f"**Description:** {item.get('description', 'N/A')}")
                                        if item.get('similarity_score'):
                                            st.write(f"**Match Score:** {item.get('similarity_score'):.2f}")
                        else:
                            st.info("No jewelry found matching your criteria. Try different search terms or check our other categories.")
        
        # Input area
        st.markdown("---")
        
        # Image upload area (above text input)
        uploaded_image = st.file_uploader(
            "📸 Upload a jewelry image (optional)",
            type=["jpg", "jpeg", "png"],
            help="Upload an image to find similar jewelry items"
        )
        
        # Text input
        user_input = st.chat_input(
            "Ask me anything: 'Show me gold necklaces', 'Find rings under $500', or upload an image above..."
        )
        
        # Process user input
        if user_input or uploaded_image:
            # Add user message to chat history
            if user_input:
                st.session_state.chat_history.append({
                    "role": "user", 
                    "content": user_input,
                    "image": None,
                    "results": None
                })
            
            # Process the query
            with st.spinner("🔍 Searching our jewelry collection..."):
                try:
                    if uploaded_image:
                        # Image-based search
                        response = search_jewelry_image(uploaded_image, selected_category if selected_category != "All Categories" else None)
                        if response and response.status_code == 200:
                            data = response.json()
                            results = data.get("results", [])
                            
                            # Add image to user message
                            if st.session_state.chat_history and user_input:
                                st.session_state.chat_history[-1]["image"] = uploaded_image
                                st.session_state.chat_history[-1]["caption"] = "Uploaded image"
                            
                            # Add assistant response
                            assistant_message = f"I found {len(results)} jewelry items similar to your uploaded image!"
                            if selected_category != "All Categories":
                                assistant_message += f" (filtered by {selected_category})"
                            
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": assistant_message,
                                "image": None,
                                "results": results
                            })
                        else:
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": "Sorry, I couldn't process your image search. Please try again.",
                                "image": None,
                                "results": None
                            })
                    
                    elif user_input:
                        # Text-based search with smart parsing
                        category_filter = selected_category if selected_category != "All Categories" else None
                        
                        # Parse user input for category hints
                        input_lower = user_input.lower()
                        if "ring" in input_lower and not category_filter:
                            category_filter = "rings"
                        elif "necklace" in input_lower and not category_filter:
                            category_filter = "necklaces"
                        elif "earring" in input_lower and not category_filter:
                            category_filter = "earrings"
                        elif "bracelet" in input_lower and not category_filter:
                            category_filter = "bracelets"
                        elif "watch" in input_lower and not category_filter:
                            category_filter = "watches"
                        
                        response = search_jewelry_text(user_input, category_filter)
                        if response and response.status_code == 200:
                            data = response.json()
                            results = data.get("results", [])
                            
                            # Generate smart response
                            if results:
                                assistant_message = f"Great! I found {len(results)} jewelry items matching your request."
                                if category_filter:
                                    assistant_message += f" Here are some beautiful {category_filter}:"
                                else:
                                    assistant_message += " Here are my top recommendations:"
                            else:
                                assistant_message = "I couldn't find any jewelry matching your exact criteria. Try searching for something like 'gold rings', 'diamond necklaces', or upload an image of jewelry you like!"
                            
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": assistant_message,
                                "image": None,
                                "results": results
                            })
                        else:
                            st.session_state.chat_history.append({
                                "role": "assistant",
                                "content": "Sorry, I couldn't process your search. Please try again or check your connection.",
                                "image": None,
                                "results": None
                            })
                    
                    # Rerun to update chat display
                    st.rerun()
                    
                except Exception as e:
                    st.session_state.chat_history.append({
                        "role": "assistant",
                        "content": f"I encountered an error: {str(e)}. Please try again.",
                        "image": None,
                        "results": None
                    })
                    st.rerun()
        
        # Clear chat button
        if st.session_state.chat_history:
            if st.button("🗑️ Clear Chat History"):
                st.session_state.chat_history = []
                st.rerun()

elif page == "Upload Products":
    st.title("📤 Upload Jewelry Products")
    
    if not st.session_state.access_token:
        st.warning("🔐 Please login first to upload products")
        st.info("Use the sidebar to login or register")
    else:
        st.info("Upload a JSON file containing your jewelry products. The file should contain an array of products with the following fields: name, description, image_url, category, and price.")
        
        uploaded_file = st.file_uploader("Choose a JSON file", type="json")
        
        if uploaded_file is not None:
            with st.spinner("Uploading products..."):
                result = upload_products_json(uploaded_file)
                
                if result["status"] == "success":
                    st.success("✅ Products uploaded successfully!")
                    st.session_state.products_uploaded = True
                    st.rerun()
                else:
                    st.error(f"❌ Error: {result.get('message', 'Unknown error occurred')}")

elif page == "Search Tools":
    st.title("🔍 Advanced Search Tools")
    
    if not st.session_state.access_token:
        st.warning("🔐 Please login first to use search tools")
    else:
        tab1, tab2 = st.tabs(["Text Search", "Image Search"])
        
        with tab1:
            st.header("Advanced Text Search")
            with st.form("advanced_text_search"):
                query = st.text_input("Search Query", placeholder="e.g., gold diamond ring under 1000")
                category = st.selectbox("Category", ["", "rings", "necklaces", "earrings", "bracelets", "watches"])
                submitted = st.form_submit_button("Search")
                
                if submitted:
                    with st.spinner("Searching..."):
                        response = search_jewelry_text(query, category if category else None)
                        if response and response.status_code == 200:
                            data = response.json()
                            st.success(f"Found {data.get('count', 0)} results")
                            
                            if data.get("results"):
                                for item in data["results"]:
                                    with st.expander(f"{item.get('name', 'Unknown')} - ${item.get('price', 'N/A')}"):
                                        col1, col2 = st.columns([1, 2])
                                        with col1:
                                            if item.get('image_url'):
                                                st.image(item['image_url'], use_container_width=True)
                                        with col2:
                                            st.write(f"**Category:** {item.get('category', 'N/A')}")
                                            st.write(f"**Price:** ${item.get('price', 'N/A')}")
                                            st.write(f"**Description:** {item.get('description', 'N/A')}")
                                            st.write(f"**Similarity Score:** {item.get('similarity_score', 0):.3f}")
                        else:
                            st.error("Search failed")
        
        with tab2:
            st.header("Advanced Image Search")
            with st.form("advanced_image_search"):
                uploaded_image = st.file_uploader("Upload jewelry image", type=['png', 'jpg', 'jpeg'])
                category = st.selectbox("Category Filter", ["", "rings", "necklaces", "earrings", "bracelets", "watches"])
                submitted = st.form_submit_button("Search by Image")
                
                if submitted and uploaded_image:
                    with st.spinner("Analyzing image and searching..."):
                        response = search_jewelry_image(uploaded_image, category if category else None)
                        if response and response.status_code == 200:
                            data = response.json()
                            st.image(uploaded_image, caption="Uploaded Image", width=300)
                            
                            if data.get("results"):
                                st.success(f"Found {len(data['results'])} similar items")
                                for item in data["results"]:
                                    with st.expander(f"{item.get('name', 'Unknown')} - Similarity: {item.get('similarity_score', 0):.2f}"):
                                        col1, col2 = st.columns([1, 2])
                                        with col1:
                                            if item.get('image_url'):
                                                st.image(item['image_url'], use_container_width=True)
                                        with col2:
                                            st.write(f"**Category:** {item.get('category', 'N/A')}")
                                            st.write(f"**Price:** ${item.get('price', 'N/A')}")
                                            st.write(f"**Description:** {item.get('description', 'N/A')}")
                        else:
                            st.error("Image search failed")
    with col1:
        st.subheader("Server Status")
        # Button moved outside the main flow
        pass
    
    with col2:
        st.subheader("Authentication Status")
        if st.session_state.access_token:
            st.success("✅ Authenticated")
            st.write(f"**Username:** {st.session_state.user_info.get('username', 'N/A')}")
            st.write(f"**Email:** {st.session_state.user_info.get('email', 'N/A')}")
        else:
            st.warning("⚠️ Not authenticated")
    
    st.subheader("Quick API Test")
    # Button moved outside the main flow
    pass

# Server Status and API Test buttons (moved outside main app flow)
if st.button("Check Server Status"):
    try:
        response = requests.get(f"{API_BASE_URL}/")
        if response.status_code == 200:
            st.success("✅ Server is running")
            data = response.json()
            st.write(f"**Message:** {data.get('message', 'N/A')}")
        else:
            st.error("❌ Server is not responding properly")
    except Exception as e:
        st.error(f"❌ Cannot connect to server: {str(e)}")

if st.button("Test All Endpoints"):
    results = []
    
    # Test root endpoint
    try:
        response = requests.get(f"{API_BASE_URL}/")
        results.append(("Root Endpoint", response.status_code == 200))
    except:
        results.append(("Root Endpoint", False))
    
    # Test auth endpoints
    try:
        response = requests.post(f"{API_BASE_URL}/auth/login", json={"username": "test", "password": "test"})
        results.append(("Login Endpoint", response.status_code in [200, 401]))
    except:
        results.append(("Login Endpoint", False))
    
    # Test jewelry search (without auth)
    try:
        response = requests.post(f"{API_BASE_URL}/products/search", data={"query": "test"})
        results.append(("Jewelry Search", response.status_code in [200, 401]))
    except:
        results.append(("Jewelry Search", False))
    
    # Display results
    for endpoint, success in results:
        if success:
            st.success(f"✅ {endpoint}: Working")
        else:
            st.error(f"❌ {endpoint}: Failed")

# Footer
st.markdown("---")
st.markdown("Built with ❤️ using Streamlit and FastAPI")