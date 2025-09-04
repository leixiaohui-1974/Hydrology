/**
 * Theme Manager for Hydrology Framework UI
 * Handles theme switching, accessibility features, and user preferences
 */

class ThemeManager {
    constructor() {
        this.themes = {
            light: 'light',
            dark: 'dark',
            'high-contrast': 'high-contrast'
        };
        
        this.currentTheme = this.getStoredTheme() || this.getSystemTheme();
        this.mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
        
        this.init();
    }
    
    init() {
        this.createThemeToggle();
        this.applyTheme(this.currentTheme);
        this.setupEventListeners();
        this.setupAccessibilityFeatures();
        this.setupResponsiveFeatures();
    }
    
    createThemeToggle() {
        // Create theme toggle if it doesn't exist
        if (!document.querySelector('.theme-toggle')) {
            const themeToggle = document.createElement('div');
            themeToggle.className = 'theme-toggle';
            themeToggle.setAttribute('role', 'region');
            themeToggle.setAttribute('aria-label', '主题设置');
            
            const select = document.createElement('select');
            select.id = 'theme-selector';
            select.setAttribute('aria-label', '选择主题');
            
            // Add options
            const options = [
                { value: 'light', text: '🌞 浅色模式' },
                { value: 'dark', text: '🌙 深色模式' },
                { value: 'high-contrast', text: '🔲 高对比度' },
                { value: 'auto', text: '🔄 跟随系统' }
            ];
            
            options.forEach(option => {
                const optionElement = document.createElement('option');
                optionElement.value = option.value;
                optionElement.textContent = option.text;
                if (option.value === this.currentTheme) {
                    optionElement.selected = true;
                }
                select.appendChild(optionElement);
            });
            
            themeToggle.appendChild(select);
            document.body.appendChild(themeToggle);
        }
    }
    
    setupEventListeners() {
        // Theme selector change
        const themeSelector = document.getElementById('theme-selector');
        if (themeSelector) {
            themeSelector.addEventListener('change', (e) => {
                this.setTheme(e.target.value);
            });
        }
        
        // System theme change
        this.mediaQuery.addEventListener('change', (e) => {
            if (this.currentTheme === 'auto') {
                this.applyTheme(this.getSystemTheme());
            }
        });
        
        // Keyboard shortcuts
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + Shift + T for theme toggle
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'T') {
                e.preventDefault();
                this.cycleTheme();
            }
            
