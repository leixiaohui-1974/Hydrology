/**
 * 二维地图可视化的JavaScript文件
 *
 * 该文件包含初始化和更新Leaflet地图的所有逻辑，
 * 用于显示二维水力模型的结果。
 *
 * 处理:
 * - 地图初始化和瓦片图层
 * - 渲染二维网格（三角形）
 * - 根据水深对网格进行着色
 * - 显示颜色图例
 * - 绘制速度矢量
 * - 处理用户交互（例如，点击单元格）
 */

// --- 地图状态变量 ---
let leafletMap = null;     // 主要的Leaflet地图对象
let meshLayer = null;      // 用于网格多边形的Leaflet要素组
let meshFaceLayers = [];   // 保存每个单独多边形图层的数组
let velocityLayer = null;  // 用于速度箭头的Leaflet图层组

// --- 二维地图可视化函数 ---

/**
 * 初始化Leaflet地图实例
 * 应用程序加载时调用此函数一次。它设置基本地图瓦片并创建速度矢量的图层组。
 * 它使用MutationObserver确保仅在地图容器选项卡可见时初始化地图，以防止大小问题。
 */
function initialize2DMap() {
    const mapContainer = document.getElementById('leaflet-map');
    if (mapContainer && leafletMap === null) {
        // 使用MutationObserver仅在选项卡可见时初始化地图
        const observer = new MutationObserver((mutationsList, obs) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    if (mapContainer.parentElement.classList.contains('active')) {
                        leafletMap = L.map('leaflet-map').setView([40.7128, -74.0060], 13);
                        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                            maxZoom: 19,
                            attribution: '© OpenStreetMap贡献者'
                        }).addTo(leafletMap);
                        velocityLayer = L.layerGroup().addTo(leafletMap);
                        obs.disconnect(); // 地图初始化后停止观察
                    }
                }
            }
        });
        observer.observe(mapContainer.parentElement, { attributes: true });
    }
}

function getColor(d, min_d, max_d) {
    // 计算强度，确保在0到1之间
    const intensity = Math.max(0, Math.min(1, (d - min_d) / (max_d - min_d + 1e-9)));
    // 从蓝色（低）到浅蓝色（高）插值颜色
    const r = 150 - Math.floor(intensity * 150);
    const g = 150 - Math.floor(intensity * 150);
    const b = 255;
    return `rgb(${r}, ${g}, ${b})`;
}

function updateLegend(min_d, max_d) {
    const legend = document.getElementById('map-legend');
    legend.innerHTML = '<strong>水深 (米)</strong><br>';
    const steps = 5;
    for (let i = 0; i < steps; i++) {
        const value = min_d + (max_d - min_d) * i / (steps - 1);
        const color = getColor(value, min_d, max_d);
        legend.innerHTML +=
            `<div class="legend-item">` +
            `<div class="legend-color" style="background-color:${color}"></div>` +
            `<span>${value.toFixed(2)}</span>` +
            `</div>`;
    }
}

function updateMapColors(timestep, simulationResults, nodeDataStore) {
    if (!simulationResults || meshFaceLayers.length === 0) return;

    let result2d = null;
    for (const compName in simulationResults) {
        const nodeId = Object.keys(nodeDataStore).find(id => nodeDataStore[id].name === compName);
        if (nodeId && nodeDataStore[nodeId].type === 'HydraulicModel2D') {
            result2d = simulationResults[compName];
            break;
        }
    }
    if (!result2d) return;

    const h_data = result2d.h[timestep];
    const max_h = Math.max(...h_data);
    const min_h = 0; // 假设最小深度为0

    meshFaceLayers.forEach((layer, i) => {
        if (h_data[i] !== undefined) {
            const depth = h_data[i];
            layer.setStyle({
                fillColor: getColor(depth, min_h, max_h),
                fillOpacity: depth > 0.001 ? 0.6 : 0.0 // 如果深度可忽略不计则透明
            });
        }
    });
    document.getElementById('time-label').textContent = timestep;
    updateLegend(min_h, max_h);
    drawVelocityArrows(timestep, result2d, nodeDataStore);
}

