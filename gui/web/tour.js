/**
 * 新手引导功能JavaScript文件
 *
 * 该文件实现了一个交互式新手引导系统，帮助新用户了解如何使用水文建模工具。
 *
 * 功能包括:
 * - 分步骤引导用户了解界面各个部分
 * - 高亮显示当前引导的元素
 * - 提供说明文字和操作提示
 * - 支持跳过、前进、后退等操作
 */

// 引导步骤定义
const tourSteps = [
    {
        target: '#palette-pane',
        title: '欢迎使用水文建模工具',
        content: '这是一个交互式的新手引导，将帮助您快速了解如何使用本工具。点击"下一步"开始。',
        position: 'right'
    },
    {
        target: '.component-item[data-type="Catchment"]',
        title: '组件库',
        content: '这里是组件库，包含了所有可用的水文和水力模型组件。您可以将组件拖拽到画布上构建模型。',
        position: 'right'
    },
    {
        target: '#canvas',
        title: '网络画布',
        content: '这是网络画布，您可以在这里构建模型网络。将组件从左侧拖拽到这里，然后连接它们形成网络。',
        position: 'bottom'
    },
    {
        target: '#properties-pane',
        title: '属性面板',
        content: '当选中一个组件时，这里会显示该组件的属性设置。您可以修改组件的参数以满足您的建模需求。',
        position: 'left'
    },
    {
        target: '#run-button',
        title: '运行模拟',
        content: '当您完成模型构建和参数设置后，点击此按钮运行模拟。模拟结果将显示在底部的图表和地图中。',
        position: 'bottom'
    },
    {
        target: '#examples-pane',
        title: '示例库',
        content: '这里提供了多个预设示例，展示了不同类型的水文水力模型。您可以直接运行这些示例来学习如何构建模型。',
        position: 'right'
    },
    {
        target: '.example-item[data-example="scs_example"]',
        title: '示例模型',
        content: '点击任意示例可以查看其详细信息，然后点击"运行示例"按钮可以直接运行该模型。',
        position: 'right'
    },
    {
        target: '.tab-button[data-tab="time-series-pane"]',
        title: '结果可视化',
        content: '模拟完成后，您可以在这里查看结果图表。支持时间序列图、剖面图和二维地图等多种可视化方式。',
        position: 'top'
    },
    {
        target: '.tab-button[data-tab="map-pane"]',
        title: '二维地图可视化',
        content: '对于二维水力模型，结果将显示在地图上。您可以使用时间滑块查看不同时步的结果。',
        position: 'top'
    },
    {
        target: '#save-button',
        title: '保存和导出',
        content: '您可以保存您的模型配置，或导出结果数据以供进一步分析。',
        position: 'bottom'
    }
];

// 当前引导步骤索引
let currentStep = 0;

// 是否正在显示引导
let isTourActive = false;

/**
 * 初始化新手引导功能
 */
function initTour() {
    // 创建引导覆盖层
    const overlay = document.createElement('div');
    overlay.id = 'tour-overlay';
    overlay.className = 'tour-overlay';
    document.body.appendChild(overlay);
    
    // 创建引导弹窗
    const tourPopup = document.createElement('div');
    tourPopup.id = 'tour-popup';
    tourPopup.className = 'tour-popup';
    tourPopup.innerHTML = `
        <div class="tour-header">
            <h3 id="tour-title">新手引导</h3>
            <button id="tour-close" class="tour-close">&times;</button>
        </div>
        <div class="tour-content">
            <p id="tour-text">欢迎使用水文建模工具！</p>
        </div>
        <div class="tour-progress">
            <span id="tour-progress-text">1 / 10</span>
        </div>
        <div class="tour-actions">
            <button id="tour-prev" class="btn-secondary" disabled>上一步</button>
            <button id="tour-next" class="btn-primary">下一步</button>
            <button id="tour-skip" class="btn-secondary">跳过引导</button>
        </div>
    `;
    document.body.appendChild(tourPopup);
    
    // 添加事件监听器
    document.getElementById('tour-close').addEventListener('click', stopTour);
    document.getElementById('tour-prev').addEventListener('click', prevStep);
    document.getElementById('tour-next').addEventListener('click', nextStep);
    document.getElementById('tour-skip').addEventListener('click', skipTour);
    
    // 检查是否是首次访问
    if (!localStorage.getItem('hydrology-tour-completed')) {
        startTour();
    }
}

/**
 * 开始新手引导
 */
function startTour() {
    isTourActive = true;
    currentStep = 0;
    document.getElementById('tour-overlay').style.display = 'block';
    showStep(currentStep);
}

/**
 * 结束新手引导
 */
function stopTour() {
    isTourActive = false;
    document.getElementById('tour-overlay').style.display = 'none';
    document.getElementById('tour-popup').style.display = 'none';
    hideHighlight();
}