            // Ctrl/Cmd + Shift + H for high contrast
            if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key === 'H') {
                e.preventDefault();
                this.setTheme('high-contrast');
            }
        });
        
        // Window resize for responsive features
        window.addEventListener('resize', this.debounce(() => {
            this.handleResize();
        }, 250));
        
        // Focus management
        document.addEventListener('focusin', this.handleFocusIn.bind(this));
        document.addEventListener('focusout', this.handleFocusOut.bind(this));
    }
    
    setupAccessibilityFeatures() {
        // Add skip link if it doesn't exist
        if (!document.querySelector('.skip-link')) {
            const skipLink = document.createElement('a');
            skipLink.href = '#main-content';
            skipLink.className = 'skip-link';
            skipLink.textContent = '跳转到主要内容';
            document.body.insertBefore(skipLink, document.body.firstChild);
        }
        
        // Add main content landmark
        const mainContent = document.querySelector('.app-container');
        if (mainContent && !mainContent.id) {
            mainContent.id = 'main-content';
            mainContent.setAttribute('role', 'main');
        }
        
        // Enhance form labels and descriptions
        this.enhanceFormAccessibility();
        
        // Add ARIA live regions for dynamic content
        this.createLiveRegions();
        
        // Setup focus trap for modals
        this.setupFocusTraps();
    }
    
    setupResponsiveFeatures() {
        // Add viewport meta tag if missing
        if (!document.querySelector('meta[name="viewport"]')) {
            const viewport = document.createElement('meta');
            viewport.name = 'viewport';
            viewport.content = 'width=device-width, initial-scale=1.0, user-scalable=yes';
            document.head.appendChild(viewport);
        }
        
        // Setup responsive navigation
        this.setupResponsiveNavigation();
        
        // Handle initial resize
        this.handleResize();
    }
    
    getSystemTheme() {
        return this.mediaQuery.matches ? 'dark' : 'light';
    }
    
    getStoredTheme() {
        try {
            return localStorage.getItem('hydrology-theme');
        } catch (e) {
            console.warn('Unable to access localStorage for theme preference');
            return null;
        }
    }
    
    storeTheme(theme) {
        try {
            localStorage.setItem('hydrology-theme', theme);
        } catch (e) {
            console.warn('Unable to store theme preference in localStorage');
        }
    }
    
    setTheme(theme) {
        this.currentTheme = theme;
        
        if (theme === 'auto') {
            this.applyTheme(this.getSystemTheme());
        } else {
            this.applyTheme(theme);
        }
        
        this.storeTheme(theme);
        this.updateThemeSelector(theme);
        this.announceThemeChange(theme);
    }
    
    applyTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        
        // Update meta theme-color for mobile browsers
        this.updateMetaThemeColor(theme);
        
        // Dispatch custom event for other components
        window.dispatchEvent(new CustomEvent('themeChanged', {
            detail: { theme }
        }));
    }
    
    updateMetaThemeColor(theme) {
        let themeColor = '#f5f7fa'; // light theme default
        
        if (theme === 'dark') {
            themeColor = '#1a1a1a';
        } else if (theme === 'high-contrast') {
            themeColor = '#000000';
        }
        
        let metaThemeColor = document.querySelector('meta[name="theme-color"]');
        if (!metaThemeColor) {
            metaThemeColor = document.createElement('meta');
            metaThemeColor.name = 'theme-color';
            document.head.appendChild(metaThemeColor);
        }
        metaThemeColor.content = themeColor;
    }
    
    updateThemeSelector(theme) {
        const selector = document.getElementById('theme-selector');
        if (selector) {
            selector.value = theme;
        }
    }
    
    cycleTheme() {
        const themes = ['light', 'dark', 'high-contrast'];
        const currentIndex = themes.indexOf(this.currentTheme === 'auto' ? this.getSystemTheme() : this.currentTheme);
        const nextIndex = (currentIndex + 1) % themes.length;
        this.setTheme(themes[nextIndex]);
    }
    
    announceThemeChange(theme) {
        const messages = {
            light: '已切换到浅色模式',
            dark: '已切换到深色模式',
            'high-contrast': '已切换到高对比度模式',
            auto: '已设置为跟随系统主题'
        };
        
        this.announceToScreenReader(messages[theme] || '主题已更改');
    }
    
    announceToScreenReader(message) {
        const announcement = document.getElementById('sr-announcements');
        if (announcement) {
            announcement.textContent = message;
            // Clear after a delay to avoid cluttering
            setTimeout(() => {
                announcement.textContent = '';
            }, 1000);
        }
    }
    
    enhanceFormAccessibility() {
        // Add proper labels and descriptions to form elements
        const inputs = document.querySelectorAll('input, select, textarea');
        inputs.forEach(input => {
            // Add required indicator
            if (input.required && !input.getAttribute('aria-required')) {
                input.setAttribute('aria-required', 'true');
            }
            
            // Add invalid state handling
            input.addEventListener('invalid', () => {
                input.setAttribute('aria-invalid', 'true');
            });
            
            input.addEventListener('input', () => {
                if (input.validity.valid) {
                    input.removeAttribute('aria-invalid');
                }
            });
        });
    }
    
    createLiveRegions() {
        // Create announcement region for screen readers
        if (!document.getElementById('sr-announcements')) {
            const announcements = document.createElement('div');
            announcements.id = 'sr-announcements';
            announcements.className = 'sr-only';
            announcements.setAttribute('aria-live', 'polite');
            announcements.setAttribute('aria-atomic', 'true');
            document.body.appendChild(announcements);
        }
        
        // Create status region for dynamic updates
        if (!document.getElementById('sr-status')) {
            const status = document.createElement('div');
            status.id = 'sr-status';
            status.className = 'sr-only';
            status.setAttribute('aria-live', 'polite');
            status.setAttribute('aria-atomic', 'false');
            document.body.appendChild(status);
        }
    }
    
    setupFocusTraps() {
        // Setup focus trapping for modal dialogs
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Tab') {
                const modal = document.querySelector('.modal:not(.d-none)');
                if (modal) {
                    this.trapFocus(e, modal);
                }
            }
        });
    }
    
    trapFocus(e, container) {
        const focusableElements = container.querySelectorAll(
            'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        
        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];
        
        if (e.shiftKey) {
            if (document.activeElement === firstElement) {
                e.preventDefault();
                lastElement.focus();
            }
        } else {
            if (document.activeElement === lastElement) {
                e.preventDefault();
                firstElement.focus();
            }
        }
    }
    
    setupResponsiveNavigation() {
        // Handle responsive navigation for mobile devices
        const tabNav = document.querySelector('.tab-nav');
        if (tabNav) {
            // Add touch support for tab navigation
            let startX = 0;
            let scrollLeft = 0;
            
            tabNav.addEventListener('touchstart', (e) => {
                startX = e.touches[0].pageX - tabNav.offsetLeft;
                scrollLeft = tabNav.scrollLeft;
            });
            
            tabNav.addEventListener('touchmove', (e) => {
                e.preventDefault();
                const x = e.touches[0].pageX - tabNav.offsetLeft;
                const walk = (x - startX) * 2;
                tabNav.scrollLeft = scrollLeft - walk;
            });
        }
    }
    
    handleResize() {
        const width = window.innerWidth;
        
        // Update CSS custom property for JavaScript access
        document.documentElement.style.setProperty('--viewport-width', `${width}px`);
        
        // Handle mobile-specific adjustments
        if (width <= 768) {
            this.enableMobileOptimizations();
        } else {
            this.disableMobileOptimizations();
        }
        
        // Announce layout changes to screen readers
        if (width <= 480 && !this.isMobileLayout) {
            this.announceToScreenReader('布局已切换到移动端模式');
            this.isMobileLayout = true;
        } else if (width > 480 && this.isMobileLayout) {
            this.announceToScreenReader('布局已切换到桌面模式');
            this.isMobileLayout = false;
        }
    }
    
    enableMobileOptimizations() {
        // Add mobile-specific classes and behaviors
        document.body.classList.add('mobile-layout');
        
        // Optimize touch targets
        const buttons = document.querySelectorAll('button');
        buttons.forEach(button => {
            if (!button.style.minHeight) {
                button.style.minHeight = '44px';
            }
        });
        
        // Enable swipe gestures for tabs
        this.enableSwipeGestures();
    }
    
    disableMobileOptimizations() {
        document.body.classList.remove('mobile-layout');
        this.disableSwipeGestures();
    }
    
    enableSwipeGestures() {
        const tabContent = document.querySelector('.tab-content');
        if (tabContent && !tabContent.dataset.swipeEnabled) {
            tabContent.dataset.swipeEnabled = 'true';
            
            let startX = 0;
            let startY = 0;
            
            tabContent.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
                startY = e.touches[0].clientY;
            });
            
            tabContent.addEventListener('touchend', (e) => {
                const endX = e.changedTouches[0].clientX;
                const endY = e.changedTouches[0].clientY;
                
                const deltaX = endX - startX;
                const deltaY = endY - startY;
                
                // Only trigger if horizontal swipe is dominant
                if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > 50) {
                    if (deltaX > 0) {
                        this.switchToPreviousTab();
                    } else {
                        this.switchToNextTab();
                    }
                }
            });
        }
    }
    
    disableSwipeGestures() {
        const tabContent = document.querySelector('.tab-content');
        if (tabContent) {
            delete tabContent.dataset.swipeEnabled;
        }
    }
    
    switchToNextTab() {
        const activeTab = document.querySelector('.tab-button.active');
        const nextTab = activeTab?.nextElementSibling;
        if (nextTab && nextTab.classList.contains('tab-button')) {
            nextTab.click();
        }
    }
    
    switchToPreviousTab() {
        const activeTab = document.querySelector('.tab-button.active');
        const prevTab = activeTab?.previousElementSibling;
        if (prevTab && prevTab.classList.contains('tab-button')) {
            prevTab.click();
        }
    }
    
    handleFocusIn(e) {
        // Add focus indicator class for styling
        e.target.classList.add('focus-visible');
        
        // Ensure focused element is visible
        this.ensureElementVisible(e.target);
    }
    
    handleFocusOut(e) {
        // Remove focus indicator class
        e.target.classList.remove('focus-visible');
    }
    
    ensureElementVisible(element) {
        // Scroll element into view if needed
        if (element.scrollIntoViewIfNeeded) {
            element.scrollIntoViewIfNeeded();
        } else {
            element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }
    
    // Utility function for debouncing
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    // Public API methods
    getCurrentTheme() {
        return this.currentTheme;
    }
    
    getAvailableThemes() {
        return Object.keys(this.themes);
    }
    
    isHighContrastMode() {
        return this.currentTheme === 'high-contrast';
    }
    
    isDarkMode() {
        const appliedTheme = this.currentTheme === 'auto' ? this.getSystemTheme() : this.currentTheme;
        return appliedTheme === 'dark';
    }
    
    // Method to update status for screen readers
    updateStatus(message) {
        const status = document.getElementById('sr-status');
        if (status) {
            status.textContent = message;
        }
    }
    
    // Method to make announcements to screen readers
    announce(message) {
        this.announceToScreenReader(message);
    }
}

// Initialize theme manager when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        window.themeManager = new ThemeManager();
    });
} else {
    window.themeManager = new ThemeManager();
}

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ThemeManager;
}