/**
 * 建模工具的主JavaScript文件
 *
 * 该文件处理:
 * - 用户界面的初始化，包括组件库、画布和属性面板
 * - 创建模型组件的拖放功能
 * - 应用程序状态的管理（节点、连接、属性）
 * - 通过Eel库与Python后端的通信
 * - 触发模拟并处理结果以进行绘图
 * - 基于用户交互和模拟状态的UI更新
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- 全局状态变量 ---
    // 这些变量保存用户模型网络的完整状态
    let nodeDataStore = {}; // 存储每个节点（组件）的属性和元数据
    let connections = [];   // 存储节点之间的连接
    let simulationResults = null; // 存储上次模拟运行的结果
    let timeSeriesChart = null; // 时间序列图表实例
    let profileChart = null; // 剖面图表实例

    // --- 初始设置和事件监听器 ---
    // 该部分负责设置UI的初始状态并附加所有必要的事件监听器以进行用户交互

    // 初始化用于二维可视化的Leaflet地图
    initialize2DMap();

    // 设置在画布上创建组件的拖放功能
    // ... (拖放监听器的代码)

    // 设置按钮（运行、保存等）和其他UI元素的监听器
    // ... (其他事件监听器的代码)

    // 添加示例选择面板的事件监听器
    setupExampleSelection();

    // 添加操作提示功能
    setupTooltips();

    // 设置图表控制面板事件监听器
    setupChartControls();

    // 初始化底部标签页图表
    initializeBottomCharts();

    // --- Eel暴露的函数和回调 ---
    // 这些函数暴露给Python后端，在后端事件（例如模拟完成）响应时调用以更新前端

    /**
     * 当后端完成模拟时触发的回调函数
     * @param {object} result - 来自后端的对象，可能包含成功或错误消息
     */
    eel.expose(simulation_finished, 'simulation_finished');
    function simulation_finished(result) {
        if (result.error) {
            console.error("模拟失败:", result.error);
            showTooltip("模拟失败: " + result.error, "error");
            // 在此处更新UI以显示错误消息
            return;
        }
        console.log("模拟成功完成。正在获取结果...");
        showTooltip("模拟成功完成！", "success");
        // 模拟完成后，我们请求完整的結果对象
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                // 使用新结果更新UI
                renderPlottingControls(); // 填充用于绘图的下拉菜单
                render2DResults(results, nodeDataStore); // 渲染二维地图可视化
                updateBottomCharts(); // 更新底部图表
            }
        });
    }

    // ... (文件的其余部分，包括所有其他用于UI管理的函数)
});

/**
 * 设置示例选择面板的事件监听器
 */
function setupExampleSelection() {
    // 为每个示例项添加点击事件监听器
    const exampleItems = document.querySelectorAll('.example-item');
    exampleItems.forEach(item => {
        item.addEventListener('click', function() {
            const exampleName = this.getAttribute('data-example');
            showExampleDetails(exampleName);
            showTooltip("已选择示例: " + getExampleTitle(exampleName), "info");
        });
    });

    // 为运行示例按钮添加点击事件监听器
    const runExampleButton = document.getElementById('run-example-button');
    if (runExampleButton) {
        runExampleButton.addEventListener('click', runSelectedExample);
    }

    // 为可视化结果按钮添加点击事件监听器
    const visualizeExampleButton = document.getElementById('visualize-example-button');
    if (visualizeExampleButton) {
        visualizeExampleButton.addEventListener('click', visualizeExampleResults);
    }
}

/**
 * 获取示例标题
 * @param {string} exampleName - 示例名称
 * @returns {string} 示例标题
 */
function getExampleTitle(exampleName) {
    const titles = {
        'scs_example': 'SCS曲线号数法',
        'xaj_example': '新安江模型',
        'hymod_example': 'Hymod模型',
        '1d_hydraulic_example': '一维水力模型',
        '2d_hydraulic_example': '二维水力模型',
        'hydraulic_features_example': '水工建筑物',
        'coupled_model_example': '耦合网络模型',
        'looped_network_example': '环状网络模型',
        'areal_precipitation_example': '面降雨计算',
        'data_assimilation_example': '数据同化',
        'ml_integration_example': '机器学习集成'
    };
    return titles[exampleName] || exampleName;
}

/**
 * 显示示例详情
 * @param {string} exampleName - 示例名称
 */
