document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const paletteItems = document.querySelectorAll('.component-item');
    const canvas = document.getElementById('canvas');
    const svg = document.getElementById('connections-svg');
    const propertiesContent = document.getElementById('properties-content');
    const plottingControls = document.getElementById('plotting-controls');
    const componentSelect = document.getElementById('component-select');
    const variableSelect = document.getElementById('variable-select');
    const plotButton = document.getElementById('plot-button');
    const saveButton = document.getElementById('save-button');
    const runButton = document.getElementById('run-button');
    const exportButton = document.getElementById('export-button');
    const logContent = document.getElementById('log-content');
    const chartCanvas = document.getElementById('live-chart');

    // --- State Variables ---
    let nodeIdCounter = 0;
    let sourceNodeForConnection = null;
    let selectedNode = null;
    const nodeDataStore = {};
    const connections = [];
    let liveChart;
    let simulationResults = null;

    // --- Initial Setup ---
    initializeChart();
    setupArrowheadMarker();

    // --- Event Listeners ---
    paletteItems.forEach(item => item.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', e.target.dataset.type)));
    canvas.addEventListener('dragover', e => e.preventDefault());
    canvas.addEventListener('drop', e => { e.preventDefault(); createNode(e.dataTransfer.getData('text/plain'), e.clientX, e.clientY); });
    canvas.addEventListener('click', clearSelection);
    saveButton.addEventListener('click', handleSave);
    runButton.addEventListener('click', handleRun);
    plotButton.addEventListener('click', handlePlot);
    componentSelect.addEventListener('change', updateVariableSelect);
    // Note: The export button is not fully wired up in this pass.
    // The get_results function was repurposed for plotting.

    // --- Eel functions exposed to Python ---
    eel.expose(update_status, 'update_status');
    function update_status(status) {
        logContent.textContent += `Step ${status.step}/${status.num_steps} | Final Outflow: ${status.final_outflow.toFixed(3)}\n`;
        logContent.scrollTop = logContent.scrollHeight;
        addDataToChart(liveChart, status.step, status.final_outflow);
    }

    eel.expose(simulation_finished, 'simulation_finished');
    function simulation_finished(result) {
        const message = result.error ? `ERROR: ${result.error}` : `SUCCESS: ${result.message}`;
        logContent.textContent += `${message}\n`;
        logContent.scrollTop = logContent.scrollHeight;
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                renderPlottingControls();
            }
        });
    }

    // --- Main UI Functions ---
    function handleRun() {
        logContent.textContent = 'Starting simulation...\n';
        simulationResults = null;
        plottingControls.style.display = 'none';
        propertiesContent.style.display = 'block';
        resetChart(liveChart, 'Live: Final Component Outflow (m^3/s)');
        eel.start_simulation('examples/config_coupled.yaml')().then(response => {
            logContent.textContent += `${response}\n`;
        });
    }

    function handleSave() {
        const dataToSend = { nodes: nodeDataStore, connections: connections };
        eel.save_config_to_yaml(dataToSend)(response => alert(response));
    }

    function handlePlot() {
        const compName = componentSelect.value;
        const varName = variableSelect.value;
        if (!compName || !varName || !simulationResults) return;

        const data = simulationResults[compName][varName];
        const labels = Array.from({ length: data.length }, (_, i) => i + 1);
        let plotData = data;
        let plotLabel = `${compName} - ${varName}`;

        if (Array.isArray(data[0])) {
            plotData = data.map(timeStepData => timeStepData[timeStepData.length - 1]);
            plotLabel += ' (Last Node)';
        }

        resetChart(liveChart, plotLabel);
        addDataToChart(liveChart, labels, plotData);
    }

    function renderPlottingControls() {
        plottingControls.style.display = 'block';
        propertiesContent.style.display = 'none';
        componentSelect.innerHTML = '';
        Object.keys(simulationResults).forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            componentSelect.appendChild(option);
        });
        updateVariableSelect();
    }

    function updateVariableSelect() {
        const compName = componentSelect.value;
        variableSelect.innerHTML = '';
        if (!compName || !simulationResults[compName]) return;
        Object.keys(simulationResults[compName]).forEach(varName => {
            const option = document.createElement('option');
            option.value = varName;
            option.textContent = varName;
            variableSelect.appendChild(option);
        });
    }

    // --- Node and Property Functions ---
    function createNode(type, x, y) { /* ... implementation ... */ }
    function handleNodeClick(event) { /* ... implementation ... */ }
    function createConnection(sourceNode, targetNode) { /* ... implementation ... */ }
    function renderProperties(nodeId) { /* ... implementation ... */ }
    function clearSelection() { /* ... implementation ... */ }
    function getDefaultParams(type) { /* ... implementation ... */ }
    function createPropertyInput(label, key, dataObject, type) { /* ... implementation ... */ }
    function setupArrowheadMarker() { /* ... implementation ... */ }

    // (Paste full implementations here to be safe)
    function createNode(type, x, y) { nodeIdCounter++; const nodeId = `node-${nodeIdCounter}`; const nodeName = `${type}_${nodeIdCounter}`; nodeDataStore[nodeId] = { id: nodeId, name: nodeName, type: type, params: getDefaultParams(type) }; const nodeEl = document.createElement('div'); nodeEl.className = 'canvas-node'; nodeEl.id = nodeId; nodeEl.textContent = nodeName; const canvasRect = canvas.getBoundingClientRect(); nodeEl.style.left = `${x - canvasRect.left - 60}px`; nodeEl.style.top = `${y - canvasRect.top - 25}px`; nodeEl.addEventListener('click', handleNodeClick); canvas.appendChild(nodeEl); }
    function handleNodeClick(event) { event.stopPropagation(); const clickedNodeEl = event.target; if (sourceNodeForConnection) { if (sourceNodeForConnection !== clickedNodeEl) createConnection(sourceNodeForConnection, clickedNodeEl); sourceNodeForConnection.classList.remove('selected-source'); sourceNodeForConnection = null; } else { if (selectedNode) selectedNode.classList.remove('selected'); selectedNode = clickedNodeEl; selectedNode.classList.add('selected'); renderProperties(selectedNode.id); } }
    function createConnection(sourceNode, targetNode) { connections.push({ from: sourceNode.id, to: targetNode.id }); const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); const sourceRect = sourceNode.getBoundingClientRect(); const targetRect = targetNode.getBoundingClientRect(); const canvasRect = canvas.getBoundingClientRect(); const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left; const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top; const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left; const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top; line.setAttribute('x1', x1); line.setAttribute('y1', y1); line.setAttribute('x2', x2); line.setAttribute('y2', y2); line.setAttribute('stroke', 'black'); line.setAttribute('stroke-width', '2'); line.setAttribute('marker-end', 'url(#arrowhead)'); svg.appendChild(line); }
    function renderProperties(nodeId) { propertiesContent.innerHTML = ''; plottingControls.style.display = 'none'; propertiesContent.style.display = 'block'; if (!nodeId) { propertiesContent.innerHTML = '<p>Select a component to see its properties.</p>'; return; } const nodeData = nodeDataStore[nodeId]; propertiesContent.appendChild(createPropertyInput('Name', 'name', nodeData, 'text')); for (const key in nodeData.params) { propertiesContent.appendChild(createPropertyInput(key, key, nodeData.params, 'number')); } }
    function clearSelection() { if (selectedNode) selectedNode.classList.remove('selected'); if (sourceNodeForConnection) sourceNodeForConnection.classList.remove('selected-source'); selectedNode = null; sourceNodeForConnection = null; renderProperties(null); if (simulationResults) { renderPlottingControls(); } }
    function getDefaultParams(type) { switch(type) { case 'RiverReach': return { slope: 0.001, manning_n: 0.03, length: 1000, width: 20 }; case 'Catchment': return { CN: 75 }; case 'Gate': return { opening_height: 1.0, width: 10, C_d: 0.6 }; case 'Pump': return { a: -0.05, b: 0, c: 5.0 }; case 'Junction': return {}; default: return {}; } }
    function createPropertyInput(label, key, dataObject, type) { const row = document.createElement('div'); row.className = 'property-row'; const labelEl = document.createElement('label'); labelEl.textContent = label.replace(/_/g, ' '); const inputEl = document.createElement('input'); inputEl.type = type; inputEl.value = dataObject[key]; inputEl.addEventListener('change', (e) => { dataObject[key] = (type === 'number') ? parseFloat(e.target.value) : e.target.value; if (key === 'name') document.getElementById(dataObject.id).textContent = e.target.value; }); row.appendChild(labelEl); row.appendChild(inputEl); return row; }
    function setupArrowheadMarker() { const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker'); marker.setAttribute('id', 'arrowhead'); marker.setAttribute('viewBox', '0 0 10 10'); marker.setAttribute('refX', '8'); marker.setAttribute('refY', '5'); marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6'); marker.setAttribute('orient', 'auto-start-reverse'); const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z'); marker.appendChild(path); defs.appendChild(marker); svg.appendChild(defs); }

    // --- Charting Functions ---
    function initializeChart() { const ctx = chartCanvas.getContext('2d'); liveChart = new Chart(ctx, { type: 'line', data: { labels: [], datasets: [{ label: 'Final Component Outflow (m^3/s)', data: [], borderColor: 'rgb(75, 192, 192)', tension: 0.1 }] }, options: { responsive: true, maintainAspectRatio: false, scales: { x: { title: { display: true, text: 'Time Step' } }, y: { title: { display: true, text: 'Discharge (m^3/s)' } } } } }); }
    function addDataToChart(chart, label, data) { if (Array.isArray(label)) { chart.data.labels = label; } else { chart.data.labels.push(label); } if (Array.isArray(data)) { chart.data.datasets[0].data = data; } else { chart.data.datasets[0].data.push(data); } chart.update(); }
    function resetChart(chart, newLabel) { chart.data.labels = []; chart.data.datasets.forEach((dataset) => { dataset.data = []; dataset.label = newLabel; }); chart.update(); }
});