function drawVelocityArrows(timestep, result2d) {
    if (!velocityLayer) return;
    velocityLayer.clearLayers();

    const u_data = result2d.u[timestep];
    const v_data = result2d.v[timestep];
    const h_data = result2d.h[timestep];

    const points = result2d.points;
    const triangles = result2d.triangles;

    // 箭头长度的简单缩放因子。这可能需要调整。
    const arrowScale = 0.5;

    for (let i = 0; i < triangles.length; i++) {
        // 仅对具有显著深度的单元格绘制箭头
        if (h_data[i] > 0.1) {
            const u = u_data[i];
            const v = v_data[i];
            const speed = Math.sqrt(u * u + v * v);

            if (speed > 0.01) {
                const triangle = triangles[i];
                // 计算三角形的质心
                const p1 = points[triangle[0]];
                const p2 = points[triangle[1]];
                const p3 = points[triangle[2]];
                const centroid_lon = (p1[0] + p2[0] + p3[0]) / 3;
                const centroid_lat = (p1[1] + p2[1] + p3[1]) / 3;

                // 计算箭头的终点
                const end_lat = centroid_lat + v * arrowScale * 0.0001;
                const end_lon = centroid_lon + u * arrowScale * 0.0001;

                const arrow = L.polyline(
                    [L.latLng(centroid_lat, centroid_lon), L.latLng(end_lat, end_lon)],
                    { color: 'black', weight: 1 }
                );
                velocityLayer.addLayer(arrow);
            }
        }
    }
}

function render2DMesh(result2d, simulationResults, nodeDataStore) {
    if (!leafletMap) return;
    if (meshLayer) {
        leafletMap.removeLayer(meshLayer);
    }
    meshFaceLayers = [];

    const points = result2d.points;
    const triangles = result2d.triangles;

    meshFaceLayers = triangles.map((triangle, i) => {
        const p1 = L.latLng(points[triangle[0]][1], points[triangle[0]][0]);
        const p2 = L.latLng(points[triangle[1]][1], points[triangle[1]][0]);
        const p3 = L.latLng(points[triangle[2]][1], points[triangle[2]][0]);
        const polygon = L.polygon([p1, p2, p3], { color: '#3498db', weight: 1 });

        polygon.on('click', () => {
            const timestep = parseInt(document.getElementById('time-slider').value, 10);
            const h_data = result2d.h[timestep];
            const depth = h_data[i];
            const popupContent = `<b>水深:</b> ${depth.toFixed(3)} 米`;
            L.popup()
                .setLatLng(polygon.getBounds().getCenter())
                .setContent(popupContent)
                .openOn(leafletMap);
        });

        return polygon;
    });

    meshLayer = L.featureGroup(meshFaceLayers).addTo(leafletMap);
    // 调整地图以适应网格边界
    setTimeout(() => {
        if (meshLayer.getBounds().isValid()) {
            leafletMap.fitBounds(meshLayer.getBounds().pad(0.1));
        }
    }, 100); // 延迟以确保地图准备就绪
}

/**
 * 在地图上渲染二维模拟结果的主函数
 * 这是所有二维可视化更新的入口点
 *
 * @param {object} results - 来自后端的完整模拟结果对象
 * @param {object} nodeDataStore - 前端的节点数据存储
 */
function render2DResults(results, nodeDataStore) {
    let result2d = null;
    // 查找二维模型组件的特定结果
    for (const compName in results) {
        const nodeId = Object.keys(nodeDataStore).find(id => nodeDataStore[id].name === compName);
        if (nodeId && nodeDataStore[nodeId].type === 'HydraulicModel2D') {
            result2d = results[compName];
            break;
        }
    }
    // 如果没有二维结果，则隐藏地图控件
    if (!result2d) {
        document.getElementById('map-controls').style.display = 'none';
        return;
    }

    // 显示控件并渲染网格
    document.getElementById('map-controls').style.display = 'flex';
    render2DMesh(result2d, results, nodeDataStore);

    // 根据时间步数配置时间滑块
    const slider = document.getElementById('time-slider');
    const num_steps = result2d.h.length;
    slider.max = num_steps > 0 ? num_steps - 1 : 0;
    slider.value = 0;
    // 添加监听器以在移动滑块时更新地图颜色
    slider.addEventListener('input', (e) => updateMapColors(parseInt(e.target.value, 10), results, nodeDataStore));

    // 为第一个时间步执行初始着色
    updateMapColors(0, results, nodeDataStore);
}