function showExampleDetails(exampleName) {
    // 隐藏其他面板，显示示例详情面板
    document.getElementById('properties-content').style.display = 'none';
    document.getElementById('plotting-controls').style.display = 'none';
    document.getElementById('example-details-pane').style.display = 'block';

    // 获取示例描述元素
    const descriptionElement = document.getElementById('example-description');
    
    // 根据示例名称设置描述
    const exampleDescriptions = {
        'scs_example': `
            <h4>SCS曲线号数法</h4>
            <p>这是一个使用SCS曲线号数法计算径流的简单水文模型示例。SCS曲线号数法是一种经验方法，用于估算给定降雨事件的径流量。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>流域组件使用SCS曲线号数法产流模块</li>
                <li>简单河道汇流模块</li>
            </ul>
            <p><strong>输入数据:</strong></p>
            <ul>
                <li>降雨数据</li>
                <li>潜在蒸散发数据</li>
            </ul>
            <p><strong>应用场景:</strong></p>
            <ul>
                <li>小流域径流估算</li>
                <li>水利工程设计</li>
                <li>洪水风险评估</li>
            </ul>
        `,
        'xaj_example': `
            <h4>新安江模型</h4>
            <p>这是一个使用新安江产流模块的水文模型示例。新安江模型是中国开发的分布式水文模型，广泛应用于湿润地区的径流预报。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>流域组件使用新安江产流模块</li>
                <li>简单汇流模块</li>
            </ul>
            <p><strong>输入数据:</strong></p>
            <ul>
                <li>降雨数据</li>
                <li>潜在蒸散发数据</li>
            </ul>
            <p><strong>特点:</strong></p>
            <ul>
                <li>三水源结构</li>
                <li>土壤蓄水容量分布曲线</li>
                <li>适合湿润地区</li>
            </ul>
        `,
        'hymod_example': `
            <h4>Hymod模型</h4>
            <p>这是一个使用Hymod产流模块的水文模型示例。Hymod是一个概念性水文模型，具有简单的结构但能很好地模拟径流过程。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>流域组件使用Hymod产流模块</li>
            </ul>
            <p><strong>输入数据:</strong></p>
            <ul>
                <li>降雨数据</li>
                <li>潜在蒸散发数据</li>
            </ul>
            <p><strong>优势:</strong></p>
            <ul>
                <li>参数少，易于率定</li>
                <li>结构简单，计算效率高</li>
                <li>适用于教学和研究</li>
            </ul>
        `,
        '1d_hydraulic_example': `
            <h4>一维水力模型</h4>
            <p>这是一个一维水力模型示例，使用Preissmann方法求解圣维南方程组。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>一维水力模型组件</li>
            </ul>
            <p><strong>输入数据:</strong></p>
            <ul>
                <li>上游边界条件（水位或流量）</li>
                <li>下游边界条件（水位或流量）</li>
            </ul>
            <p><strong>应用:</strong></p>
            <ul>
                <li>河道洪水演进计算</li>
                <li>水库调度模拟</li>
                <li>水质传输模拟</li>
            </ul>
        `,
        '2d_hydraulic_example': `
            <h4>二维水力模型</h4>
            <p>这是一个二维水力模型示例，用于模拟平面二维水流。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>二维水力模型组件</li>
            </ul>
            <p><strong>输入数据:</strong></p>
            <ul>
                <li>地形数据</li>
                <li>边界条件</li>
            </ul>
            <p><strong>特点:</strong></p>
            <ul>
                <li>非结构化网格</li>
                <li>浅水方程求解</li>
                <li>适用于复杂地形</li>
            </ul>
        `,
        'hydraulic_features_example': `
            <h4>水工建筑物</h4>
            <p>这是一个包含水工建筑物（如闸门、泵站）的水力模型示例。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>一维水力模型组件</li>
                <li>闸门结构</li>
                <li>泵站结构</li>
            </ul>
            <p><strong>功能:</strong></p>
            <ul>
                <li>闸门控制策略</li>
                <li>泵站运行调度</li>
                <li>联合调度优化</li>
            </ul>
        `,
        'coupled_model_example': `
            <h4>耦合网络模型</h4>
            <p>这是一个水文-水力耦合模型示例，将流域产流模型与河道汇流模型耦合。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>水文模型组件（流域）</li>
                <li>水力模型组件（河道）</li>
            </ul>
            <p><strong>连接关系:</strong></p>
            <ul>
                <li>流域产流连接到河道汇流</li>
            </ul>
            <p><strong>优势:</strong></p>
            <ul>
                <li>物理过程完整</li>
                <li>预测精度高</li>
                <li>适用于复杂流域</li>
            </ul>
        `,
        'looped_network_example': `
            <h4>环状网络模型</h4>
            <p>这是一个具有环状拓扑结构的复杂网络模型示例。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>多个水力模型组件</li>
            </ul>
            <p><strong>连接关系:</strong></p>
            <ul>
                <li>形成环状连接的复杂网络</li>
            </ul>
            <p><strong>应用:</strong></p>
            <ul>
                <li>城市排水系统</li>
                <li>复杂河网模拟</li>
                <li>管网优化设计</li>
            </ul>
        `,
        'areal_precipitation_example': `
            <h4>面降雨计算</h4>
            <p>这是一个面降雨计算示例，演示如何从点雨量数据计算面平均降雨量。</p>
            <p><strong>模型组件:</strong></p>
            <ul>
                <li>多个流域组件</li>
            </ul>
            <p><strong>功能特性:</strong></p>
            <ul>
                <li>泰森多边形法</li>
                <li>反距离权重法</li>
                <li>克里金插值法</li>
            </ul>
            <p><strong>用途:</strong></p>
            <ul>
                <li>提高降雨输入精度</li>
                <li>支持分布式水文模型</li>
                <li>优化模型参数率定</li>
            </ul>
        `,
        'data_assimilation_example': `
            <h4>数据同化</h4>
            <p>这是一个数据同化示例，演示如何将观测数据同化到模型中以提高预测精度。</p>
            <p><strong>功能特性:</strong></p>
            <ul>
                <li>EnKF（集合卡尔曼滤波）</li>
                <li>粒子滤波</li>
                <li>多源数据融合</li>
            </ul>
            <p><strong>优势:</strong></p>
            <ul>
                <li>实时修正模型状态</li>
                <li>提高预报准确性</li>
                <li>降低不确定性</li>
            </ul>
        `,
        'ml_integration_example': `
            <h4>机器学习集成</h4>
            <p>这是一个机器学习集成示例，演示如何将机器学习方法集成到水文建模中。</p>
            <p><strong>功能特性:</strong></p>
            <ul>
                <li>深度学习模型</li>
                <li>传统机器学习方法</li>
                <li>特征工程</li>
                <li>模型训练和评估</li>
            </ul>
            <p><strong>应用:</strong></p>
            <ul>
                <li>径流预测</li>
                <li>参数优化</li>
                <li>异常检测</li>
            </ul>
        `
    };

    // 设置示例描述
    descriptionElement.innerHTML = exampleDescriptions[exampleName] || `<h4>${getExampleTitle(exampleName)}</h4><p>示例描述暂不可用。</p>`;
    
    // 保存当前选中的示例名称
    document.getElementById('example-details-pane').setAttribute('data-selected-example', exampleName);
    
    // 显示可视化按钮（仅对部分示例可用）
    const visualizeButton = document.getElementById('visualize-example-button');
    const examplesWithVisualization = ['2d_hydraulic_example', '1d_hydraulic_example'];
    if (visualizeButton) {
        if (examplesWithVisualization.includes(exampleName)) {
            visualizeButton.style.display = 'block';
        } else {
            visualizeButton.style.display = 'none';
        }
    }
}

