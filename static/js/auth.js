// Authentication JavaScript

class AuthManager {
    constructor() {
        this.apiBase = '/api';
        this.setupEventListeners();
    }

    setupEventListeners() {
        // Login Form
        const loginForm = document.getElementById('loginForm');
        if (loginForm) {
            loginForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.login();
            });
        }

        // Signup Form
        const signupForm = document.getElementById('signupForm');
        if (signupForm) {
            signupForm.addEventListener('submit', (e) => {
                e.preventDefault();
                this.signup();
            });
        }
    }

    async login() {
        const email = document.getElementById('loginEmail').value.trim();
        const password = document.getElementById('loginPassword').value.trim();

        if (!email || !password) {
            this.showError('Please fill in all fields');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (!response.ok) {
                this.showError(data.message || 'Login failed');
                return;
            }

            // Store token and user ID
            localStorage.setItem('token', data.data.token);
            localStorage.setItem('userId', data.data.user._id);

            this.showSuccess('Login successful! Redirecting...');

            setTimeout(() => {
                window.location.href = '/';
            }, 1500);
        } catch (error) {
            console.error('Login error:', error);
            this.showError('An error occurred. Please try again.');
        }
    }

    async signup() {
        const email = document.getElementById('signupEmail').value.trim();
        const username = document.getElementById('signupUsername').value.trim();
        const fullName = document.getElementById('signupFullName').value.trim();
        const password = document.getElementById('signupPassword').value.trim();
        const confirmPassword = document.getElementById('signupConfirmPassword').value.trim();

        if (!email || !username || !password || !confirmPassword) {
            this.showError('Please fill in all required fields');
            return;
        }

        if (password !== confirmPassword) {
            this.showError('Passwords do not match');
            return;
        }

        if (password.length < 8) {
            this.showError('Password must be at least 8 characters');
            return;
        }

        try {
            const response = await fetch(`${this.apiBase}/auth/signup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email,
                    username,
                    full_name: fullName,
                    password
                })
            });

            const data = await response.json();

            if (!response.ok) {
                this.showError(data.message || 'Signup failed');
                return;
            }

            // Store token and user ID
            localStorage.setItem('token', data.data.token);
            localStorage.setItem('userId', data.data.user._id);

            this.showSuccess('Account created! Redirecting...');

            setTimeout(() => {
                window.location.href = '/';
            }, 1500);
        } catch (error) {
            console.error('Signup error:', error);
            this.showError('An error occurred. Please try again.');
        }
    }

    showError(message) {
        this.showNotification(message, 'danger');
    }

    showSuccess(message) {
        this.showNotification(message, 'success');
    }

    showNotification(message, type) {
        const alertDiv = document.createElement('div');
        alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3 shadow-sm`;
        alertDiv.style.zIndex = '1050';
        alertDiv.style.minWidth = '320px';
        alertDiv.style.maxWidth = '90%';
        
        alertDiv.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;

        // Insert at top of body
        document.body.insertAdjacentElement('afterbegin', alertDiv);

        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            const alert = new bootstrap.Alert(alertDiv);
            alert.close();
        }, 5000);
    }
}

// Initialize auth when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    new AuthManager();
});
