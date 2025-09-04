/**
 * Enhanced Hydrology Framework GUI Application
 * Includes accessibility features, responsive design, and improved UX
 */

class HydrologyApp {
    constructor() {
        this.components = new Map();
        this.connections = new Map();
        this.selectedComponent = null;
        this.draggedComponent = null;
        this.isConnecting = false;
        this.connectionStart = null;
        this.canvas = null;
        this.svg = null;
        this.currentExample = null;
        this.simulationResults = null;
        this.isDarkMode = false;
        
        // Accessibility features
        this.announcer = null;
        this.focusManager = null;
        
        // Mobile/touch support
        this.touchStartPos = null;
        this.isTouchDevice = 'ontouchstart' in window;
        
        this.init();
    }
    
    init() {
        this.setupCanvas();
        this.setupEventListeners();
        this.setupAccessibility();
        this.setupTouchSupport();
        this.loadExamples();
        this.initializeTheme();
        
        // Initialize with welcome message
        this.announce('水文建模工具已准备就绪。使用Tab键导航，拖拽组件到画布创建模型。');
    }
    
    setupCanvas() {
        this.canvas = document.getElementById('canvas');
        this.svg = document.getElementById('connections-svg');
        
        if (!this.canvas || !this.svg) {
            console.error('Canvas or SVG element not found');
            return;
        }
        
        // Set up canvas dimensions
        this.resizeCanvas();
        window.addEventListener('resize', () => this.resizeCanvas());
        
        // Canvas event listeners
        this.canvas.addEventListener('click', (e) => this.handleCanvasClick(e));
        this.canvas.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.canvas.addEventListener('drop', (e) => this.handleDrop(e));
        this.canvas.addEventListener('keydown', (e) => this.handleCanvasKeydown(e));
        
        // Context menu for canvas
        this.canvas.addEventListener('contextmenu', (e) => this.handleContextMenu(e));
    }
    