/**
 * 运行选中的示例
 */
function runSelectedExample() {
    // 获取当前选中的示例名称
    const examplePane = document.getElementById('example-details-pane');
    const exampleName = examplePane.getAttribute('data-selected-example');
    
    if (!exampleName) {
        console.error("没有选中的示例");
        showTooltip("请先选择一个示例", "warning");
        return;
    }
    
    // 禁用运行按钮并显示加载状态
    const runButton = document.getElementById('run-example-button');
    runButton.disabled = true;
    runButton.textContent = '运行中...';
    
    // 隐藏之前的结果
    document.getElementById('example-results').style.display = 'none';
    
    showTooltip("正在运行示例: " + getExampleTitle(exampleName) + "，请稍候...", "info");
    
    // 调用Python后端运行示例
    eel.exposed_run_example(exampleName)((result) => {
        // 恢复运行按钮
        runButton.disabled = false;
        runButton.textContent = '运行示例';
        
        // 处理结果
        if (result.error) {
            // 显示错误信息
            document.getElementById('example-results-content').innerHTML = `
                <div class="error-message">
                    <h5>运行错误</h5>
                    <p>${result.error}</p>
                </div>
            `;
            document.getElementById('example-results').style.display = 'block';
            showTooltip("示例运行失败: " + result.error, "error");
        } else {
            // 显示成功信息和结果
            let resultsHtml = `
                <div class="success-message">
                    <h5>运行成功</h5>
                    <p>${result.message}</p>
                </div>
            `;
            
            // 显示组件信息
            if (result.components && result.components.length > 0) {
                resultsHtml += `
                    <div class="components-info">
                        <h5>模型组件</h5>
                        <ul>
                            ${result.components.map(comp => `<li>${comp}</li>`).join('')}
                        </ul>
                    </div>
                `;
            }
            
            // 显示结果摘要
            if (result.results) {
                resultsHtml += `
                    <div class="results-summary">
                        <h5>结果摘要</h5>
                        <p>模拟已完成，共生成 ${Object.keys(result.results).length} 个组件的结果。</p>
                        <p>点击"可视化结果"按钮查看详细可视化。</p>
                    </div>
                `;
                
                // 显示详细结果
                resultsHtml += `
                    <div class="results-details">
                        <h5>详细结果</h5>
                `;
                
                // 遍历每个组件的结果
                for (const [compName, compResults] of Object.entries(result.results)) {
                    resultsHtml += `
                        <div class="component-results">
                            <h6>组件: ${compName}</h6>
                    `;
                    
                    // 显示该组件的所有变量
                    for (const [varName, varData] of Object.entries(compResults)) {
                        // 如果是数组且有数据
                        if (Array.isArray(varData) && varData.length > 0) {
                            // 如果是二维数组（时间序列数据）
                            if (Array.isArray(varData[0])) {
                                resultsHtml += `
                                    <div class="variable-data">
                                        <strong>${varName}:</strong> ${varData.length} 个时间步的数据
                                    </div>
                                `;
                            } else {
                                // 一维数组，显示统计信息
                                const min = Math.min(...varData);
                                const max = Math.max(...varData);
                                const avg = varData.reduce((a, b) => a + b, 0) / varData.length;
                                resultsHtml += `
                                    <div class="variable-data">
                                        <strong>${varName}:</strong> 最小值: ${min.toFixed(4)}, 最大值: ${max.toFixed(4)}, 平均值: ${avg.toFixed(4)}
                                    </div>
                                `;
                            }
                        } else if (typeof varData === "number") {
                            resultsHtml += `
                                <div class="variable-data">
                                    <strong>${varName}:</strong> ${varData.toFixed(4)}
                                </div>
                            `;
                        } else {
                            resultsHtml += `
                                <div class="variable-data">
                                    <strong>${varName}:</strong> ${varData}
                                </div>
                            `;
                        }
                    }
                    
                    resultsHtml += `
                        </div>
                    `;
                }
                
                resultsHtml += `
                    </div>
                `;
            }
            
            document.getElementById('example-results-content').innerHTML = resultsHtml;
            document.getElementById('example-results').style.display = 'block';
            showTooltip("示例运行成功！", "success");
        }
    });
}

