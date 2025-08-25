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
            // 在此处更新UI以显示错误消息
            return;
        }
        console.log("模拟成功完成。正在获取结果...");
        // 模拟完成后，我们请求完整的結果对象
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                // 使用新结果更新UI
                renderPlottingControls(); // 填充用于绘图的下拉菜单
                render2DResults(results, nodeDataStore); // 渲染二维地图可视化
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
        });
    });

    // 为运行示例按钮添加点击事件监听器
    const runExampleButton = document.getElementById('run-example-button');
    if (runExampleButton) {
        runExampleButton.addEventListener('click', runSelectedExample);
    }
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
        `
    };

    // 设置示例描述
    descriptionElement.innerHTML = exampleDescriptions[exampleName] || `<h4>${exampleName}</h4><p>示例描述暂不可用。</p>`;
    
    // 保存当前选中的示例名称
    document.getElementById('example-details-pane').setAttribute('data-selected-example', exampleName);
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
        return;
    }
    
    // 禁用运行按钮并显示加载状态
    const runButton = document.getElementById('run-example-button');
    runButton.disabled = true;
    runButton.textContent = '运行中...';
    
    // 隐藏之前的结果
    document.getElementById('example-results').style.display = 'none';
    
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
        }
    });
}