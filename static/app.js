// Jewelry Store API Client
class JewelryAPI {
    constructor(baseURL = 'http://localhost:8000') {
        this.baseURL = baseURL;
        this.accessToken = null;
        this.userInfo = null;
        this.loadAuthData();
    }

    // Authentication methods
    async login(username, password) {
        try {
            // Send as JSON since backend expects JSON with username field
            const loginData = {
                username: username,
                password: password
            };

            const response = await fetch(`${this.baseURL}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(loginData)
            });

            const data = await response.json();

            if (response.ok) {
                this.accessToken = data.access_token;
                this.userInfo = { username, email: data.email || username };
                this.saveAuthData();
                return { success: true, data };
            } else {
                return { success: false, error: data.detail || 'Login failed' };
            }
        } catch (error) {
            return { success: false, error: 'Connection error. Please check if the server is running.' };
        }
    }

    async register(userData) {
        try {
            const response = await fetch(`${this.baseURL}/auth/signup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(userData)
            });

            const data = await response.json();

            if (response.ok) {
                return { success: true, data };
            } else {
                return { success: false, error: data.detail || 'Registration failed' };
            }
        } catch (error) {
            return { success: false, error: 'Connection error. Please check if the server is running.' };
        }
    }

    logout() {
        this.accessToken = null;
        this.userInfo = null;
        this.clearAuthData();
    }

    // Search methods
    async searchProducts(query, category = null, limit = 10) {
        return this.searchJewelry({ query, category, limit });
    }

    async searchJewelry(searchParams) {
        if (!this.accessToken) {
            return { success: false, error: 'Please login first' };
        }

        try {
            // First, create or get a session
            console.log('Creating new chat session...');
            const sessionResponse = await fetch(`${this.baseURL}/chat/sessions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.accessToken}`
                }
            });

            console.log('Session creation response status:', sessionResponse.status);
            
            if (!sessionResponse.ok) {
                const errorData = await sessionResponse.json();
                console.error('Session creation failed:', errorData);
                throw new Error(errorData.detail || 'Failed to create chat session');
            }

            const { session_id } = await sessionResponse.json();

            // Now use the chat query endpoint with the session ID
            console.log('Sending query:', searchParams.query || '');
            console.log('Current session ID:', session_id);
            console.log('Auth token available:', !!this.accessToken);
            
            const response = await fetch(`${this.baseURL}/chat/query`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.accessToken}`
                },
                body: JSON.stringify({
                    query: searchParams.query || '',
                    session_id: session_id,
                    limit: searchParams.limit || 10,
                    category: searchParams.category || null
                })
            });

            console.log('Response status:', response.status);
            const data = await response.json();
            console.log('Query response:', data);

            if (response.ok) {
                // Check if the response contains products or similar_products
                let products = data.products || data.similar_products || [];
                
                // Remove duplicate products based on product ID or name
                const uniqueProducts = [];
                const seenIds = new Set();
                
                products.forEach(product => {
                    const idKey = product.id || product.name; // Use ID if available, otherwise name
                    if (!seenIds.has(idKey)) {
                        seenIds.add(idKey);
                        uniqueProducts.push(product);
                    }
                });
                
                return { 
                    success: true, 
                    data: {
                        results: uniqueProducts,
                        count: uniqueProducts.length
                    } 
                };
            } else {
                return { 
                    success: false, 
                    error: data.detail || 'Search failed' 
                };
            }
        } catch (error) {
            console.error('Search error:', error);
            return { 
                success: false, 
                error: error.message || 'Failed to perform search' 
            };
        }
    }

    async uploadProducts(productsData) {
        if (!this.accessToken) {
            return { success: false, error: 'Please login first' };
        }

        try {
            // Extract the products array if it's wrapped in an object
            let productsArray;
            if (productsData && productsData.products && Array.isArray(productsData.products)) {
                productsArray = productsData.products;
            } else if (Array.isArray(productsData)) {
                productsArray = productsData;
            } else {
                return { success: false, error: 'Invalid products data format' };
            }

            // Create a JSON file for upload
            const jsonContent = JSON.stringify(productsArray, null, 2);
            const blob = new Blob([jsonContent], { type: 'application/json' });
            const file = new File([blob], 'products.json', { type: 'application/json' });
            
            const formData = new FormData();
            formData.append('file', file);

            const response = await fetch(`${this.baseURL}/products/upload`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.accessToken}`
                    // Don't set Content-Type for FormData, let browser set it
                },
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                return { success: true, data };
            } else {
                return { success: false, error: data.detail || 'Upload failed' };
            }
        } catch (error) {
            return { success: false, error: 'Connection error. Please check if the server is running.' };
        }
    }

    async searchByImage(imageData, searchParams = {}) {
        if (!this.accessToken) {
            return { success: false, error: 'Please login first' };
        }

        try {
            // First, create or get a session
            const sessionResponse = await fetch(`${this.baseURL}/chat/sessions`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.accessToken}`
                }
            });

            if (!sessionResponse.ok) {
                const error = await sessionResponse.json();
                throw new Error(error.detail || 'Failed to create chat session');
            }

            const { session_id } = await sessionResponse.json();

            // Handle different image input types
            let imageFile;
            
            if (imageData instanceof File) {
                // If it's a File object (from file input), use it directly
                imageFile = imageData;
            } else if (imageData.startsWith('data:image')) {
                // If it's base64 data URI, convert to blob
                const base64Data = imageData.split(',')[1];
                const byteCharacters = atob(base64Data);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                
                // Determine MIME type
                const mimeType = imageData.split(',')[0].split(':')[1].split(';')[0];
                const imageBlob = new Blob([byteArray], { type: mimeType });
                
                // Convert blob to File
                imageFile = new File([imageBlob], 'search_image.jpg', { type: mimeType });
            } else {
                // Assume it's base64 without data URI prefix, convert to blob
                const byteCharacters = atob(imageData);
                const byteNumbers = new Array(byteCharacters.length);
                for (let i = 0; i < byteCharacters.length; i++) {
                    byteNumbers[i] = byteCharacters.charCodeAt(i);
                }
                const byteArray = new Uint8Array(byteNumbers);
                const imageBlob = new Blob([byteArray], { type: 'image/jpeg' });
                
                // Convert blob to File
                imageFile = new File([imageBlob], 'search_image.jpg', { type: 'image/jpeg' });
            }

            // Create FormData for image upload
            const formData = new FormData();
            formData.append('session_id', session_id);
            formData.append('query', searchParams.query || '');
            formData.append('image', imageFile);
            if (searchParams.category) {
                formData.append('category', searchParams.category);
            }

            // Use the correct image search endpoint
            const response = await fetch(`${this.baseURL}/chat/image-query`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.accessToken}`
                    // Don't set Content-Type for FormData, let browser set it
                },
                body: formData
            });

            const data = await response.json();

            if (response.ok) {
                // Check if the response contains products
                const products = data.products || [];
                
                return { 
                    success: true, 
                    data: {
                        results: products,
                        count: products.length
                    } 
                };
            } else {
                return { success: false, error: data.detail || 'Image search failed' };
            }
        } catch (error) {
            console.error('Image search error:', error);
            return { success: false, error: error.message || 'Failed to perform image search' };
        }
    }

    // Utility methods
    saveAuthData() {
        if (this.accessToken && this.userInfo) {
            localStorage.setItem('access_token', this.accessToken);
            localStorage.setItem('user_info', JSON.stringify(this.userInfo));
        }
    }

    loadAuthData() {
        const token = localStorage.getItem('access_token');
        const user = localStorage.getItem('user_info');
        
        if (token && user) {
            this.accessToken = token;
            this.userInfo = JSON.parse(user);
        }
    }

    clearAuthData() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_info');
    }

    isAuthenticated() {
        return !!this.accessToken;
    }

    getUserInfo() {
        return this.userInfo;
    }
}