/**
 * 可视化示例结果
 */
function visualizeExampleResults() {
    // 获取当前选中的示例名称
    const examplePane = document.getElementById('example-details-pane');
    const exampleName = examplePane.getAttribute('data-selected-example');
    
    if (!exampleName) {
        console.error("没有选中的示例");
        showTooltip("请先选择一个示例", "warning");
        return;
    }
    
    // 检查是否有结果可以可视化
    if (!simulationResults) {
        showTooltip("请先运行示例以生成结果", "warning");
        return;
    }
    
    // 根据示例类型进行不同的可视化
    switch (exampleName) {
        case '2d_hydraulic_example':
            // 切换到底部的二维地图面板
            switchToTab('map-pane');
            showTooltip("已切换到二维地图可视化", "info");
            break;
        case '1d_hydraulic_example':
            // 切换到底部的时间序列面板
            switchToTab('time-series-pane');
            showTooltip("已切换到时间序列可视化", "info");
            break;
        default:
            showTooltip("该示例暂不支持可视化", "info");
    }
}

/**
 * 切换到底部指定的标签页
 * @param {string} tabId - 标签页ID
 */
function switchToTab(tabId) {
    // 隐藏所有标签页
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    
    // 显示指定标签页
    const targetPane = document.getElementById(tabId);
    if (targetPane) {
        targetPane.classList.add('active');
    }
    
    // 更新标签按钮状态
    document.querySelectorAll('.tab-button').forEach(button => {
        button.classList.remove('active');
        if (button.getAttribute('data-tab') === tabId) {
            button.classList.add('active');
        }
    });
}