    setupEventListeners() {
        // Component palette
        const componentItems = document.querySelectorAll('.component-item');
        componentItems.forEach(item => {
            item.addEventListener('dragstart', (e) => this.handleDragStart(e));
            item.addEventListener('click', (e) => this.handleComponentClick(e));
            item.addEventListener('keydown', (e) => this.handleComponentKeydown(e));
        });
        
        // Main action buttons
        document.getElementById('run-button')?.addEventListener('click', () => this.runSimulation());
        document.getElementById('save-button')?.addEventListener('click', () => this.saveModel());
        document.getElementById('export-button')?.addEventListener('click', () => this.exportModel());
        
        // Canvas controls
        document.getElementById('zoom-in')?.addEventListener('click', () => this.zoomIn());
        document.getElementById('zoom-out')?.addEventListener('click', () => this.zoomOut());
        document.getElementById('reset-view')?.addEventListener('click', () => this.resetView());
        document.getElementById('clear-canvas')?.addEventListener('click', () => this.clearCanvas());
        
        // Tab navigation
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(button => {
            button.addEventListener('click', (e) => this.switchTab(e));
        });
        
        // Example items
        const exampleItems = document.querySelectorAll('.example-item');
        exampleItems.forEach(item => {
            item.addEventListener('click', (e) => this.loadExample(e));
            item.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    this.loadExample(e);
                }
            });
        });
        
        // Data source management
        document.querySelector('.add-data-source')?.addEventListener('submit', (e) => this.addDataSource(e));
        document.querySelector('.browse-button')?.addEventListener('click', () => this.browseFile());
        
        // Plot controls
        document.getElementById('component-select')?.addEventListener('change', (e) => this.updateVariableSelect(e));
        document.getElementById('plot-selected')?.addEventListener('click', () => this.plotSelected());
        
        // Log controls
        document.getElementById('clear-log')?.addEventListener('click', () => this.clearLog());
        document.getElementById('export-log')?.addEventListener('click', () => this.exportLog());
        
        // Data controls
        document.getElementById('export-data')?.addEventListener('click', () => this.exportData());
        document.getElementById('import-data')?.addEventListener('click', () => this.importData());
        
        // Global keyboard shortcuts
        document.addEventListener('keydown', (e) => this.handleGlobalKeydown(e));
    }
    
    setupAccessibility() {
        this.announcer = document.getElementById('sr-announcements');
        this.statusAnnouncer = document.getElementById('sr-status');
        
        // Focus management
        this.focusManager = {
            trapFocus: (container) => {
                const focusableElements = container.querySelectorAll(
                    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
                );
                const firstElement = focusableElements[0];
                const lastElement = focusableElements[focusableElements.length - 1];
                
                container.addEventListener('keydown', (e) => {
                    if (e.key === 'Tab') {
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
                });
            }
        };
        
        // Skip link functionality
        const skipLink = document.querySelector('.skip-link');
        if (skipLink) {
            skipLink.addEventListener('click', (e) => {
                e.preventDefault();
                const target = document.querySelector(skipLink.getAttribute('href'));
                if (target) {
                    target.focus();
                    target.scrollIntoView();
                }
            });
        }
    }
    
    setupTouchSupport() {
        if (!this.isTouchDevice) return;
        
        // Touch events for canvas
        this.canvas.addEventListener('touchstart', (e) => this.handleTouchStart(e));
        this.canvas.addEventListener('touchmove', (e) => this.handleTouchMove(e));
        this.canvas.addEventListener('touchend', (e) => this.handleTouchEnd(e));
        
        // Touch events for components
        const componentItems = document.querySelectorAll('.component-item');
        componentItems.forEach(item => {
            item.addEventListener('touchstart', (e) => this.handleComponentTouchStart(e));
        });
        
        // Swipe gestures for tabs
        const tabContent = document.querySelector('.tab-content');
        if (tabContent) {
            let startX = null;
            
            tabContent.addEventListener('touchstart', (e) => {
                startX = e.touches[0].clientX;
            });
            
            tabContent.addEventListener('touchend', (e) => {
                if (startX === null) return;
                
                const endX = e.changedTouches[0].clientX;
                const diff = startX - endX;
                
                if (Math.abs(diff) > 50) { // Minimum swipe distance
                    if (diff > 0) {
                        this.switchToNextTab();
                    } else {
                        this.switchToPrevTab();
                    }
                }
                
                startX = null;
            });
        }
    }
    
    initializeTheme() {
        // Check for saved theme preference or default to system
        const savedTheme = localStorage.getItem('hydrology-theme') || 'system';
        if (window.themeManager) {
            window.themeManager.setTheme(savedTheme);
        }
    }
    
    // Canvas Management
    resizeCanvas() {
        const rect = this.canvas.getBoundingClientRect();
        this.svg.setAttribute('width', rect.width);
        this.svg.setAttribute('height', rect.height);
    }
    
    handleCanvasClick(e) {
        if (e.target === this.canvas) {
            this.deselectComponent();
        }
    }
    
    handleCanvasKeydown(e) {
        switch (e.key) {
            case 'Delete':
            case 'Backspace':
                if (this.selectedComponent) {
                    this.deleteComponent(this.selectedComponent);
                }
                break;
            case 'Escape':
                this.deselectComponent();
                break;
            case 'c':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.copyComponent();
                }
                break;
            case 'v':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.pasteComponent();
                }
                break;
        }
    }
    
    handleContextMenu(e) {
        e.preventDefault();
        this.showContextMenu(e.clientX, e.clientY);
    }
    
    // Component Management
    handleDragStart(e) {
        this.draggedComponent = e.target.dataset.type;
        e.dataTransfer.effectAllowed = 'copy';
        e.dataTransfer.setData('text/plain', this.draggedComponent);
        
        // Add visual feedback
        e.target.classList.add('dragging');
        
        this.announce(`开始拖拽${e.target.textContent}组件`);
    }
    
    handleDragOver(e) {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        
        // Visual feedback for drop zone
        this.canvas.classList.add('drag-over');
    }
    
    handleDrop(e) {
        e.preventDefault();
        this.canvas.classList.remove('drag-over');
        
        const componentType = e.dataTransfer.getData('text/plain');
        if (componentType) {
            const rect = this.canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            this.addComponent(componentType, x, y);
        }
        
        // Remove dragging class from all components
        document.querySelectorAll('.component-item.dragging').forEach(item => {
            item.classList.remove('dragging');
        });
    }
    
    handleComponentClick(e) {
        if (this.isTouchDevice) return; // Handle via touch events
        
        const componentType = e.target.dataset.type;
        this.addComponentToCenter(componentType);
    }
    
    handleComponentKeydown(e) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            const componentType = e.target.dataset.type;
            this.addComponentToCenter(componentType);
        }
    }
    
    addComponent(type, x, y) {
        const id = `${type}_${Date.now()}`;
        const component = {
            id,
            type,
            x,
            y,
            properties: this.getDefaultProperties(type),
            connections: []
        };
        
        this.components.set(id, component);
        this.renderComponent(component);
        this.selectComponent(id);
        
        this.announce(`已添加${this.getComponentDisplayName(type)}组件到画布`);
        this.updateStatus(`组件总数: ${this.components.size}`);
    }
    
    addComponentToCenter(type) {
        const rect = this.canvas.getBoundingClientRect();
        const x = rect.width / 2;
        const y = rect.height / 2;
        this.addComponent(type, x, y);
    }
    
    renderComponent(component) {
        const element = document.createElement('div');
        element.className = 'canvas-node';
        element.id = component.id;
        element.setAttribute('data-type', component.type);
        element.setAttribute('role', 'button');
        element.setAttribute('tabindex', '0');
        element.setAttribute('aria-label', `${this.getComponentDisplayName(component.type)}组件`);
        
        element.style.left = `${component.x}px`;
        element.style.top = `${component.y}px`;
        
        element.innerHTML = `
            <div class="node-header">
                <span class="node-icon">${this.getComponentIcon(component.type)}</span>
                <span class="node-title">${this.getComponentDisplayName(component.type)}</span>
            </div>
            <div class="node-id">${component.id}</div>
        `;
        
        // Event listeners
        element.addEventListener('click', (e) => {
            e.stopPropagation();
            this.selectComponent(component.id);
        });
        
        element.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                this.selectComponent(component.id);
            }
        });
        
        element.addEventListener('dblclick', () => {
            this.editComponentProperties(component.id);
        });
        
        // Make draggable
        element.draggable = true;
        element.addEventListener('dragstart', (e) => {
            e.dataTransfer.setData('component-id', component.id);
        });
        
        this.canvas.appendChild(element);
    }
    
    selectComponent(id) {
        // Deselect previous
        this.deselectComponent();
        
        const element = document.getElementById(id);
        if (element) {
            element.classList.add('selected');
            element.focus();
            this.selectedComponent = id;
            this.showComponentProperties(id);
            
            const component = this.components.get(id);
            this.announce(`已选择${this.getComponentDisplayName(component.type)}组件`);
        }
    }
    
    deselectComponent() {
        if (this.selectedComponent) {
            const element = document.getElementById(this.selectedComponent);
            if (element) {
                element.classList.remove('selected');
            }
            this.selectedComponent = null;
            this.hideComponentProperties();
        }
    }
    
    deleteComponent(id) {
        const component = this.components.get(id);
        if (!component) return;
        
        // Remove connections
        this.removeComponentConnections(id);
        
        // Remove from canvas
        const element = document.getElementById(id);
        if (element) {
            element.remove();
        }
        
        // Remove from components map
        this.components.delete(id);
        
        this.announce(`已删除${this.getComponentDisplayName(component.type)}组件`);
        this.updateStatus(`组件总数: ${this.components.size}`);
        
        if (this.selectedComponent === id) {
            this.selectedComponent = null;
            this.hideComponentProperties();
        }
    }
    
    // Properties Management
    showComponentProperties(id) {
        const component = this.components.get(id);
        if (!component) return;
        
        const propertiesContent = document.getElementById('properties-content');
        if (!propertiesContent) return;
        
        propertiesContent.innerHTML = `
            <div class="property-section">
                <h3>${this.getComponentDisplayName(component.type)}属性</h3>
                <div class="property-form" role="form">
                    ${this.generatePropertyFields(component)}
                    <div class="property-actions">
                        <button type="button" class="btn-primary" onclick="app.applyProperties('${id}')">
                            应用更改
                        </button>
                        <button type="button" class="btn-secondary" onclick="app.resetProperties('${id}')">
                            重置
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Focus first input for accessibility
        const firstInput = propertiesContent.querySelector('input, select, textarea');
        if (firstInput) {
            setTimeout(() => firstInput.focus(), 100);
        }
    }
    
    hideComponentProperties() {
        const propertiesContent = document.getElementById('properties-content');
        if (propertiesContent) {
            propertiesContent.innerHTML = `
                <div class="no-selection-message">
                    <p>请选择一个组件来编辑其属性</p>
                    <p class="text-muted">在画布中点击组件或使用键盘导航选择</p>
                </div>
            `;
        }
    }
    
    generatePropertyFields(component) {
        const properties = component.properties;
        let html = '';
        
        for (const [key, value] of Object.entries(properties)) {
            const fieldId = `prop_${component.id}_${key}`;
            const label = this.getPropertyLabel(key);
            const type = this.getPropertyType(key, value);
            
            html += `
                <div class="property-row">
                    <label for="${fieldId}">${label}:</label>
                    ${this.generatePropertyInput(fieldId, key, value, type)}
                </div>
            `;
        }
        
        return html;
    }
    
    generatePropertyInput(fieldId, key, value, type) {
        switch (type) {
            case 'number':
                return `<input type="number" id="${fieldId}" value="${value}" step="any">`;
            case 'boolean':
                return `<input type="checkbox" id="${fieldId}" ${value ? 'checked' : ''}>`;
            case 'select':
                const options = this.getPropertyOptions(key);
                let optionsHtml = '';
                for (const option of options) {
                    const selected = option.value === value ? 'selected' : '';
                    optionsHtml += `<option value="${option.value}" ${selected}>${option.label}</option>`;
                }
                return `<select id="${fieldId}">${optionsHtml}</select>`;
            default:
                return `<input type="text" id="${fieldId}" value="${value}">`;
        }
    }
    
    applyProperties(id) {
        const component = this.components.get(id);
        if (!component) return;
        
        const form = document.querySelector('.property-form');
        const inputs = form.querySelectorAll('input, select, textarea');
        
        inputs.forEach(input => {
            const key = input.id.split('_').pop();
            let value = input.value;
            
            if (input.type === 'checkbox') {
                value = input.checked;
            } else if (input.type === 'number') {
                value = parseFloat(value) || 0;
            }
            
            component.properties[key] = value;
        });
        
        this.announce('属性已更新');
        this.updateComponentDisplay(id);
    }
    
    resetProperties(id) {
        const component = this.components.get(id);
        if (!component) return;
        
        component.properties = this.getDefaultProperties(component.type);
        this.showComponentProperties(id);
        this.updateComponentDisplay(id);
        this.announce('属性已重置为默认值');
    }
    
    // Simulation Management
    async runSimulation() {
        if (this.components.size === 0) {
            this.showError('请先添加组件到画布');
            return;
        }
        
        this.announce('开始运行模拟');
        this.updateStatus('正在运行模拟...');
        
        const runButton = document.getElementById('run-button');
        if (runButton) {
            runButton.disabled = true;
            runButton.innerHTML = '<span class="loading-spinner"></span> 运行中...';
        }
        
        try {
            // Simulate API call
            const modelData = this.exportModelData();
            const results = await this.callSimulationAPI(modelData);
            
            this.simulationResults = results;
            this.displayResults(results);
            this.announce('模拟运行完成');
            this.updateStatus('模拟完成');
            
        } catch (error) {
            console.error('Simulation error:', error);
            this.showError('模拟运行失败: ' + error.message);
            this.announce('模拟运行失败');
        } finally {
            if (runButton) {
                runButton.disabled = false;
                runButton.innerHTML = '<span aria-hidden="true">▶️</span> 运行';
            }
        }
    }
    
    async callSimulationAPI(modelData) {
        // Mock API call - replace with actual API endpoint
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                if (Math.random() > 0.1) { // 90% success rate
                    resolve({
                        status: 'success',
                        components: this.generateMockResults(),
                        timestamp: new Date().toISOString()
                    });
                } else {
                    reject(new Error('模拟计算失败'));
                }
            }, 2000 + Math.random() * 3000); // 2-5 second delay
        });
    }
    
    generateMockResults() {
        const results = {};
        
        for (const [id, component] of this.components) {
            results[id] = {
                type: component.type,
                variables: this.generateMockVariables(component.type),
                status: 'completed'
            };
        }
        
        return results;
    }
    
    generateMockVariables(componentType) {
        const baseTime = Array.from({length: 24}, (_, i) => i);
        
        switch (componentType) {
            case 'Catchment':
                return {
                    flow: baseTime.map(t => 10 + 5 * Math.sin(t * Math.PI / 12) + Math.random() * 2),
                    precipitation: baseTime.map(t => Math.max(0, 2 * Math.sin(t * Math.PI / 6) + Math.random())),
                    evaporation: baseTime.map(t => 1 + 0.5 * Math.sin(t * Math.PI / 12))
                };
            case 'RiverReach':
                return {
                    discharge: baseTime.map(t => 15 + 8 * Math.sin(t * Math.PI / 12) + Math.random() * 3),
                    water_level: baseTime.map(t => 2 + 0.5 * Math.sin(t * Math.PI / 12) + Math.random() * 0.1),
                    velocity: baseTime.map(t => 1.2 + 0.3 * Math.sin(t * Math.PI / 12))
                };
            default:
                return {
                    value: baseTime.map(t => Math.random() * 10)
                };
        }
    }
    
    displayResults(results) {
        this.updateComponentSelect(results.components);
        this.logMessage('模拟完成', 'success');
        this.logMessage(`处理了 ${Object.keys(results.components).length} 个组件`, 'info');
        
        // Switch to plot tab
        this.switchToTab('plot-tab');
    }
    
    // UI Helper Methods
    announce(message) {
        if (this.announcer) {
            this.announcer.textContent = message;
        }
    }
    
    updateStatus(message) {
        if (this.statusAnnouncer) {
            this.statusAnnouncer.textContent = message;
        }
    }
    
    showError(message) {
        this.showToast(message, 'error');
        this.logMessage(message, 'error');
    }
    
    showSuccess(message) {
        this.showToast(message, 'success');
        this.logMessage(message, 'success');
    }
    
    showToast(message, type = 'info') {
        const container = document.getElementById('toast-container');
        if (!container) return;
        
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.setAttribute('role', 'alert');
        toast.setAttribute('aria-live', 'polite');
        
        toast.innerHTML = `
            <div class="toast-content">
                <span class="toast-icon">${this.getToastIcon(type)}</span>
                <span class="toast-message">${message}</span>
                <button class="toast-close" aria-label="关闭通知">&times;</button>
            </div>
        `;
        
        const closeBtn = toast.querySelector('.toast-close');
        closeBtn.addEventListener('click', () => {
            toast.remove();
        });
        
        container.appendChild(toast);
        
        // Auto remove after 5 seconds
        setTimeout(() => {
            if (toast.parentNode) {
                toast.remove();
            }
        }, 5000);
    }
    
    getToastIcon(type) {
        switch (type) {
            case 'success': return '✅';
            case 'error': return '❌';
            case 'warning': return '⚠️';
            default: return 'ℹ️';
        }
    }
    
    logMessage(message, level = 'info') {
        const logContent = document.getElementById('log-content');
        if (!logContent) return;
        
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${level.toUpperCase()}: ${message}\n`;
        
        logContent.textContent += logEntry;
        logContent.scrollTop = logContent.scrollHeight;
    }
    
    clearLog() {
        const logContent = document.getElementById('log-content');
        if (logContent) {
            logContent.textContent = '日志已清空\n';
        }
    }
    
    // Tab Management
    switchTab(e) {
        const clickedTab = e.target;
        const targetPaneId = clickedTab.getAttribute('aria-controls');
        
        // Update tab buttons
        document.querySelectorAll('.tab-button').forEach(tab => {
            tab.classList.remove('active');
            tab.setAttribute('aria-selected', 'false');
        });
        
        clickedTab.classList.add('active');
        clickedTab.setAttribute('aria-selected', 'true');
        
        // Update tab panes
        document.querySelectorAll('.tab-pane').forEach(pane => {
            pane.classList.remove('active');
        });
        
        const targetPane = document.getElementById(targetPaneId);
        if (targetPane) {
            targetPane.classList.add('active');
        }
        
        this.announce(`切换到${clickedTab.textContent.trim()}标签页`);
    }
    
    switchToTab(tabId) {
        const tab = document.getElementById(tabId);
        if (tab) {
            tab.click();
        }
    }
    
    switchToNextTab() {
        const tabs = document.querySelectorAll('.tab-button');
        const activeTab = document.querySelector('.tab-button.active');
        const currentIndex = Array.from(tabs).indexOf(activeTab);
        const nextIndex = (currentIndex + 1) % tabs.length;
        tabs[nextIndex].click();
    }
    
    switchToPrevTab() {
        const tabs = document.querySelectorAll('.tab-button');
        const activeTab = document.querySelector('.tab-button.active');
        const currentIndex = Array.from(tabs).indexOf(activeTab);
        const prevIndex = currentIndex > 0 ? currentIndex - 1 : tabs.length - 1;
        tabs[prevIndex].click();
    }
    
    // Touch Support
    handleTouchStart(e) {
        if (e.touches.length === 1) {
            this.touchStartPos = {
                x: e.touches[0].clientX,
                y: e.touches[0].clientY
            };
        }
    }
    
    handleTouchMove(e) {
        e.preventDefault(); // Prevent scrolling
    }
    
    handleTouchEnd(e) {
        if (this.touchStartPos && e.changedTouches.length === 1) {
            const touch = e.changedTouches[0];
            const deltaX = Math.abs(touch.clientX - this.touchStartPos.x);
            const deltaY = Math.abs(touch.clientY - this.touchStartPos.y);
            
            // If it's a tap (small movement)
            if (deltaX < 10 && deltaY < 10) {
                this.handleCanvasClick(e);
            }
        }
        
        this.touchStartPos = null;
    }
    
    handleComponentTouchStart(e) {
        // Long press to add component
        const component = e.target;
        const longPressTimer = setTimeout(() => {
            this.addComponentToCenter(component.dataset.type);
            navigator.vibrate && navigator.vibrate(50); // Haptic feedback
        }, 500);
        
        const clearTimer = () => {
            clearTimeout(longPressTimer);
            component.removeEventListener('touchend', clearTimer);
            component.removeEventListener('touchmove', clearTimer);
        };
        
        component.addEventListener('touchend', clearTimer);
        component.addEventListener('touchmove', clearTimer);
    }
    
    // Utility Methods
    getComponentDisplayName(type) {
        const names = {
            'Catchment': '流域',
            'RiverReach': '河段',
            'Junction': '连接点',
            'Gate': '闸门',
            'Pump': '水泵',
            'HydraulicModel2D': '二维模型区域'
        };
        return names[type] || type;
    }
    
    getComponentIcon(type) {
        const icons = {
            'Catchment': '🏞️',
            'RiverReach': '🌊',
            'Junction': '➕',
            'Gate': '⛕',
            'Pump': '⚡',
            'HydraulicModel2D': '🌐'
        };
        return icons[type] || '📦';
    }
    
    getDefaultProperties(type) {
        const defaults = {
            'Catchment': {
                area: 100,
                curve_number: 70,
                initial_abstraction: 0.2,
                time_of_concentration: 60
            },
            'RiverReach': {
                length: 1000,
                slope: 0.001,
                manning_n: 0.03,
                width: 10
            },
            'Junction': {
                elevation: 0,
                storage_area: 0
            },
            'Gate': {
                width: 5,
                height: 2,
                discharge_coefficient: 0.6
            },
            'Pump': {
                capacity: 10,
                efficiency: 0.8,
                head: 5
            },
            'HydraulicModel2D': {
                cell_size: 10,
                time_step: 1,
                manning_n: 0.03
            }
        };
        return { ...defaults[type] } || {};
    }
    
    getPropertyLabel(key) {
        const labels = {
            area: '面积 (km²)',
            curve_number: 'CN值',
            initial_abstraction: '初损率',
            time_of_concentration: '汇流时间 (min)',
            length: '长度 (m)',
            slope: '坡度',
            manning_n: '曼宁系数',
            width: '宽度 (m)',
            elevation: '高程 (m)',
            storage_area: '调蓄面积 (m²)',
            height: '高度 (m)',
            discharge_coefficient: '流量系数',
            capacity: '容量 (m³/s)',
            efficiency: '效率',
            head: '扬程 (m)',
            cell_size: '网格大小 (m)',
            time_step: '时间步长 (s)'
        };
        return labels[key] || key;
    }
    
    getPropertyType(key, value) {
        if (typeof value === 'number') return 'number';
        if (typeof value === 'boolean') return 'boolean';
        return 'text';
    }
    
    getPropertyOptions(key) {
        // Return options for select fields if needed
        return [];
    }
    
    // Global keyboard shortcuts
    handleGlobalKeydown(e) {
        // Only handle if not in input field
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') {
            return;
        }
        
        switch (e.key) {
            case 'F1':
                e.preventDefault();
                this.showHelp();
                break;
            case 'F5':
                if (!e.ctrlKey) {
                    e.preventDefault();
                    this.runSimulation();
                }
                break;
            case 's':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.saveModel();
                }
                break;
            case 'o':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.loadModel();
                }
                break;
            case 'n':
                if (e.ctrlKey) {
                    e.preventDefault();
                    this.clearCanvas();
                }
                break;
        }
    }
    
    // Placeholder methods for future implementation
    saveModel() {
        const modelData = this.exportModelData();
        console.log('Saving model:', modelData);
        this.showSuccess('模型已保存');
    }
    
    loadModel() {
        console.log('Loading model...');
        this.showSuccess('模型已加载');
    }
    
    exportModel() {
        const modelData = this.exportModelData();
        console.log('Exporting model:', modelData);
        this.showSuccess('模型已导出');
    }
    
    exportModelData() {
        return {
            components: Array.from(this.components.values()),
            connections: Array.from(this.connections.values()),
            metadata: {
                created: new Date().toISOString(),
                version: '1.0.0'
            }
        };
    }
    
    clearCanvas() {
        if (this.components.size === 0) {
            this.showError('画布已经是空的');
            return;
        }
        
        if (confirm('确定要清空画布吗？这将删除所有组件。')) {
            this.components.clear();
            this.connections.clear();
            this.canvas.querySelectorAll('.canvas-node').forEach(node => node.remove());
            this.svg.innerHTML = '';
            this.deselectComponent();
            this.announce('画布已清空');
            this.updateStatus('画布已清空');
        }
    }
    
    zoomIn() {
        // Implement zoom functionality
        this.announce('放大画布');
    }
    
    zoomOut() {
        // Implement zoom functionality
        this.announce('缩小画布');
    }
    
    resetView() {
        // Implement view reset
        this.announce('重置视图');
    }
    
    showHelp() {
        this.showToast('按F1查看帮助，Ctrl+S保存，F5运行模拟', 'info');
    }
    
    loadExamples() {
        // Load example configurations
        console.log('Loading examples...');
    }
    
    loadExample(e) {
        const exampleType = e.target.dataset.example;
        console.log('Loading example:', exampleType);
        this.showSuccess(`已加载${e.target.textContent}示例`);
    }
    
    addDataSource(e) {
        e.preventDefault();
        const formData = new FormData(e.target);
        console.log('Adding data source:', Object.fromEntries(formData));
        this.showSuccess('数据源已添加');
    }
    
    browseFile() {
        // Implement file browser
        console.log('Opening file browser...');
    }
    
    updateComponentSelect(components) {
        const select = document.getElementById('component-select');
        if (!select) return;
        
        select.innerHTML = '<option value="">选择组件</option>';
        
        for (const [id, component] of Object.entries(components)) {
            const option = document.createElement('option');
            option.value = id;
            option.textContent = `${this.getComponentDisplayName(component.type)} (${id})`;
            select.appendChild(option);
        }
    }
    
    updateVariableSelect(e) {
        const componentId = e.target.value;
        const variableSelect = document.getElementById('variable-select');
        
        if (!variableSelect || !componentId || !this.simulationResults) return;
        
        const component = this.simulationResults.components[componentId];
        if (!component) return;
        
        variableSelect.innerHTML = '<option value="">选择变量</option>';
        
        for (const variable of Object.keys(component.variables)) {
            const option = document.createElement('option');
            option.value = variable;
            option.textContent = variable;
            variableSelect.appendChild(option);
        }
    }
    
    plotSelected() {
        const componentId = document.getElementById('component-select')?.value;
        const variable = document.getElementById('variable-select')?.value;
        
        if (!componentId || !variable) {
            this.showError('请选择组件和变量');
            return;
        }
        
        console.log('Plotting:', componentId, variable);
        this.showSuccess('图表已生成');
    }
    
    exportData() {
        if (!this.simulationResults) {
            this.showError('没有可导出的数据');
            return;
        }
        
        console.log('Exporting data...');
        this.showSuccess('数据已导出');
    }
    
    importData() {
        console.log('Importing data...');
        this.showSuccess('数据已导入');
    }
    
    exportLog() {
        const logContent = document.getElementById('log-content')?.textContent;
        if (!logContent) {
            this.showError('没有可导出的日志');
            return;
        }
        
        console.log('Exporting log...');
        this.showSuccess('日志已导出');
    }
    
    // Additional helper methods
    updateComponentDisplay(id) {
        const element = document.getElementById(id);
        const component = this.components.get(id);
        
        if (element && component) {
            // Update visual representation if needed
            console.log('Updating component display:', id);
        }
    }
    
    removeComponentConnections(id) {
        // Remove all connections involving this component
        for (const [connId, connection] of this.connections) {
            if (connection.from === id || connection.to === id) {
                this.connections.delete(connId);
                // Remove visual connection line
                const line = document.getElementById(`connection_${connId}`);
                if (line) line.remove();
            }
        }
    }
    
    showContextMenu(x, y) {
        // Implement context menu
        console.log('Showing context menu at:', x, y);
    }
    
    copyComponent() {
        if (this.selectedComponent) {
            console.log('Copying component:', this.selectedComponent);
            this.announce('组件已复制');
        }
    }
    
    pasteComponent() {
        console.log('Pasting component...');
        this.announce('组件已粘贴');
    }
    
    editComponentProperties(id) {
        this.selectComponent(id);
        const firstInput = document.querySelector('#properties-content input, #properties-content select');
        if (firstInput) {
            firstInput.focus();
        }
    }
}

// Initialize the application
let app;
document.addEventListener('DOMContentLoaded', function() {
    app = new HydrologyApp();
    
    // Make app globally available for inline event handlers
    window.app = app;
});

// Export for module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = HydrologyApp;
}