// UI Controller
class UIController {
    constructor(api) {
        this.api = api;
        this.currentSearchMode = 'text';
        this.uploadedImage = null;
        this.jsonData = null;
        this.jsonFile = null;
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.updateUI();
        this.setupDragAndDrop();
        // Initialize upload section
        this.setUploadMode('json');
        // Setup periodic authentication check
        this.setupAuthCheck();
        // Setup global error handler for 401 responses
        this.setupGlobalErrorHandler();
    }

    setupAuthCheck() {
        // Check authentication status every 30 seconds
        setInterval(() => {
            if (this.api.isAuthenticated() && !this.api.getUserInfo()) {
                // Token exists but user info is missing, might be expired
                this.api.logout();
                this.updateUI();
                this.showStatus('Session expired. Please login again.', 'error');
            }
        }, 30000);
    }

    setupGlobalErrorHandler() {
        // Intercept fetch responses to catch 401 errors globally
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            if (response.status === 401) {
                // Auto logout on 401 response
                this.api.logout();
                this.updateUI();
                this.showStatus('Session expired. Please login again.', 'error');
            }
            return response;
        };
    }

    setupEventListeners() {
        // Tab switching
        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', (e) => this.switchTab(e.target.textContent.toLowerCase(), e));
        });

        // Search mode switching
        document.querySelectorAll('.mode-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.setSearchMode(e.target.textContent.toLowerCase().split(' ')[0], e));
        });

        // Quick filter buttons
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.quickSearch(e.target.textContent.toLowerCase().split(' ')[1]));
        });

        // Form submissions - using onclick handlers instead since they're defined in HTML
        // No need to add event listeners for login/register/signup/logout buttons
        
        // Search button is also handled via onclick
        
        // Enter key handling for search input
        const textQuery = document.getElementById('textQuery');
        if (textQuery) {
            textQuery.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && this.currentSearchMode === 'text') {
                    this.performSearch();
                }
            });
        }

        // Image upload
        const imageInput = document.getElementById('imageInput');
        if (imageInput) {
            imageInput.addEventListener('change', (e) => this.handleImageUpload(e));
        }

        // JSON file upload
        const jsonFileInput = document.getElementById('jsonFileInput');
        if (jsonFileInput) {
            jsonFileInput.addEventListener('change', (e) => this.handleJSONUpload(e));
        }

        // Manual product form - no form element exists, handled by button onclick

        // Prevent upload button clicks if not authenticated
        this.setupUploadButtonProtection();
    }

    setupUploadButtonProtection() {
        // Add authentication check to upload buttons
        const uploadJsonBtn = document.querySelector('#jsonUpload .btn-success');
        if (uploadJsonBtn) {
            uploadJsonBtn.addEventListener('click', (e) => {
                if (!this.api.isAuthenticated()) {
                    e.preventDefault();
                    this.showStatus('Please login first to upload products', 'error');
                    return;
                }
            });
        }

        const uploadManualBtn = document.querySelector('#manualUpload .btn-success');
        if (uploadManualBtn) {
            uploadManualBtn.addEventListener('click', (e) => {
                if (!this.api.isAuthenticated()) {
                    e.preventDefault();
                    this.showStatus('Please login first to add products', 'error');
                    return;
                }
            });
        }
    }

    setupDragAndDrop() {
        const uploadArea = document.querySelector('.file-upload');
        if (uploadArea) {
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadArea.classList.add('dragover');
            });

            uploadArea.addEventListener('dragleave', () => {
                uploadArea.classList.remove('dragover');
            });

            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadArea.classList.remove('dragover');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    this.handleImageFile(files[0]);
                }
            });
        }
    }

    // UI Update methods
    updateUI() {
        const isAuthenticated = this.api.isAuthenticated();
        const userInfo = this.api.getUserInfo();

        // Update auth section visibility
        const authSection = document.getElementById('authSection');
        const userInfoSection = document.getElementById('userInfo');
        const searchSection = document.getElementById('searchSection');
        const uploadSection = document.getElementById('uploadSection');
        const uploadLoginRequired = document.getElementById('uploadLoginRequired');
        const searchLoginRequired = document.getElementById('loginRequired');
        const searchContent = document.getElementById('searchContent');
        const uploadContent = document.getElementById('uploadContent');
        const historyContent = document.getElementById('historyContent');
        const mainTabs = document.getElementById('mainTabs');
        const resultsSection = document.getElementById('resultsSection');

        if (isAuthenticated) {
            authSection.style.display = 'none';
            userInfoSection.classList.add('active');
            mainTabs.style.display = 'flex';
            
            // Show content sections and hide login required messages
            if (searchLoginRequired) searchLoginRequired.style.display = 'none';
            if (searchContent) searchContent.style.display = 'block';
            if (uploadLoginRequired) uploadLoginRequired.style.display = 'none';
            if (uploadContent) uploadContent.style.display = 'block';
            if (historyContent) historyContent.style.display = 'block';
            
            if (userInfo) {
                const userEmailElement = document.getElementById('userEmail');
                if (userEmailElement) {
                    userEmailElement.textContent = userInfo.email || userInfo.username || 'User';
                }
            }
        } else {
            authSection.style.display = 'block';
            userInfoSection.classList.remove('active');
            mainTabs.style.display = 'none';
            
            // Hide content sections and show login required messages
            if (searchLoginRequired) searchLoginRequired.style.display = 'block';
            if (searchContent) searchContent.style.display = 'none';
            if (uploadLoginRequired) uploadLoginRequired.style.display = 'block';
            if (uploadContent) uploadContent.style.display = 'none';
            if (historyContent) historyContent.style.display = 'none';
            
            if (resultsSection) resultsSection.style.display = 'none';
        }
    }

    switchTab(tab, event) {
        // Update tab buttons
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        if (event && event.target) {
            event.target.classList.add('active');
        }

        // Show/hide forms
        if (tab === 'login') {
            document.getElementById('loginForm').style.display = 'block';
        document.getElementById('signupForm').style.display = 'none';
        } else {
            document.getElementById('loginForm').style.display = 'none';
        document.getElementById('signupForm').style.display = 'block';
        }
    }

    setSearchMode(mode, event) {
        this.currentSearchMode = mode;
        
        // Update button states
        document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.remove('active'));
        if (event && event.target) {
            event.target.classList.add('active');
        }

        // Show/hide input fields
        const textSearch = document.getElementById('textSearch');
        const imageSearch = document.getElementById('imageSearch');
        const combinedSearch = document.getElementById('combinedSearch');
        const similaritySearch = document.getElementById('similaritySearch');

        // Hide all search modes first
        if (textSearch) textSearch.style.display = 'none';
        if (imageSearch) imageSearch.style.display = 'none';
        if (combinedSearch) combinedSearch.style.display = 'none';
        if (similaritySearch) similaritySearch.style.display = 'none';

        // Show the selected search mode
        if (mode === 'text') {
            if (textSearch) textSearch.style.display = 'block';
        } else if (mode === 'image') {
            if (imageSearch) imageSearch.style.display = 'block';
        } else if (mode === 'combined') {
            if (combinedSearch) combinedSearch.style.display = 'block';
        } else if (mode === 'similarity') {
            if (similaritySearch) similaritySearch.style.display = 'block';
        }
    }

    setUploadMode(mode, event = null) {
        // Update button states
        document.querySelectorAll('#uploadSection .section-tab').forEach(btn => btn.classList.remove('active'));
        if (event && event.target) {
            event.target.classList.add('active');
        } else {
            // Set default active button
            const defaultBtn = mode === 'json' ? 
                document.querySelector('#uploadSection .section-tab:first-child') :
                document.querySelector('#uploadSection .section-tab:last-child');
            if (defaultBtn) defaultBtn.classList.add('active');
        }

        // Show/hide upload sections
        const jsonUpload = document.getElementById('jsonUpload');
        const manualUpload = document.getElementById('manualUpload');

        if (jsonUpload && manualUpload) {
            if (mode === 'json') {
                jsonUpload.style.display = 'block';
                manualUpload.style.display = 'none';
            } else {
                jsonUpload.style.display = 'none';
                manualUpload.style.display = 'block';
            }
        }
    }

    async uploadJsonProducts() {
        if (!this.api.isAuthenticated()) {
            this.showStatus('Please login first to upload products', 'error');
            return;
        }
        
        if (!this.jsonData) {
            this.showStatus('Please select a JSON file first', 'error');
            return;
        }
        
        this.showLoading('Uploading products...');
        
        try {
            const result = await this.api.uploadProducts({ products: this.jsonData });
            
            if (result.success) {
                this.showStatus(`Successfully uploaded ${result.details?.inserted_count || 0} products!`, 'success');
                // Clear the form
                this.jsonData = null;
                this.jsonFile = null;
                const jsonFileInput = document.getElementById('jsonFileInput');
                if (jsonFileInput) {
                    jsonFileInput.value = '';
                }
            } else {
                this.showStatus('Upload failed: ' + result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Upload error: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    addManualProduct() {
        this.handleManualProductSubmit();
    }

    // Authentication methods
    async login() {
        const username = document.getElementById('loginEmail').value;
        const password = document.getElementById('loginPassword').value;

        if (!username || !password) {
            this.showStatus('Please enter both username and password', 'error');
            return;
        }

        const result = await this.api.login(username, password);
        
        if (result.success) {
            this.showStatus('Login successful!', 'success');
            this.updateUI();
        } else {
            this.showStatus(result.error, 'error');
        }
    }

    async register() {
        const email = document.getElementById('signupEmail').value;
        const password = document.getElementById('signupPassword').value;
        const confirmPassword = document.getElementById('confirmPassword').value;

        if (!email || !password) {
            this.showStatus('Please fill in all required fields', 'error');
            return;
        }

        if (password !== confirmPassword) {
            this.showStatus('Passwords do not match', 'error');
            return;
        }

        const userData = {
            username: email,  // Use email as username
            email: email,
            password: password,
            full_name: email  // Use email as full_name for now
        };

        const result = await this.api.register(userData);
        
        if (result.success) {
            this.showStatus('Registration successful! Please login.', 'success');
            // Switch to login tab
            const loginTab = document.querySelector('.tab');
            if (loginTab) {
                loginTab.click();
            }
        } else {
            this.showStatus(result.error, 'error');
        }
    }

    logout() {
        this.api.logout();
        this.showStatus('Logged out successfully', 'info');
        this.updateUI();
    }

    // Search methods
    quickSearch(category) {
        // Map frontend categories to backend categories
        const categoryMapping = {
            'electronics': 'Smartphones',  // Map electronics to Smartphones as primary electronics category
            'clothing': 'clothing',        // Map clothing to actual clothing category
            'home': 'Smart Speakers',      // Map home to Smart Speakers as smart home devices
            'books': 'Tablets',            // Map books to Tablets as reading devices
            'sports': 'Smartwatches'       // Map sports to Smartwatches as fitness tracking
        };
        
        const backendCategory = categoryMapping[category] || category;
        
        // Set the search query to a generic term and use the backend category as the category filter
        const searchQuery = document.getElementById('searchQuery');
        if (searchQuery) {
            searchQuery.value = 'products';
        }
        
        // Perform search with the mapped category
        this.performSearchWithCategory(backendCategory);
    }
    
    async performSearchWithCategory(category) {
        if (!this.api.isAuthenticated()) {
            this.showStatus('Please login first', 'error');
            return;
        }

        const limit = parseInt(document.getElementById('limit')?.value) || 10;

        this.showLoading(true);

        let searchParams = {
            query: 'products',  // Generic query
            category: category,  // Use the specific category
            limit: limit
        };

        try {
            const result = await this.api.searchJewelry(searchParams);
            
            if (result.success) {
                this.displayResults(result.data.results || result.data);
            } else {
                this.showStatus(result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Search failed. Please try again.', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    handleImageUpload(event) {
        const file = event.target.files[0];
        if (file) {
            this.handleImageFile(file);
        }
    }

    async handleJSONUpload(event) {
        const file = event.target.files[0];
        if (!file) return;

        this.jsonFile = file;
        this.showLoading('Processing JSON file...');
        
        try {
            const fileContent = await this.readFileAsText(file);
            this.jsonData = JSON.parse(fileContent);
            
            // Show preview
            const jsonPreview = document.getElementById('jsonPreview');
            const jsonContent = document.getElementById('jsonContent');
            
            if (jsonPreview && jsonContent) {
                jsonContent.textContent = JSON.stringify(this.jsonData, null, 2);
                jsonPreview.style.display = 'block';
            }
            
            this.showStatus(`JSON file loaded: ${Array.isArray(this.jsonData) ? this.jsonData.length : 'Unknown'} products found`, 'success');
        } catch (error) {
            this.showStatus('Error processing JSON file: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async handleManualProductSubmit() {
        if (!this.api.isAuthenticated()) {
            this.showStatus('Please login first to add products', 'error');
            return;
        }
        
        // Get values directly from form fields since they don't have name attributes
        const productName = document.getElementById('productName');
        const productCategory = document.getElementById('productCategory');
        const productDescription = document.getElementById('productDescription');
        const productPrice = document.getElementById('productPrice');
        const productImageUrl = document.getElementById('productImageUrl');

        if (!productName || !productCategory || !productDescription || !productPrice) {
            this.showStatus('Required form fields not found', 'error');
            return;
        }

        const product = {
            name: productName.value,
            category: productCategory.value,
            description: productDescription.value,
            price: parseFloat(productPrice.value) || 0,
            image_url: productImageUrl ? productImageUrl.value : ''
        };

        this.showLoading('Adding product...');
        
        try {
            const result = await this.api.uploadProducts({ products: [product] });
            
            if (result.success) {
                this.showStatus('Product added successfully!', 'success');
                // Clear form fields
                productName.value = '';
                productCategory.value = '';
                productDescription.value = '';
                productPrice.value = '';
                if (productImageUrl) productImageUrl.value = '';
            } else {
                this.showStatus('Failed to add product: ' + result.error, 'error');
            }
        } catch (error) {
            this.showStatus('Error adding product: ' + error.message, 'error');
        } finally {
            this.showLoading(false);
        }
    }

    async readFileAsText(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = e => resolve(e.target.result);
            reader.onerror = reject;
            reader.readAsText(file);
        });
    }

    handleImageFile(file) {
        const reader = new FileReader();
        reader.onload = (e) => {
            const uploadText = document.getElementById('uploadText');
            const imagePreview = document.getElementById('imagePreview');
            if (uploadText && imagePreview) {
                uploadText.style.display = 'none';
                imagePreview.src = e.target.result;
                imagePreview.style.display = 'block';
            }
            this.uploadedImage = e.target.result;
        };
        reader.readAsDataURL(file);
    }

    async performSearch() {
        if (!this.api.isAuthenticated()) {
            this.showStatus('Please login first', 'error');
            return;
        }

        this.showLoading(true);

        try {
            let result;
            
            if (this.currentSearchMode === 'text') {
                const textQuery = document.getElementById('textQuery');
                if (!textQuery || !textQuery.value.trim()) {
                    this.showStatus('Please enter a search query', 'error');
                    this.showLoading(false);
                    return;
                }
                result = await this.api.searchJewelry({
                    query: textQuery.value,
                    limit: 10
                });
            } else if (this.currentSearchMode === 'image') {
                if (!this.uploadedImage) {
                    this.showStatus('Please upload an image first', 'error');
                    this.showLoading(false);
                    return;
                }
                result = await this.api.searchByImage(this.uploadedImage, {
                    limit: 10
                });
            } else if (this.currentSearchMode === 'combined') {
                const combinedTextQuery = document.getElementById('combinedTextQuery');
                const combinedImageInput = document.getElementById('combinedImageInput');
                
                if (!combinedTextQuery || !combinedTextQuery.value.trim()) {
                    this.showStatus('Please enter a search query', 'error');
                    this.showLoading(false);
                    return;
                }
                
                if (combinedImageInput && combinedImageInput.files[0]) {
                    // Combined text + image search
                    const imageFile = combinedImageInput.files[0];
                    const reader = new FileReader();
                    reader.onload = async (e) => {
                        try {
                            result = await this.api.searchByImage(e.target.result, {
                                query: combinedTextQuery.value,
                                limit: 10
                            });
                            if (result && result.success) {
                                this.displayResults(result.data.results || result.data);
                            } else {
                                this.showStatus(result?.error || 'Search failed', 'error');
                            }
                        } catch (error) {
                            this.showStatus('Search failed. Please try again.', 'error');
                        } finally {
                            this.showLoading(false);
                        }
                    };
                    reader.readAsDataURL(imageFile);
                    return; // Early return to avoid double execution
                } else {
                    // Text-only search
                    result = await this.api.searchJewelry({
                        query: combinedTextQuery.value,
                        limit: 10
                    });
                }
            } else if (this.currentSearchMode === 'similarity') {
                const similarityQuery = document.getElementById('similarityQuery');
                const similarityImageInput = document.getElementById('similarityImageInput');
                const similarityLimit = document.getElementById('similarityLimit');
                
                if (!similarityQuery || !similarityQuery.value.trim()) {
                    this.showStatus('Please enter a similarity description', 'error');
                    this.showLoading(false);
                    return;
                }
                
                const limit = similarityLimit ? parseInt(similarityLimit.value) : 10;
                
                if (similarityImageInput && similarityImageInput.files[0]) {
                    // Similarity search with image
                    const imageFile = similarityImageInput.files[0];
                    const reader = new FileReader();
                    reader.onload = async (e) => {
                        try {
                            result = await this.api.searchByImage(e.target.result, {
                                query: similarityQuery.value,
                                limit: limit
                            });
                            if (result && result.success) {
                                this.displayResults(result.data.results || result.data);
                            } else {
                                this.showStatus(result?.error || 'Search failed', 'error');
                            }
                        } catch (error) {
                            this.showStatus('Search failed. Please try again.', 'error');
                        } finally {
                            this.showLoading(false);
                        }
                    };
                    reader.readAsDataURL(imageFile);
                    return; // Early return to avoid double execution
                } else {
                    // Text-only similarity search
                    result = await this.api.searchJewelry({
                        query: similarityQuery.value,
                        limit: limit
                    });
                }
            }

            if (result && result.success) {
                console.log('Search successful, calling displayResults with:', result.data.results || result.data);
                console.log('result.data:', result.data);
                console.log('result.data.results:', result.data?.results);
                this.displayResults(result.data.results || result.data);
            } else {
                console.log('Search failed:', result);
                this.showStatus(result?.error || 'Search failed', 'error');
            }
        } catch (error) {
            this.showStatus('Search failed. Please try again.', 'error');
        } finally {
            this.showLoading(false);
        }
    }

    handleSearchResult(result) {
        console.log('handleSearchResult called with:', result);
        if (result && result.products) {
            const results = result.products;
            console.log('Results to display:', results);
            this.displayResults(results);
        } else if (result && result.success) {
            const results = result.data?.results || result.data;
            console.log('Results to display:', results);
            this.displayResults(results);
        } else {
            this.showStatus(result?.error || 'Search failed', 'error');
        }
    }

    displayResults(results) {
        const resultsContainer = document.getElementById('searchResults');
        const resultsSection = document.getElementById('resultsSection');

        console.log('=== DISPLAY RESULTS START ===');
        console.log('displayResults called with:', results);
        console.log('Results container:', resultsContainer);
        console.log('Results section:', resultsSection);
        console.log('Results type:', typeof results);
        console.log('Is Array?', Array.isArray(results));
        console.log('Results length:', results ? results.length : 'N/A');

        if (!resultsContainer || !resultsSection) {
            console.error('Results container or section not found');
            return;
        }

        // Ensure results is an array
        if (!Array.isArray(results)) {
            console.log('Results is not an array, converting...');
            if (results && typeof results === 'object') {
                // If it's an object with a results property, use that
                results = results.results || results.data || [results];
            } else {
                results = [];
            }
        }

        console.log('After conversion - Results:', results);
        console.log('After conversion - Is Array?', Array.isArray(results));
        console.log('After conversion - Length:', results ? results.length : 'N/A');

        if (!results || results.length === 0) {
            console.log('No results to display');
            resultsContainer.innerHTML = '<p style="text-align: center; color: #666;">No results found. Try adjusting your search criteria.</p>';
            resultsSection.style.display = 'block';
            console.log('=== DISPLAY RESULTS END - NO RESULTS ===');
            return;
        }

        console.log('Processing results:', results);

        // Create products grid container
        const productsGrid = document.createElement('div');
        productsGrid.className = 'products-grid';

        results.forEach((item, index) => {
            console.log(`Processing item ${index}:`, item);
            console.log(`Item name: ${item.name}`);
            console.log(`Item price: ${item.price}`);
            console.log(`Item category: ${item.category}`);
            
            // Determine the image source - only use real images, never placeholder services
            let imageSrc = '';
            const svgPlaceholder = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDMwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMDAiIGhlaWdodD0iMjAwIiBmaWxsPSIjRjBGMEYwIi8+Cjx0ZXh0IHg9IjE1MCIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM2NjY2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5ObyBJbWFnZTwvdGV4dD4KPC9zdmc+';
            
            // Check image_url first (most reliable source)
            if (item.image_url && item.image_url.trim() && !item.image_url.includes('placeholder.com') && !item.image_url.includes('example.com')) {
                if (item.image_url.match(/^[A-Za-z0-9+/]{20,}/)) {
                    // It's base64 data, create a data URI
                    imageSrc = `data:image/jpeg;base64,${item.image_url}`;
                } else if (item.image_url.startsWith('data:') || item.image_url.startsWith('http')) {
                    // It's already a data URI or external URL (but not placeholder)
                    imageSrc = item.image_url;
                } else {
                    // Skip invalid URLs
                    imageSrc = svgPlaceholder;
                }
            } else if (item.image_path && item.image_path.trim() && !item.image_path.includes('placeholder.com') && !item.image_path.includes('example.com')) {
                imageSrc = item.image_path;
            } else if (item.image && item.image.trim() && !item.image.includes('placeholder.com') && !item.image.includes('example.com')) {
                if (item.image.startsWith('data:') || item.image.startsWith('http')) {
                    imageSrc = item.image;
                } else {
                    // Assume it's base64 data
                    imageSrc = `data:image/jpeg;base64,${item.image}`;
                }
            } else {
                // Always use inline SVG placeholder for missing images or blocked URLs
                imageSrc = svgPlaceholder;
            }
            
            const productCard = document.createElement('div');
            productCard.className = 'product-card';
            productCard.innerHTML = `
                <img src="${imageSrc}" 
                     alt="${item.name}"
                     class="product-image"
                     onerror="this.onerror=null; this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzAwIiBoZWlnaHQ9IjIwMCIgdmlld0JveD0iMCAwIDMwMCAyMDAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIzMDAiIGhlaWdodD0iMjAwIiBmaWxsPSIjRjBGMEYwIi8+Cjx0ZXh0IHg9IjE1MCIgeT0iMTAwIiBmb250LWZhbWlseT0iQXJpYWwsIHNhbnMtc2VyaWYiIGZvbnQtc2l6ZT0iMTQiIGZpbGw9IiM2NjY2NjYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5ObyBJbWFnZTwvdGV4dD4KPC9zdmc+';" style="width: 100%; height: 200px; object-fit: cover;">
                <div class="product-info">
                    <h3 class="product-name">${item.name}</h3>
                    <p class="product-price">$${item.price || 'N/A'}</p>
                    <p class="product-category">${item.category}</p>
                    <p class="product-description">${item.description && item.description.trim() ? item.description : 'No description available'}</p>
                    <p class="similarity-score">Similarity: ${item.score ? `${(item.score * 100).toFixed(1)}%` : 'N/A'}</p>
                </div>
            `;
            productsGrid.appendChild(productCard);
        });

        // Clear and populate results container
        resultsContainer.innerHTML = '';
        resultsContainer.appendChild(productsGrid);

        resultsSection.style.display = 'block';
        
        console.log('Results section is now visible');
        console.log('Number of product cards created:', productsGrid.children.length);
        
        // Scroll to results
        resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
        
        console.log('=== DISPLAY RESULTS COMPLETED SUCCESSFULLY ===');
    }

    // Utility methods
    showStatus(message, type) {
        const statusElement = document.getElementById('statusMessage');
        if (statusElement) {
            statusElement.textContent = message;
            statusElement.className = `status ${type}`;
            statusElement.style.display = 'block';
            
            setTimeout(() => {
                statusElement.style.display = 'none';
            }, 5000);
        }
    }

    showLoading(show) {
        const loadingElement = document.getElementById('loadingIndicator');
        const searchBtn = document.getElementById('searchBtn');
        
        if (loadingElement && searchBtn) {
            if (show) {
                loadingElement.style.display = 'block';
                searchBtn.disabled = true;
            } else {
                loadingElement.style.display = 'none';
                searchBtn.disabled = false;
            }
        }
    }
}

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    const api = new JewelryAPI();
    const ui = new UIController(api);
    
    // Make API globally available for debugging
    window.jewelryAPI = api;
    window.jewelryUI = ui;
});