/**
 * 设置操作提示功能
 */
function setupTooltips() {
    // 创建提示元素
    const tooltip = document.createElement('div');
    tooltip.className = 'tooltip';
    tooltip.id = 'global-tooltip';
    document.body.appendChild(tooltip);
}

/**
 * 显示操作提示
 * @param {string} message - 提示信息
 * @param {string} type - 提示类型 (info, success, warning, error)
 */
function showTooltip(message, type = 'info') {
    const tooltip = document.getElementById('global-tooltip');
    if (!tooltip) return;
    
    // 设置提示内容和样式
    tooltip.textContent = message;
    tooltip.className = 'tooltip ' + type;
    
    // 显示提示
    tooltip.classList.add('show');
    
    // 3秒后自动隐藏
    setTimeout(() => {
        tooltip.classList.remove('show');
    }, 3000);
}

/**
 * 设置图表控制面板事件监听器
 */
function setupChartControls() {
    // 时间序列图表类型选择
    const timeSeriesChartType = document.getElementById('time-series-chart-type');
    const timeSeriesRefresh = document.getElementById('time-series-refresh');
    
    if (timeSeriesChartType && timeSeriesRefresh) {
        timeSeriesChartType.addEventListener('change', function() {
            showTooltip("时间序列图表类型已更改为: " + this.options[this.selectedIndex].text, "info");
            updateTimeSeriesChart();
        });
        
        timeSeriesRefresh.addEventListener('click', function() {
            showTooltip("正在刷新时间序列图表...", "info");
            updateTimeSeriesChart();
        });
    }
    
    // 剖面图表类型选择
    const profileChartType = document.getElementById('profile-chart-type');
    const profileRefresh = document.getElementById('profile-refresh');
    
    if (profileChartType && profileRefresh) {
        profileChartType.addEventListener('change', function() {
            showTooltip("剖面图表类型已更改为: " + this.options[this.selectedIndex].text, "info");
            updateProfileChart();
        });
        
        profileRefresh.addEventListener('click', function() {
            showTooltip("正在刷新剖面图表...", "info");
            updateProfileChart();
        });
    }
    
    // 右侧面板的图表类型选择
    const chartTypeSelect = document.getElementById('chart-type-select');
    const plotButton = document.getElementById('plot-button');
    
    if (chartTypeSelect && plotButton) {
        chartTypeSelect.addEventListener('change', function() {
            showTooltip("图表类型已更改为: " + this.options[this.selectedIndex].text, "info");
        });
        
        plotButton.addEventListener('click', function() {
            const selectedType = chartTypeSelect.value;
            showTooltip("正在绘制" + chartTypeSelect.options[chartTypeSelect.selectedIndex].text + "...", "info");
            plotSelectedData();
        });
    }
}

/**
 * 初始化底部标签页图表
 */
function initializeBottomCharts() {
    // 为时间序列图表添加事件监听器
    const timeSeriesChartType = document.getElementById('time-series-chart-type');
    const timeSeriesRefresh = document.getElementById('time-series-refresh');
    
    if (timeSeriesChartType && timeSeriesRefresh) {
        timeSeriesRefresh.addEventListener('click', function() {
            updateTimeSeriesChart();
        });
    }
    
    // 为剖面图表添加事件监听器
    const profileChartType = document.getElementById('profile-chart-type');
    const profileRefresh = document.getElementById('profile-refresh');
    
    if (profileChartType && profileRefresh) {
        profileRefresh.addEventListener('click', function() {
            updateProfileChart();
        });
    }
    
    // 为标签按钮添加事件监听器
    document.querySelectorAll('.tab-button').forEach(button => {
        button.addEventListener('click', function() {
            const tabId = this.getAttribute('data-tab');
            switchToTab(tabId);
        });
    });
}

/**
 * 更新时间序列图表
 */
