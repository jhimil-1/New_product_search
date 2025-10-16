/**
 * Jewellery Chatbot Widget
 * A customizable chatbot widget for jewellery e-commerce websites
 * 
 * Usage:
 * 1. Include this script in your HTML: <script src="jewellery-chatbot-widget.js"></script>
 * 2. Initialize the widget: JewelleryChatbot.init({ apiUrl: 'http://localhost:8000' });
 * 
 * Configuration Options:
 * - apiUrl: Your API base URL (required)
 * - username: Pre-configured username (optional)
 * - password: Pre-configured password (optional)
 * - position: Widget position ('bottom-right', 'bottom-left', 'top-right', 'top-left')
 * - theme: Color theme ('blue', 'purple', 'green', 'custom')
 * - customColors: Custom color scheme (if theme is 'custom')
 */

(function(window) {
    'use strict';

    class JewelleryChatbot {
        constructor() {
            this.config = {
                apiUrl: '',
                position: 'bottom-right',
                theme: 'blue',
                customColors: {},
                autoOpen: false,
                welcomeMessage: '✨ Welcome to our Jewellery Store! ✨\n\nI\'m your personal jewellery assistant. I can help you find the perfect piece! 💍✨\n\nTry asking me things like:\n• "Show me gold necklaces under $500"\n• "I\'m looking for diamond earrings"\n• "What are your best selling rings?"\n• "Help me choose a gift for anniversary"',
                placeholderText: 'Ask about rings, necklaces, earrings, or gifts...',
                maxFileSize: 5 * 1024 * 1024, // 5MB
                allowedFileTypes: ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
            };
            
            this.state = {
                isOpen: false,
                isAuthenticated: false,
                accessToken: null,
                sessionId: null,
                userId: null,
                messages: [],
                isTyping: false,
                currentUser: null
            };
            
            this.elements = {};
            this.apiEndpoints = {
                signup: '/auth/signup',
                login: '/auth/login',
                createSession: '/chat/sessions',
                chatQuery: '/chat/query',
                chatHistory: '/chat/history',
                health: '/health'
            };
        }

        /**
         * Initialize the chatbot widget
         * @param {Object} config - Configuration options
         */
        init(config) {
            // Merge configuration
            this.config = { ...this.config, ...config };
            
            // Validate required configuration
            if (!this.config.apiUrl) {
                console.error('JewelleryChatbot: apiUrl is required');
                return;
            }
            
            // Create widget UI
            this.createWidget();
            
            // Set up event listeners
            this.setupEventListeners();
            
            // Check API health
            this.checkAPIHealth();
            
            // Auto-open if configured
            if (this.config.autoOpen) {
                this.toggleChat();
            }
            
            console.log('JewelleryChatbot: Widget initialized successfully');
        }

        /**
         * Create the widget UI elements
         */
        createWidget() {
            // Main widget container
            const widgetContainer = document.createElement('div');
            widgetContainer.id = 'jewellery-chatbot-widget';
            widgetContainer.className = 'jewellery-chatbot-widget';
            
            // Chat button
            const chatButton = document.createElement('div');
            chatButton.className = 'jewellery-chatbot-button';
            chatButton.innerHTML = `
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                    <path d="M20 2H4C2.9 2 2 2.9 2 4V22L6 18H20C21.1 18 22 17.1 22 16V4C22 2.9 21.1 2 20 2Z" fill="currentColor"/>
                </svg>
            `;
            
            // Chat window
            const chatWindow = document.createElement('div');
            chatWindow.className = 'jewellery-chatbot-window';
            chatWindow.innerHTML = `
                <div class="jewellery-chatbot-header">
                    <div class="jewellery-chatbot-title">
                        <span class="jewellery-chatbot-icon">💎</span>
                        <span>Jewellery Assistant</span>
                    </div>
                    <div class="jewellery-chatbot-controls">
                        <button class="jewellery-chatbot-minimize" title="Minimize">−</button>
                        <button class="jewellery-chatbot-close" title="Close">×</button>
                    </div>
                </div>
                
                <div class="jewellery-chatbot-messages"></div>
                
                <div class="jewellery-chatbot-input-area">
                    <div class="jewellery-chatbot-file-upload" style="display: none;">
                        <input type="file" accept="image/*" class="jewellery-chatbot-file-input">
                        <div class="jewellery-chatbot-file-preview"></div>
                    </div>
                    
                    <div class="jewellery-chatbot-input-container">
                        <button class="jewellery-chatbot-attach" title="Attach Image">📎</button>
                        <input type="text" class="jewellery-chatbot-input" placeholder="${this.config.placeholderText}">
                        <button class="jewellery-chatbot-send" title="Send">➤</button>
                    </div>
                </div>
                
                <div class="jewellery-chatbot-auth" style="display: none;">
                    <div class="jewellery-chatbot-auth-form">
                        <h3>Sign In</h3>
                        <input type="text" class="jewellery-chatbot-username" placeholder="Username or Email">
                        <input type="password" class="jewellery-chatbot-password" placeholder="Password">
                        <div class="jewellery-chatbot-auth-buttons">
                            <button class="jewellery-chatbot-login">Login</button>
                            <button class="jewellery-chatbot-signup">Sign Up</button>
                        </div>
                    </div>
                </div>
                
                <div class="jewellery-chatbot-typing" style="display: none;">
                    <span>Typing...</span>
                </div>
            `;
            
            widgetContainer.appendChild(chatButton);
            widgetContainer.appendChild(chatWindow);
            document.body.appendChild(widgetContainer);
            
            // Store references to elements
            this.elements = {
                widgetContainer,
                chatButton,
                chatWindow,
                messagesContainer: chatWindow.querySelector('.jewellery-chatbot-messages'),
                input: chatWindow.querySelector('.jewellery-chatbot-input'),
                sendButton: chatWindow.querySelector('.jewellery-chatbot-send'),
                attachButton: chatWindow.querySelector('.jewellery-chatbot-attach'),
                fileInput: chatWindow.querySelector('.jewellery-chatbot-file-input'),
                fileUpload: chatWindow.querySelector('.jewellery-chatbot-file-upload'),
                filePreview: chatWindow.querySelector('.jewellery-chatbot-file-preview'),
                authContainer: chatWindow.querySelector('.jewellery-chatbot-auth'),
                usernameInput: chatWindow.querySelector('.jewellery-chatbot-username'),
                passwordInput: chatWindow.querySelector('.jewellery-chatbot-password'),
                loginButton: chatWindow.querySelector('.jewellery-chatbot-login'),
                signupButton: chatWindow.querySelector('.jewellery-chatbot-signup'),
                minimizeButton: chatWindow.querySelector('.jewellery-chatbot-minimize'),
                closeButton: chatWindow.querySelector('.jewellery-chatbot-close'),
                typingIndicator: chatWindow.querySelector('.jewellery-chatbot-typing')
            };
            
            // Apply styles
            this.applyStyles();
            this.setPosition(this.config.position);
        }

        /**
         * Apply CSS styles to the widget
         */
        applyStyles() {
            const styles = `
                .jewellery-chatbot-widget {
                    position: fixed;
                    z-index: 10000;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                
                .jewellery-chatbot-button {
                    width: 60px;
                    height: 60px;
                    border-radius: 50%;
                    background: ${this.getPrimaryColor()};
                    color: white;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                    transition: all 0.3s ease;
                    position: relative;
                }
                
                .jewellery-chatbot-button:hover {
                    transform: scale(1.1);
                    box-shadow: 0 6px 20px rgba(0,0,0,0.2);
                }
                
                .jewellery-chatbot-window {
                    width: 380px;
                    height: 600px;
                    background: white;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.2);
                    display: none;
                    flex-direction: column;
                    position: absolute;
                    bottom: 80px;
                    right: 0;
                    overflow: hidden;
                }
                
                .jewellery-chatbot-window.open {
                    display: flex;
                }
                
                .jewellery-chatbot-header {
                    background: ${this.getPrimaryColor()};
                    color: white;
                    padding: 16px 20px;
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    border-radius: 12px 12px 0 0;
                }
                
                .jewellery-chatbot-title {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-weight: 600;
                    font-size: 16px;
                }
                
                .jewellery-chatbot-icon {
                    font-size: 20px;
                }
                
                .jewellery-chatbot-controls {
                    display: flex;
                    gap: 8px;
                }
                
                .jewellery-chatbot-controls button {
                    background: rgba(255,255,255,0.2);
                    border: none;
                    color: white;
                    width: 24px;
                    height: 24px;
                    border-radius: 50%;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 14px;
                    transition: background 0.2s ease;
                }
                
                .jewellery-chatbot-controls button:hover {
                    background: rgba(255,255,255,0.3);
                }
                
                .jewellery-chatbot-messages {
                    flex: 1;
                    padding: 20px;
                    overflow-y: auto;
                    background: #f8f9fa;
                }
                
                .jewellery-chatbot-message {
                    margin-bottom: 16px;
                    display: flex;
                    flex-direction: column;
                }
                
                .jewellery-chatbot-message.user {
                    align-items: flex-end;
                }
                
                .jewellery-chatbot-message.assistant {
                    align-items: flex-start;
                }
                
                .jewellery-chatbot-message-bubble {
                    max-width: 80%;
                    padding: 12px 16px;
                    border-radius: 18px;
                    font-size: 14px;
                    line-height: 1.4;
                }
                
                .jewellery-chatbot-message.user .jewellery-chatbot-message-bubble {
                    background: ${this.getPrimaryColor()};
                    color: white;
                    border-bottom-right-radius: 4px;
                }
                
                .jewellery-chatbot-message.assistant .jewellery-chatbot-message-bubble {
                    background: white;
                    color: #333;
                    border: 1px solid #e1e5e9;
                    border-bottom-left-radius: 4px;
                }
                
                .jewellery-chatbot-message-time {
                    font-size: 11px;
                    color: #999;
                    margin-top: 4px;
                }
                
                .jewellery-chatbot-input-area {
                    border-top: 1px solid #e1e5e9;
                    background: white;
                }
                
                .jewellery-chatbot-file-upload {
                    padding: 12px 16px;
                    border-bottom: 1px solid #e1e5e9;
                    background: #f8f9fa;
                }
                
                .jewellery-chatbot-file-preview {
                    display: flex;
                    align-items: center;
                    gap: 8px;
                    font-size: 12px;
                    color: #666;
                }
                
                .jewellery-chatbot-file-preview img {
                    width: 40px;
                    height: 40px;
                    object-fit: cover;
                    border-radius: 4px;
                }
                
                .jewellery-chatbot-input-container {
                    display: flex;
                    align-items: center;
                    padding: 12px 16px;
                    gap: 8px;
                }
                
                .jewellery-chatbot-input {
                    flex: 1;
                    border: 1px solid #e1e5e9;
                    border-radius: 20px;
                    padding: 10px 16px;
                    font-size: 14px;
                    outline: none;
                    transition: border-color 0.2s ease;
                }
                
                .jewellery-chatbot-input:focus {
                    border-color: ${this.getPrimaryColor()};
                }
                
                .jewellery-chatbot-attach,
                .jewellery-chatbot-send {
                    width: 36px;
                    height: 36px;
                    border: none;
                    border-radius: 50%;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 16px;
                    transition: all 0.2s ease;
                }
                
                .jewellery-chatbot-attach {
                    background: #f8f9fa;
                    color: #666;
                }
                
                .jewellery-chatbot-attach:hover {
                    background: #e9ecef;
                }
                
                .jewellery-chatbot-send {
                    background: ${this.getPrimaryColor()};
                    color: white;
                }
                
                .jewellery-chatbot-send:hover {
                    background: ${this.getPrimaryColor()};
                    opacity: 0.9;
                }
                
                .jewellery-chatbot-send:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                }
                
                .jewellery-chatbot-auth {
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(255,255,255,0.95);
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    z-index: 100;
                }
                
                .jewellery-chatbot-auth-form {
                    background: white;
                    padding: 32px;
                    border-radius: 12px;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                    width: 90%;
                    max-width: 320px;
                    text-align: center;
                }
                
                .jewellery-chatbot-auth-form h3 {
                    margin: 0 0 24px 0;
                    color: #333;
                    font-size: 20px;
                }
                
                .jewellery-chatbot-auth-form input {
                    width: 100%;
                    padding: 12px 16px;
                    margin-bottom: 12px;
                    border: 1px solid #e1e5e9;
                    border-radius: 8px;
                    font-size: 14px;
                    outline: none;
                }
                
                .jewellery-chatbot-auth-form input:focus {
                    border-color: ${this.getPrimaryColor()};
                }
                
                .jewellery-chatbot-auth-buttons {
                    display: flex;
                    gap: 8px;
                    margin-top: 16px;
                }
                
                .jewellery-chatbot-auth-buttons button {
                    flex: 1;
                    padding: 12px;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: 600;
                    cursor: pointer;
                    transition: all 0.2s ease;
                }
                
                .jewellery-chatbot-login {
                    background: ${this.getPrimaryColor()};
                    color: white;
                }
                
                .jewellery-chatbot-login:hover {
                    opacity: 0.9;
                }
                
                .jewellery-chatbot-signup {
                    background: #f8f9fa;
                    color: #666;
                    border: 1px solid #e1e5e9;
                }
                
                .jewellery-chatbot-signup:hover {
                    background: #e9ecef;
                }
                
                .jewellery-chatbot-typing {
                    padding: 8px 16px;
                    font-size: 12px;
                    color: #999;
                    font-style: italic;
                }
                
                .jewellery-chatbot-product {
                    background: white;
                    border: 1px solid #e1e5e9;
                    border-radius: 8px;
                    padding: 12px;
                    margin: 8px 0;
                }
                
                .jewellery-chatbot-product-name {
                    font-weight: 600;
                    color: #333;
                    margin-bottom: 4px;
                }
                
                .jewellery-chatbot-product-price {
                    color: ${this.getPrimaryColor()};
                    font-weight: 600;
                    margin-bottom: 4px;
                }
                
                .jewellery-chatbot-product-description {
                    font-size: 12px;
                    color: #666;
                    line-height: 1.3;
                }
                
                .jewellery-chatbot-product-image {
                    width: 100%;
                    max-width: 200px;
                    height: 150px;
                    object-fit: cover;
                    border-radius: 4px;
                    margin: 8px 0;
                }
                
                /* Responsive design */
                @media (max-width: 480px) {
                    .jewellery-chatbot-window {
                        width: 100vw;
                        height: 100vh;
                        border-radius: 0;
                        bottom: 0;
                        right: 0;
                        left: 0;
                        top: 0;
                    }
                    
                    .jewellery-chatbot-button {
                        bottom: 20px;
                        right: 20px;
                    }
                }
            `;
            
            // Add styles to head
            const styleElement = document.createElement('style');
            styleElement.textContent = styles;
            document.head.appendChild(styleElement);
        }

        /**
         * Get primary color based on theme
         */
        getPrimaryColor() {
            const themes = {
                blue: '#007bff',
                purple: '#6f42c1',
                green: '#28a745',
                custom: this.config.customColors.primary || '#007bff'
            };
            return themes[this.config.theme] || themes.blue;
        }

        /**
         * Set widget position
         */
        setPosition(position) {
            const positions = {
                'bottom-right': { bottom: '20px', right: '20px' },
                'bottom-left': { bottom: '20px', left: '20px' },
                'top-right': { top: '20px', right: '20px' },
                'top-left': { top: '20px', left: '20px' }
            };
            
            const pos = positions[position] || positions['bottom-right'];
            Object.assign(this.elements.widgetContainer.style, pos);
        }

        /**
         * Set up event listeners
         */
        setupEventListeners() {
            // Toggle chat window
            this.elements.chatButton.addEventListener('click', () => this.toggleChat());
            this.elements.minimizeButton.addEventListener('click', () => this.toggleChat());
            this.elements.closeButton.addEventListener('click', () => this.toggleChat());
            
            // Send message
            this.elements.sendButton.addEventListener('click', () => this.sendMessage());
            this.elements.input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') this.sendMessage();
            });
            
            // File upload
            this.elements.attachButton.addEventListener('click', () => {
                this.elements.fileInput.click();
            });
            this.elements.fileInput.addEventListener('change', (e) => this.handleFileUpload(e));
            
            // Authentication
            this.elements.loginButton.addEventListener('click', () => this.login());
            this.elements.signupButton.addEventListener('click', () => this.signup());
        }

        /**
         * Toggle chat window
         */
        toggleChat() {
            this.state.isOpen = !this.state.isOpen;
            
            if (this.state.isOpen) {
                this.elements.chatWindow.classList.add('open');
                this.elements.chatButton.style.display = 'none';
                
                // Check authentication
                if (!this.state.isAuthenticated) {
                    this.showAuthForm();
                } else {
                    this.hideAuthForm();
                    this.loadChatHistory();
                }
                
                // Focus input
                setTimeout(() => this.elements.input.focus(), 100);
            } else {
                this.elements.chatWindow.classList.remove('open');
                this.elements.chatButton.style.display = 'flex';
            }
        }

        /**
         * Show authentication form
         */
        showAuthForm() {
            this.elements.authContainer.style.display = 'flex';
            this.elements.messagesContainer.style.display = 'none';
            this.elements.inputArea.style.display = 'none';
        }

        /**
         * Hide authentication form
         */
        hideAuthForm() {
            this.elements.authContainer.style.display = 'none';
            this.elements.messagesContainer.style.display = 'block';
            this.elements.inputArea.style.display = 'block';
            
            // Add welcome message if no messages
            if (this.state.messages.length === 0) {
                this.addMessage('assistant', this.config.welcomeMessage);
            }
        }

        /**
         * Check API health
         */
        async checkAPIHealth() {
            try {
                const response = await this.makeRequest(this.apiEndpoints.health, 'GET');
                if (response.status === 'ok') {
                    console.log('JewelleryChatbot: API connection successful');
                }
            } catch (error) {
                console.error('JewelleryChatbot: API connection failed', error);
                this.addMessage('assistant', 'Sorry, I\'m having trouble connecting to the server. Please try again later.');
            }
        }

        /**
         * Make API request
         */
        async makeRequest(endpoint, method = 'GET', data = null, headers = {}) {
            const url = this.config.apiUrl + endpoint;
            const options = {
                method,
                headers: {
                    'Content-Type': 'application/json',
                    ...headers
                }
            };
            
            if (this.state.accessToken) {
                options.headers['Authorization'] = `Bearer ${this.state.accessToken}`;
            }
            
            if (data && method !== 'GET') {
                options.body = JSON.stringify(data);
            }
            
            const response = await fetch(url, options);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        }

        /**
         * User signup
         */
        async signup() {
            const username = this.elements.usernameInput.value.trim();
            const password = this.elements.passwordInput.value.trim();
            
            if (!username || !password) {
                alert('Please enter both username and password');
                return;
            }
            
            try {
                const data = {
                    username: username,
                    email: username,
                    password: password
                };
                
                const response = await this.makeRequest(this.apiEndpoints.signup, 'POST', data);
                
                // Auto-login after signup
                await this.login();
                
            } catch (error) {
                console.error('Signup error:', error);
                alert('Signup failed. Please try again.');
            }
        }

        // /**
        //  * User login
        //  */
        // async login() {
        //     const username = this.elements.usernameInput.value.trim();
        //     const password = this.elements.passwordInput.value.trim();
            
        //     if (!username || !password) {
        //         alert('Please enter both username and password');
        //         return;
        //     }
            
        //     try {
        //         const data = {
        //             username: username,
        //             password: password
        //         };
                
        //         const response = await this.makeRequest(this.apiEndpoints.login, 'POST', data);
                
        //         this.state.accessToken = response.access_token;
        //         this.state.userId = response.user_id;
        //         this.state.isAuthenticated = true;
        //         this.state.currentUser = username;
                
        //         // Create session
        //         await this.createSession();
                
        //         this.hideAuthForm();
        //         this.addMessage('assistant', `Welcome back, ${username}! ${this.config.welcomeMessage}`);
                
        //     } catch (error) {
        //         console.error('Login error:', error);
        //         alert('Login failed. Please check your credentials.');
        //     }
        // }



        async login() {
            const username = this.elements.usernameInput.value.trim();
            const password = this.elements.passwordInput.value.trim();
            
            if (!username || !password) {
                alert('Please enter both username and password');
                return;
            }
            
            try {
                const data = {
                    username: username,
                    password: password
                };
                
                const response = await this.makeRequest(this.apiEndpoints.login, 'POST', data);
                
                this.state.accessToken = response.access_token;
                this.state.userId = response.user_id;
                this.state.isAuthenticated = true;
                this.state.currentUser = username;
                
                // Create session
                await this.createSession();
                
                // Clear any previous messages and reset state
                this.state.messages = [];
                this.elements.messagesContainer.innerHTML = '';
                
                this.hideAuthForm();
                
                // Add a proper welcome message
                const welcomeMessage = `Welcome back, ${username}! I'm your personal jewellery assistant. How can I help you today?`;
                this.addMessage('assistant', welcomeMessage);
                
                // Add a follow-up suggestion
                setTimeout(() => {
                    this.addMessage('assistant', 'You can ask me about:\n• Specific jewellery items\n• Gift recommendations\n• Price ranges\n• Or anything else you\'re looking for!');
                }, 500);
                
            } catch (error) {
                console.error('Login error:', error);
                alert('Login failed. Please check your credentials.');
            }
        }

        /**
         * Create chat session
         */
        async createSession() {
            try {
                const response = await this.makeRequest(this.apiEndpoints.createSession, 'POST');
                this.state.sessionId = response.session_id;
                console.log('Session created:', this.state.sessionId);
            } catch (error) {
                console.error('Session creation error:', error);
                throw error;
            }
        }

        /**
         * Send message
         */
        async sendMessage() {
            const message = this.elements.input.value.trim();
            
            if (!message) return;
            
            if (!this.state.isAuthenticated) {
                this.showAuthForm();
                return;
            }
            
            if (!this.state.sessionId) {
                await this.createSession();
            }
            
            // Add user message to UI
            this.addMessage('user', message);
            
            // Clear input
            this.elements.input.value = '';
            
            // Show typing indicator
            this.showTyping(true);
            
            try {
                const data = {
                    query: message,
                    session_id: this.state.sessionId,
                    limit: 5
                };
                
                const response = await this.makeRequest(this.apiEndpoints.chatQuery, 'POST', data);
                
                // Add assistant response
                this.addMessage('assistant', response.response, response.products);
                
            } catch (error) {
                console.error('Chat error:', error);
                this.addMessage('assistant', 'Sorry, I encountered an error. Please try again.');
            } finally {
                this.showTyping(false);
            }
        }

        /**
         * Handle file upload
         */
        async handleFileUpload(event) {
            const file = event.target.files[0];
            
            if (!file) return;
            
            // Validate file
            if (!this.config.allowedFileTypes.includes(file.type)) {
                alert('Please upload an image file (JPEG, PNG, or WebP)');
                return;
            }
            
            if (file.size > this.config.maxFileSize) {
                alert('File size must be less than 5MB');
                return;
            }
            
            // Show file preview
            const reader = new FileReader();
            reader.onload = (e) => {
                this.elements.filePreview.innerHTML = `
                    <img src="${e.target.result}" alt="Preview">
                    <span>${file.name}</span>
                    <button onclick="this.parentElement.innerHTML=''" style="margin-left: auto;">×</button>
                `;
                this.elements.fileUpload.style.display = 'block';
            };
            reader.readAsDataURL(file);
            
            // TODO: Implement image-based search when API supports it
            console.log('File uploaded:', file.name);
        }

        /**
         * Add message to chat
         */
        addMessage(role, content, products = null) {
            const messageElement = document.createElement('div');
            messageElement.className = `jewellery-chatbot-message ${role}`;
            
            const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            
            let messageHTML = `
                <div class="jewellery-chatbot-message-bubble">
                    ${this.escapeHtml(content)}
                </div>
                <div class="jewellery-chatbot-message-time">${time}</div>
            `;
            
            // Add products if available
            if (products && products.length > 0) {
                messageHTML += '<div class="jewellery-chatbot-products">';
                products.forEach(product => {
                    messageHTML += this.createProductHTML(product);
                });
                messageHTML += '</div>';
            }
            
            messageElement.innerHTML = messageHTML;
            this.elements.messagesContainer.appendChild(messageElement);
            
            // Scroll to bottom
            this.scrollToBottom();
            
            // Store message in state
            this.state.messages.push({ role, content, products, timestamp: new Date() });
        }

        /**
         * Create product HTML
         */
        createProductHTML(product) {
            return `
                <div class="jewellery-chatbot-product">
                    ${product.image_url ? `<img src="${product.image_url}" alt="${product.name}" class="jewellery-chatbot-product-image">` : ''}
                    <div class="jewellery-chatbot-product-name">${product.name}</div>
                    <div class="jewellery-chatbot-product-price">$${product.price}</div>
                    ${product.description ? `<div class="jewellery-chatbot-product-description">${product.description}</div>` : ''}
                </div>
            `;
        }

        /**
         * Show/hide typing indicator
         */
        showTyping(show) {
            this.state.isTyping = show;
            this.elements.typingIndicator.style.display = show ? 'block' : 'none';
            this.scrollToBottom();
        }

        /**
         * Scroll to bottom of messages
         */
        scrollToBottom() {
            this.elements.messagesContainer.scrollTop = this.elements.messagesContainer.scrollHeight;
        }

        /**
         * Escape HTML
         */
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        /**
         * Load chat history
         */
        async loadChatHistory() {
            if (!this.state.sessionId) return;
            
            try {
                const response = await this.makeRequest(`${this.apiEndpoints.chatHistory}/${this.state.sessionId}`, 'GET');
                
                // Clear existing messages
                this.elements.messagesContainer.innerHTML = '';
                this.state.messages = [];
                
                // Add historical messages
                if (response.messages && response.messages.length > 0) {
                    response.messages.forEach(msg => {
                        this.addMessage(msg.role, msg.content, msg.products);
                    });
                }
                
            } catch (error) {
                console.error('Load history error:', error);
            }
        }

        /**
         * Public API methods
         */
        open() {
            if (!this.state.isOpen) {
                this.toggleChat();
            }
        }

        close() {
            if (this.state.isOpen) {
                this.toggleChat();
            }
        }

        send(message) {
            this.elements.input.value = message;
            this.sendMessage();
        }

        setTheme(theme) {
            this.config.theme = theme;
            this.applyStyles();
        }

        setPosition(position) {
            this.config.position = position;
            const positions = {
                'bottom-right': { bottom: '20px', right: '20px' },
                'bottom-left': { bottom: '20px', left: '20px' },
                'top-right': { top: '20px', right: '20px' },
                'top-left': { top: '20px', left: '20px' }
            };
            
            const pos = positions[position] || positions['bottom-right'];
            Object.assign(this.elements.widgetContainer.style, pos);
        }
    }

    // Create global instance
    window.JewelleryChatbot = new JewelleryChatbot();

    // Auto-initialize if configuration is provided
    if (window.JewelleryChatbotConfig) {
        window.JewelleryChatbot.init(window.JewelleryChatbotConfig);
    }

})(window);