/**
 * 跳过新手引导
 */
function skipTour() {
    stopTour();
    localStorage.setItem('hydrology-tour-completed', 'true');
}

/**
 * 显示指定步骤
 * @param {number} stepIndex - 步骤索引
 */
function showStep(stepIndex) {
    if (stepIndex < 0 || stepIndex >= tourSteps.length) return;
    
    const step = tourSteps[stepIndex];
    const targetElement = document.querySelector(step.target);
    
    if (!targetElement) {
        console.warn(`无法找到引导目标元素: ${step.target}`);
        return;
    }
    
    // 更新弹窗内容
    document.getElementById('tour-title').textContent = step.title;
    document.getElementById('tour-text').textContent = step.content;
    document.getElementById('tour-progress-text').textContent = `${stepIndex + 1} / ${tourSteps.length}`;
    
    // 更新按钮状态
    document.getElementById('tour-prev').disabled = stepIndex === 0;
    document.getElementById('tour-next').textContent = stepIndex === tourSteps.length - 1 ? '完成引导' : '下一步';
    
    // 显示弹窗
    const popup = document.getElementById('tour-popup');
    popup.style.display = 'block';
    
    // 定位弹窗
    positionPopup(targetElement, popup, step.position);
    
    // 高亮目标元素
    highlightElement(targetElement);
}

/**
 * 定位引导弹窗
 * @param {Element} targetElement - 目标元素
 * @param {Element} popup - 弹窗元素
 * @param {string} position - 位置 (top, right, bottom, left)
 */
function positionPopup(targetElement, popup, position) {
    const targetRect = targetElement.getBoundingClientRect();
    const popupRect = popup.getBoundingClientRect();
    
    let top, left;
    
    switch (position) {
        case 'top':
            top = targetRect.top - popupRect.height - 10;
            left = targetRect.left + (targetRect.width - popupRect.width) / 2;
            break;
        case 'right':
            top = targetRect.top + (targetRect.height - popupRect.height) / 2;
            left = targetRect.right + 10;
            break;
        case 'bottom':
            top = targetRect.bottom + 10;
            left = targetRect.left + (targetRect.width - popupRect.width) / 2;
            break;
        case 'left':
            top = targetRect.top + (targetRect.height - popupRect.height) / 2;
            left = targetRect.left - popupRect.width - 10;
            break;
        default:
            // 默认定位在右侧
            top = targetRect.top + (targetRect.height - popupRect.height) / 2;
            left = targetRect.right + 10;
    }
    
    // 确保弹窗在视窗内
    if (left < 10) left = 10;
    if (left + popupRect.width > window.innerWidth - 10) left = window.innerWidth - popupRect.width - 10;
    if (top < 10) top = 10;
    if (top + popupRect.height > window.innerHeight - 10) top = window.innerHeight - popupRect.height - 10;
    
    popup.style.top = `${top}px`;
    popup.style.left = `${left}px`;
}

/**
 * 高亮显示目标元素
 * @param {Element} element - 要高亮的元素
 */
function highlightElement(element) {
    hideHighlight();
    
    // 创建高亮遮罩
    const highlight = document.createElement('div');
    highlight.className = 'tour-highlight';
    highlight.id = 'tour-highlight';
    
    const rect = element.getBoundingClientRect();
    highlight.style.position = 'fixed';
    highlight.style.top = `${rect.top - 5}px`;
    highlight.style.left = `${rect.left - 5}px`;
    highlight.style.width = `${rect.width + 10}px`;
    highlight.style.height = `${rect.height + 10}px`;
    highlight.style.zIndex = '9999';
    highlight.style.pointerEvents = 'none';
    highlight.style.boxShadow = '0 0 0 9999px rgba(0, 0, 0, 0.5)';
    highlight.style.borderRadius = '4px';
    
    document.body.appendChild(highlight);
}

/**
 * 隐藏高亮
 */
function hideHighlight() {
    const highlight = document.getElementById('tour-highlight');
    if (highlight) {
        highlight.remove();
    }
}

/**
 * 前一步
 */
function prevStep() {
    if (currentStep > 0) {
        currentStep--;
        showStep(currentStep);
    }
}

/**
 * 下一步
 */
function nextStep() {
    if (currentStep < tourSteps.length - 1) {
        currentStep++;
        showStep(currentStep);
    } else {
        // 完成引导
        finishTour();
    }
}

/**
 * 完成引导
 */
function finishTour() {
    stopTour();
    localStorage.setItem('hydrology-tour-completed', 'true');
    alert('恭喜！您已完成新手引导。现在您可以开始使用水文建模工具了！');
}

// 页面加载完成后初始化引导
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化以确保所有元素都已加载
    setTimeout(initTour, 1000);
});