function updateTimeSeriesChart() {
    if (!simulationResults) {
        showTooltip("没有可用的模拟结果", "warning");
        return;
    }
    
    const chartType = document.getElementById('time-series-chart-type').value;
    
    // 获取第一个组件和变量作为示例数据
    let firstComponent, firstVariable;
    for (const compName in simulationResults) {
        firstComponent = compName;
        for (const varName in simulationResults[compName]) {
            firstVariable = varName;
            break;
        }
        if (firstVariable) break;
    }
    
    if (!firstComponent || !firstVariable) {
        showTooltip("没有找到可绘制的数据", "warning");
        return;
    }
    
    const data = simulationResults[firstComponent][firstVariable];
    
    // 准备图表数据
    let chartData, labels;
    if (Array.isArray(data[0])) {
        // 二维数组，时间序列数据
        labels = data.map((_, index) => index);
        chartData = data.map(arr => arr.length > 0 ? arr[0] : 0);
    } else {
        // 一维数组
        labels = data.map((_, index) => index);
        chartData = data;
    }
    
    const ctx = document.getElementById('time-series-chart').getContext('2d');
    
    // 如果已有图表实例，先销毁
    if (window.timeSeriesChart) {
        window.timeSeriesChart.destroy();
    }
    
    // 根据图表类型创建图表
    const chartConfig = {
        type: chartType === 'area' ? 'line' : chartType,
        data: {
            labels: labels,
            datasets: [{
                label: `${firstComponent} - ${firstVariable}`,
                data: chartData,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: chartType === 'area' ? 'rgba(54, 162, 235, 0.2)' : undefined,
                tension: 0.1,
                fill: chartType === 'area'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false
                }
            }
        }
    };
    
    window.timeSeriesChart = new Chart(ctx, chartConfig);
    showTooltip("时间序列图表已更新", "info");
}

/**
 * 更新剖面图表
 */
function updateProfileChart() {
    if (!simulationResults) {
        showTooltip("没有可用的模拟结果", "warning");
        return;
    }
    
    const chartType = document.getElementById('profile-chart-type').value;
    
    // 获取第一个组件和变量作为示例数据
    let firstComponent, firstVariable;
    for (const compName in simulationResults) {
        firstComponent = compName;
        for (const varName in simulationResults[compName]) {
            firstVariable = varName;
            break;
        }
        if (firstVariable) break;
    }
    
    if (!firstComponent || !firstVariable) {
        showTooltip("没有找到可绘制的数据", "warning");
        return;
    }
    
    const data = simulationResults[firstComponent][firstVariable];
    
    // 准备图表数据
    let chartData, labels;
    if (Array.isArray(data[0])) {
        // 二维数组，时间序列数据
        labels = data.map((_, index) => index);
        chartData = data.map(arr => arr.length > 0 ? arr[0] : 0);
    } else {
        // 一维数组
        labels = data.map((_, index) => index);
        chartData = data;
    }
    
    const ctx = document.getElementById('profile-chart').getContext('2d');
    
    // 如果已有图表实例，先销毁
    if (window.profileChart) {
        window.profileChart.destroy();
    }
    
    // 根据图表类型创建图表
    const chartConfig = {
        type: chartType,
        data: {
            labels: labels,
            datasets: [{
                label: `${firstComponent} - ${firstVariable}`,
                data: chartData,
                backgroundColor: chartType === 'bar' ? 'rgba(54, 162, 235, 0.6)' : undefined,
                borderColor: 'rgb(54, 162, 235)',
                borderWidth: 1,
                tension: chartType === 'line' ? 0.1 : undefined,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    };
    
    window.profileChart = new Chart(ctx, chartConfig);
    showTooltip("剖面图表已更新", "info");
}

/**
 * 更新底部所有图表
 */
function updateBottomCharts() {
    updateTimeSeriesChart();
    updateProfileChart();
}

/**
 * 填充用于绘图的下拉菜单
 */
function renderPlottingControls() {
    const componentSelect = document.getElementById('component-select');
    const variableSelect = document.getElementById('variable-select');
    
    // 清空现有选项
    componentSelect.innerHTML = '';
    variableSelect.innerHTML = '';
    
    // 如果没有模拟结果，隐藏绘图控件
    if (!simulationResults) {
        document.getElementById('plotting-controls').style.display = 'none';
        return;
    }
    
    // 显示绘图控件
    document.getElementById('plotting-controls').style.display = 'block';
    document.getElementById('properties-content').style.display = 'none';
    document.getElementById('example-details-pane').style.display = 'none';
    
    // 填充组件选择下拉菜单
    for (const compName in simulationResults) {
        const option = document.createElement('option');
        option.value = compName;
        option.textContent = compName;
        componentSelect.appendChild(option);
    }
    
    // 如果有组件，自动选择第一个并填充变量
    if (Object.keys(simulationResults).length > 0) {
        const firstComponent = Object.keys(simulationResults)[0];
        componentSelect.value = firstComponent;
        populateVariableSelect(firstComponent);
    }
    
    // 为组件选择添加事件监听器
    componentSelect.addEventListener('change', function() {
        populateVariableSelect(this.value);
    });
    
    // 为绘图按钮添加事件监听器
    document.getElementById('plot-button').addEventListener('click', plotSelectedData);
}

/**
 * 填充变量选择下拉菜单
 * @param {string} componentName - 组件名称
 */
function populateVariableSelect(componentName) {
    const variableSelect = document.getElementById('variable-select');
    variableSelect.innerHTML = '';
    
    if (!simulationResults || !simulationResults[componentName]) return;
    
    const componentData = simulationResults[componentName];
    for (const varName in componentData) {
        const option = document.createElement('option');
        option.value = varName;
        option.textContent = varName;
        variableSelect.appendChild(option);
    }
}

/**
 * 绘制选中的数据
 */
function plotSelectedData() {
    const componentSelect = document.getElementById('component-select');
    const variableSelect = document.getElementById('variable-select');
    const chartTypeSelect = document.getElementById('chart-type-select');
    
    const componentName = componentSelect.value;
    const variableName = variableSelect.value;
    const chartType = chartTypeSelect.value;
    
    if (!componentName || !variableName) {
        showTooltip("请选择组件和变量", "warning");
        return;
    }
    
    if (!simulationResults || !simulationResults[componentName] || !simulationResults[componentName][variableName]) {
        showTooltip("无法找到选中的数据", "error");
        return;
    }
    
    const data = simulationResults[componentName][variableName];
    
    // 根据图表类型绘制图表
    switch (chartType) {
        case 'line':
            drawLineChart(data, componentName, variableName);
            break;
        case 'bar':
            drawBarChart(data, componentName, variableName);
            break;
        case 'scatter':
            drawScatterChart(data, componentName, variableName);
            break;
        case 'area':
            drawAreaChart(data, componentName, variableName);
            break;
        default:
            drawLineChart(data, componentName, variableName);
    }
    
    showTooltip(`已绘制 ${componentName} 的 ${variableName} 数据`, "success");
}

/**
 * 绘制折线图
 * @param {Array} data - 数据数组
 * @param {string} componentName - 组件名称
 * @param {string} variableName - 变量名称
 */
function drawLineChart(data, componentName, variableName) {
    // 查找或创建图表容器
    let chartContainer = document.getElementById('preview-plot-container');
    if (!chartContainer) {
        chartContainer = document.createElement('div');
        chartContainer.id = 'preview-plot-container';
        chartContainer.style.width = '100%';
        chartContainer.style.height = '300px';
        document.getElementById('properties-pane').appendChild(chartContainer);
    }
    
    // 清空容器
    chartContainer.innerHTML = '<canvas id="preview-chart"></canvas>';
    
    const ctx = document.getElementById('preview-chart').getContext('2d');
    
    // 准备数据
    let chartData;
    let labels;
    
    if (Array.isArray(data[0])) {
        // 二维数组，假设是时间序列数据
        labels = data.map((_, index) => index);
        chartData = data.map(arr => arr.length > 0 ? arr[0] : 0); // 取第一个值
    } else {
        // 一维数组
        labels = data.map((_, index) => index);
        chartData = data;
    }
    
    // 如果已有图表实例，先销毁
    if (window.previewChart) {
        window.previewChart.destroy();
    }
    
    // 创建新图表
    window.previewChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `${componentName} - ${variableName}`,
                data: chartData,
                borderColor: 'rgb(54, 162, 235)',
                backgroundColor: 'rgba(54, 162, 235, 0.2)',
                tension: 0.1,
                fill: false
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false
                }
            }
        }
    });
}

/**
 * 绘制柱状图
 * @param {Array} data - 数据数组
 * @param {string} componentName - 组件名称
 * @param {string} variableName - 变量名称
 */
function drawBarChart(data, componentName, variableName) {
    // 查找或创建图表容器
    let chartContainer = document.getElementById('preview-plot-container');
    if (!chartContainer) {
        chartContainer = document.createElement('div');
        chartContainer.id = 'preview-plot-container';
        chartContainer.style.width = '100%';
        chartContainer.style.height = '300px';
        document.getElementById('properties-pane').appendChild(chartContainer);
    }
    
    // 清空容器
    chartContainer.innerHTML = '<canvas id="preview-chart"></canvas>';
    
    const ctx = document.getElementById('preview-chart').getContext('2d');
    
    // 准备数据
    let chartData;
    let labels;
    
    if (Array.isArray(data[0])) {
        // 二维数组，假设是时间序列数据
        labels = data.map((_, index) => index);
        chartData = data.map(arr => arr.length > 0 ? arr[0] : 0); // 取第一个值
    } else {
        // 一维数组
        labels = data.map((_, index) => index);
        chartData = data;
    }
    
    // 如果已有图表实例，先销毁
    if (window.previewChart) {
        window.previewChart.destroy();
    }
    
    // 创建新图表
    window.previewChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: `${componentName} - ${variableName}`,
                data: chartData,
                backgroundColor: 'rgba(54, 162, 235, 0.6)',
                borderColor: 'rgb(54, 162, 235)',
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

/**
 * 绘制散点图
 * @param {Array} data - 数据数组
 * @param {string} componentName - 组件名称
 * @param {string} variableName - 变量名称
 */
function drawScatterChart(data, componentName, variableName) {
    // 查找或创建图表容器
    let chartContainer = document.getElementById('preview-plot-container');
    if (!chartContainer) {
        chartContainer = document.createElement('div');
        chartContainer.id = 'preview-plot-container';
        chartContainer.style.width = '100%';
        chartContainer.style.height = '300px';
        document.getElementById('properties-pane').appendChild(chartContainer);
    }
    
    // 清空容器
    chartContainer.innerHTML = '<canvas id="preview-chart"></canvas>';
    
    const ctx = document.getElementById('preview-chart').getContext('2d');
    
    // 准备数据
    let chartData;
    
    if (Array.isArray(data[0])) {
        // 二维数组，假设是时间序列数据
        chartData = data.map((arr, index) => ({
            x: index,
            y: arr.length > 0 ? arr[0] : 0
        }));
    } else {
        // 一维数组
        chartData = data.map((value, index) => ({
            x: index,
            y: value
        }));
    }
    
    // 如果已有图表实例，先销毁
    if (window.previewChart) {
        window.previewChart.destroy();
    }
    
    // 创建新图表
    window.previewChart = new Chart(ctx, {
        type: 'scatter',
        data: {
            datasets: [{
                label: `${componentName} - ${variableName}`,
                data: chartData,
                backgroundColor: 'rgb(255, 99, 132)',
                borderColor: 'rgb(255, 99, 132)',
                pointRadius: 5,
                pointHoverRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: {
                    type: 'linear',
                    position: 'bottom'
                },
                y: {
                    beginAtZero: false
                }
            }
        }
    });
}

/**
 * 绘制面积图
 * @param {Array} data - 数据数组
 * @param {string} componentName - 组件名称
 * @param {string} variableName - 变量名称
 */
function drawAreaChart(data, componentName, variableName) {
    // 查找或创建图表容器
    let chartContainer = document.getElementById('preview-plot-container');
    if (!chartContainer) {
        chartContainer = document.createElement('div');
        chartContainer.id = 'preview-plot-container';
        chartContainer.style.width = '100%';
        chartContainer.style.height = '300px';
        document.getElementById('properties-pane').appendChild(chartContainer);
    }
    
    // 清空容器
    chartContainer.innerHTML = '<canvas id="preview-chart"></canvas>';
    
    const ctx = document.getElementById('preview-chart').getContext('2d');
    
    // 准备数据
    let chartData;
    let labels;
    
    if (Array.isArray(data[0])) {
        // 二维数组，假设是时间序列数据
        labels = data.map((_, index) => index);
        chartData = data.map(arr => arr.length > 0 ? arr[0] : 0); // 取第一个值
    } else {
        // 一维数组
        labels = data.map((_, index) => index);
        chartData = data;
    }
    
    // 如果已有图表实例，先销毁
    if (window.previewChart) {
        window.previewChart.destroy();
    }
    
    // 创建新图表
    window.previewChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: `${componentName} - ${variableName}`,
                data: chartData,
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.2)',
                tension: 0.1,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false
                }
            }
        }
    });
}

// 为所有按钮添加点击事件监听器以显示提示
document.addEventListener('click', function(e) {
    if (e.target.tagName === 'BUTTON') {
        const buttonText = e.target.textContent;
        if (buttonText) {
            showTooltip(buttonText + " 已点击", "info");
        }
    }
});