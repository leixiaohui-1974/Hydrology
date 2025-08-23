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
    const timeSeriesChartCanvas = document.getElementById('time-series-chart');
    const profileChartCanvas = document.getElementById('profile-chart');
    const tabButtons = document.querySelectorAll('.tab-button');
    const rainfallTypeSelect = document.getElementById('rainfall-type-select');
    const interpolationOptions = document.getElementById('interpolation-options');
    const interpolationMethodSelect = document.getElementById('interpolation-method-select');
    const methodParametersContainer = document.getElementById('method-parameters');
    const previewButton = document.getElementById('preview-button');
    const previewPlot = document.getElementById('preview-plot');
    const baseflowSourceSelect = document.getElementById('baseflow-source-select');
    const browseSubbasinsButton = document.getElementById('browse-subbasins');
    const subbasinsFilePathInput = document.getElementById('subbasins-file-path');
    const browseGaugesButton = document.getElementById('browse-gauges');
    const gaugesFilePathInput = document.getElementById('gauges-file-path');
    const dataSourceList = document.getElementById('data-source-list');
    const newSourceNameInput = document.getElementById('new-source-name');
    const newSourcePathInput = document.getElementById('new-source-path');
    const browseNewSourceButton = document.getElementById('browse-new-source');
    const addSourceButton = document.getElementById('add-source-button');

    // --- State Variables ---
    let nodeIdCounter = 0;
    let sourceNodeForConnection = null;
    let selectedNode = null;
    const nodeDataStore = {};
    const connections = [];
    let timeSeriesChart; // Renamed from liveChart
    let profileChart;
    let simulationResults = null;
    let nameToIdMap = {}; // New map for quick lookup
    const dataSourcesStore = {};
    const monitoredComponents = {}; // New: To store { nodeId: ['var1', 'var2'], ... }
    const chartColors = [
        'rgb(75, 192, 192)', 'rgb(255, 99, 132)', 'rgb(54, 162, 235)',
        'rgb(255, 206, 86)', 'rgb(153, 102, 255)', 'rgb(255, 159, 64)'
    ];

    // --- Initial Setup ---
    initializeCharts();
    setupArrowheadMarker();

    // --- Event Listeners ---
    tabButtons.forEach(button => button.addEventListener('click', handleTabClick));
    paletteItems.forEach(item => item.addEventListener('dragstart', e => e.dataTransfer.setData('text/plain', e.target.dataset.type)));
    canvas.addEventListener('dragover', e => e.preventDefault());
    canvas.addEventListener('drop', e => { e.preventDefault(); createNode(e.dataTransfer.getData('text/plain'), e.clientX, e.clientY); });
    canvas.addEventListener('click', clearSelection);
    saveButton.addEventListener('click', handleSave);
    runButton.addEventListener('click', handleRun);
    plotButton.addEventListener('click', handlePlot);
    componentSelect.addEventListener('change', updateVariableSelect);
    rainfallTypeSelect.addEventListener('change', handleRainfallTypeChange);
    interpolationMethodSelect.addEventListener('change', renderMethodParameters);
    // Note: The export button is not fully wired up in this pass.
    // The get_results function was repurposed for plotting.

    // --- Initial UI State ---
    handleRainfallTypeChange(); // Set initial state
    renderMethodParameters(); // Set initial state

    // --- Main Event Listeners ---
    previewButton.addEventListener('click', handlePreview);
    browseSubbasinsButton.addEventListener('click', () => handleBrowseClick(subbasinsFilePathInput));
    browseGaugesButton.addEventListener('click', () => handleBrowseClick(gaugesFilePathInput));
    browseNewSourceButton.addEventListener('click', () => handleBrowseClick(newSourcePathInput));
    addSourceButton.addEventListener('click', handleAddDataSource);


    // --- Eel functions exposed to Python ---
    eel.expose(update_status, 'update_status');
    function update_status(status) {
        // This function now only updates the text log. Plotting is handled by update_live_data.
        logContent.textContent += `Step ${status.step}/${status.num_steps} | Final Outflow: ${status.final_outflow.toFixed(3)}\n`;
        logContent.scrollTop = logContent.scrollHeight;
    }

    eel.expose(update_live_data, 'update_live_data');
    function update_live_data(data) {
        if (!data) return;

        // Determine the node type to decide which chart to use
        const nodeId = nameToIdMap[data.component_id];
        if (!nodeId) return; // Component not found in map
        const nodeType = nodeDataStore[nodeId].type;

        // Routing logic: Z and Q for river-like models go to the profile chart
        // Everything else goes to the time series chart.
        const isProfileVariable = (data.variable === 'Z' || data.variable === 'Q');
        const isRiverComponent = (nodeType === 'RiverReach' || nodeType === 'HydraulicModel');

        if (isProfileVariable && isRiverComponent) {
            // --- Logic for Profile Chart ---
            if (profileChart === null) return;

            const datasetLabel = `${data.component_id} - ${data.variable}`;
            let dataset = profileChart.data.datasets.find(ds => ds.label === datasetLabel);

            if (!dataset) {
                const colorIndex = profileChart.data.datasets.length % chartColors.length;
                dataset = {
                    label: datasetLabel,
                    data: [],
                    borderColor: chartColors[colorIndex],
                    tension: 0.1,
                    fill: false
                };
                profileChart.data.datasets.push(dataset);
            }

            // Generate X-axis labels (distance)
            const params = nodeDataStore[nodeId].params;
            const num_nodes = data.value.length;
            const length = params.length || 1000; // Default length if not specified
            const dx = length / (num_nodes > 1 ? num_nodes - 1 : 1);
            const x_labels = Array.from({length: num_nodes}, (_, i) => (i * dx).toFixed(0));

            // For profiles, we replace the data, not append
            dataset.data = data.value;
            profileChart.data.labels = x_labels;
            profileChart.update();

        } else {
            // --- Logic for Time Series Chart ---
            if (timeSeriesChart === null) return;

            const datasetLabel = `${data.component_id} - ${data.variable}`;
            let dataset = timeSeriesChart.data.datasets.find(ds => ds.label === datasetLabel);

            if (!dataset) {
                const colorIndex = timeSeriesChart.data.datasets.length % chartColors.length;
                dataset = {
                    label: datasetLabel,
                    data: [],
                    borderColor: chartColors[colorIndex],
                    tension: 0.1,
                    fill: false
                };
                timeSeriesChart.data.datasets.push(dataset);
            }

            const timeLabel = (data.time_step + 1).toString();
            if (timeSeriesChart.data.labels.length <= data.time_step) {
                 timeSeriesChart.data.labels.push(timeLabel);
            }

            let value = data.value;
            if (Array.isArray(value)) {
                value = value[value.length - 1];
            }

            dataset.data.push(value);
            timeSeriesChart.update();
        }
    }

    eel.expose(simulation_finished, 'simulation_finished');
    function simulation_finished(result) {
        const message = result.error ? `ERROR: ${result.error}` : `SUCCESS: ${result.message}`;
        logContent.textContent += `${message}\n`;
        logContent.scrollTop = logContent.scrollHeight;

        // Clear monitoring state
        for (const nodeId in monitoredComponents) {
            delete monitoredComponents[nodeId];
            updateNodeVisuals(nodeId, false);
        }

        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                renderPlottingControls();
            }
        });
    }

    // --- Main UI Functions ---
    function gatherUIData() {
        const guiData = {
            nodes: nodeDataStore,
            connections: connections,
            monitored_components: monitoredComponents, // Add monitored components to payload
            sim_params: {
                dt_seconds: 60, // Hardcoded for now
                num_steps: 100  // Hardcoded for now
            },
            data_sources: dataSourcesStore, // Use the new dynamic store
            global_inputs: [], // This will be constructed on the backend now
            areal_precipitation: {},
            preprocessing: {}
        };

        // Gather Areal Precipitation settings
        const arealPrecipInput = document.getElementById('areal-precip-input-select').value;
        if (arealPrecipInput) {
             guiData.areal_precipitation = {
                input_name: arealPrecipInput,
                output_name: `${arealPrecipInput}_areal`,
                subbasins_shapefile: document.getElementById('subbasins-file-path').value,
                rain_gauges_file: document.getElementById('gauges-file-path').value,
                method: document.getElementById('interpolation-method-select').value,
                parameters: {} // Simplified for now
            };
        }

        // Gather Preprocessing settings
        const baseflowInput = document.getElementById('baseflow-source-select').value;
        if (baseflowInput) {
            guiData.preprocessing = {
                baseflow_separation: {
                    flow_input: baseflowInput,
                    output_baseflow: `${baseflowInput}_base`,
                    output_quickflow: `${baseflowInput}_quick`,
                    parameters: {
                        alpha: parseFloat(document.getElementById('baseflow-alpha-input').value)
                    }
                }
            };
        }

        return guiData;
    }

    function handleRun() {
        logContent.textContent = 'Starting simulation...\n';
        simulationResults = null;
        plottingControls.style.display = 'none';
        propertiesContent.style.display = 'block';

        // Clear the charts completely for the new live data
        timeSeriesChart.data.labels = [];
        timeSeriesChart.data.datasets = [];
        timeSeriesChart.update();

        profileChart.data.labels = [];
        profileChart.data.datasets = [];
        profileChart.update();

        // Build the name -> id map for the upcoming run
        nameToIdMap = {};
        for (const nodeId in nodeDataStore) {
            nameToIdMap[nodeDataStore[nodeId].name] = nodeId;
        }

        const guiData = gatherUIData();

        // Call the backend with the complete GUI data structure
        eel.start_simulation(guiData)().then(response => {
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

        // Post-simulation plotting will use the time series chart for now
        resetChart(timeSeriesChart, plotLabel);
        addDataToChart(timeSeriesChart, labels, plotData);
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
    function renderProperties(nodeId) {
        propertiesContent.innerHTML = '';
        plottingControls.style.display = 'none';
        propertiesContent.style.display = 'block';
        if (!nodeId) {
            propertiesContent.innerHTML = '<p>Select a component to see its properties.</p>';
            return;
        }

        const nodeData = nodeDataStore[nodeId];
        propertiesContent.appendChild(createPropertyInput('Name', 'name', nodeData, 'text'));

        // Special handling for HydrologicalModel to add a data source dropdown
        if (nodeData.type === 'HydrologicalModel') {
            const row = document.createElement('div');
            row.className = 'property-row';
            const labelEl = document.createElement('label');
            labelEl.textContent = 'Rainfall Source';
            const selectEl = document.createElement('select');

            const sourceNames = Object.keys(dataSourcesStore);
            sourceNames.forEach(name => {
                const option = document.createElement('option');
                option.value = name;
                option.textContent = name;
                selectEl.appendChild(option);
            });

            // Set the current value if it exists
            if (nodeData.params.rainfall_source) {
                selectEl.value = nodeData.params.rainfall_source;
            }

            selectEl.addEventListener('change', (e) => {
                nodeData.params.rainfall_source = e.target.value;
            });

            row.appendChild(labelEl);
            row.appendChild(selectEl);
            propertiesContent.appendChild(row);
        }

        // Render other parameters
        for (const key in nodeData.params) {
            // Don't create a standard input for the one we just handled
            if (key === 'rainfall_source') continue;
            propertiesContent.appendChild(createPropertyInput(key, key, nodeData.params, 'number'));
        }
    }
    function clearSelection() { /* ... implementation ... */ }
    function getDefaultParams(type) { /* ... implementation ... */ }
    function createPropertyInput(label, key, dataObject, type) { /* ... implementation ... */ }
    function setupArrowheadMarker() { /* ... implementation ... */ }

    // --- Preprocessing UI Functions ---
    function handlePreview() {
        console.log("Preview button clicked.");
        // For now, hardcode the file path. A real implementation would get this
        // from a file input or a list of loaded data sources.
        const flowDataSource = 'data/observed_flow.csv';
        const alphaValue = parseFloat(document.getElementById('baseflow-alpha-input').value);

        const config = {
            baseflow: {
                flow_data_path: flowDataSource,
                alpha: alphaValue
            }
        };

        // Clear previous plot and show a loading message
        previewPlot.src = "";
        previewPlot.alt = "Running preprocessing...";

        eel.run_preprocessing_preview(config)().then(result => {
            if (result.error) {
                alert(`Error: ${result.error}`);
                previewPlot.alt = "An error occurred.";
            } else {
                console.log("Received plot path:", result.plot_path);
                // The path is relative to the web folder
                // Add a timestamp to the URL to force the browser to reload the image
                previewPlot.src = `${result.plot_path}?t=${new Date().getTime()}`;
                previewPlot.alt = "Baseflow separation preview plot";
            }
        });
    }

    // --- Data Source UI Functions ---
    function handleAddDataSource() {
        const name = newSourceNameInput.value;
        const path = newSourcePathInput.value;
        if (!name || !path) {
            alert("Please provide both a name and a file path for the data source.");
            return;
        }
        if (dataSourcesStore[name]) {
            alert(`A data source with the name "${name}" already exists.`);
            return;
        }
        dataSourcesStore[name] = { file: path };
        newSourceNameInput.value = '';
        newSourcePathInput.value = '';
        renderDataSources();
    }

    function renderDataSources() {
        dataSourceList.innerHTML = '';
        const sourceNames = Object.keys(dataSourcesStore);

        // Update the dropdowns that use these sources
        const selectsToUpdate = [
            document.getElementById('areal-precip-input-select'),
            document.getElementById('baseflow-source-select')
        ];

        selectsToUpdate.forEach(select => {
            if (select) {
                const currentVal = select.value;
                select.innerHTML = '';
                sourceNames.forEach(name => {
                    const option = document.createElement('option');
                    option.value = name;
                    option.textContent = name;
                    select.appendChild(option);
                });
                select.value = currentVal;
            }
        });
    }

    async function handleBrowseClick(inputElement) {
        try {
            const path = await eel.open_file_dialog()();
            if (path) {
                inputElement.value = path;
            }
        } catch (e) {
            console.error("Error opening file dialog:", e);
            alert("Could not open file dialog. This feature may not work in all environments.");
        }
    }

    function handleRainfallTypeChange() {
        if (rainfallTypeSelect.value === 'interpolated') {
            interpolationOptions.classList.remove('hidden');
        } else {
            interpolationOptions.classList.add('hidden');
        }
    }

    function renderMethodParameters() {
        const method = interpolationMethodSelect.value;
        methodParametersContainer.innerHTML = ''; // Clear existing params

        if (method === 'idw') {
            methodParametersContainer.appendChild(
                createPropertyInput('Power', 'power', { power: 2 }, 'number')
            );
        } else if (method === 'thiessen') {
            methodParametersContainer.appendChild(
                createPropertyInput('Cache File', 'cache_file', { cache_file: 'thiessen_weights.json' }, 'text')
            );
        } else if (method === 'kriging') {
            const variogramInput = createPropertyInput('Variogram Model', 'variogram_model', { variogram_model: 'linear' }, 'text');
            const resolutionInput = createPropertyInput('Grid Resolution', 'grid_resolution', { grid_resolution: 10 }, 'number');
            methodParametersContainer.appendChild(variogramInput);
            methodParametersContainer.appendChild(resolutionInput);
        }
    }

    function handleNodeRightClick(event) {
        event.preventDefault(); // Prevent default context menu
        const nodeId = event.target.id;
        const isMonitored = monitoredComponents.hasOwnProperty(nodeId);

        if (isMonitored) {
            delete monitoredComponents[nodeId];
            updateNodeVisuals(nodeId, false);
            console.log(`Stopped monitoring ${nodeId}`);
        } else {
            const nodeType = nodeDataStore[nodeId].type;
            monitoredComponents[nodeId] = getDefaultMonitorVars(nodeType);
            updateNodeVisuals(nodeId, true);
            console.log(`Started monitoring ${nodeId} for variables: ${monitoredComponents[nodeId]}`);
        }
    }

    function getDefaultMonitorVars(type) {
        // Define default variables to monitor for each component type
        switch(type) {
            case 'RiverReach':
            case 'HydraulicModel': // Assuming this is the new name
                return ['Q', 'Z']; // Flow and Water Level Profile
            case 'Catchment':
            case 'HydrologicalModel':
                return ['get_outflow']; // Use method name
            case 'Junction':
            case 'Gate':
            case 'Pump':
                return ['get_outflow'];
            default:
                return [];
        }
    }

    function updateNodeVisuals(nodeId, isMonitored) {
        const nodeEl = document.getElementById(nodeId);
        if (nodeEl) {
            if (isMonitored) {
                nodeEl.classList.add('monitored');
            } else {
                nodeEl.classList.remove('monitored');
            }
        }
    }

    // (Paste full implementations here to be safe)
    function createNode(type, x, y) { nodeIdCounter++; const nodeId = `node-${nodeIdCounter}`; const nodeName = `${type}_${nodeIdCounter}`; nodeDataStore[nodeId] = { id: nodeId, name: nodeName, type: type, params: getDefaultParams(type) }; const nodeEl = document.createElement('div'); nodeEl.className = 'canvas-node'; nodeEl.id = nodeId; nodeEl.textContent = nodeName; const canvasRect = canvas.getBoundingClientRect(); nodeEl.style.left = `${x - canvasRect.left - 60}px`; nodeEl.style.top = `${y - canvasRect.top - 25}px`; nodeEl.addEventListener('click', handleNodeClick); nodeEl.addEventListener('contextmenu', handleNodeRightClick); canvas.appendChild(nodeEl); }
    function handleNodeClick(event) { event.stopPropagation(); const clickedNodeEl = event.target; if (sourceNodeForConnection) { if (sourceNodeForConnection !== clickedNodeEl) createConnection(sourceNodeForConnection, clickedNodeEl); sourceNodeForConnection.classList.remove('selected-source'); sourceNodeForConnection = null; } else { if (selectedNode) selectedNode.classList.remove('selected'); selectedNode = clickedNodeEl; selectedNode.classList.add('selected'); renderProperties(selectedNode.id); } }
    function createConnection(sourceNode, targetNode) { connections.push({ from: sourceNode.id, to: targetNode.id }); const line = document.createElementNS('http://www.w3.org/2000/svg', 'line'); const sourceRect = sourceNode.getBoundingClientRect(); const targetRect = targetNode.getBoundingClientRect(); const canvasRect = canvas.getBoundingClientRect(); const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left; const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top; const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left; const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top; line.setAttribute('x1', x1); line.setAttribute('y1', y1); line.setAttribute('x2', x2); line.setAttribute('y2', y2); line.setAttribute('stroke', 'black'); line.setAttribute('stroke-width', '2'); line.setAttribute('marker-end', 'url(#arrowhead)'); svg.appendChild(line); }
    function renderProperties(nodeId) { propertiesContent.innerHTML = ''; plottingControls.style.display = 'none'; propertiesContent.style.display = 'block'; if (!nodeId) { propertiesContent.innerHTML = '<p>Select a component to see its properties.</p>'; return; } const nodeData = nodeDataStore[nodeId]; propertiesContent.appendChild(createPropertyInput('Name', 'name', nodeData, 'text')); for (const key in nodeData.params) { propertiesContent.appendChild(createPropertyInput(key, key, nodeData.params, 'number')); } }
    function clearSelection() { if (selectedNode) selectedNode.classList.remove('selected'); if (sourceNodeForConnection) sourceNodeForConnection.classList.remove('selected-source'); selectedNode = null; sourceNodeForConnection = null; renderProperties(null); if (simulationResults) { renderPlottingControls(); } }
    function getDefaultParams(type) { switch(type) { case 'RiverReach': return { slope: 0.001, manning_n: 0.03, length: 1000, width: 20 }; case 'Catchment': return { CN: 75 }; case 'Gate': return { opening_height: 1.0, width: 10, C_d: 0.6 }; case 'Pump': return { a: -0.05, b: 0, c: 5.0 }; case 'Junction': return {}; default: return {}; } }
    function createPropertyInput(label, key, dataObject, type) { const row = document.createElement('div'); row.className = 'property-row'; const labelEl = document.createElement('label'); labelEl.textContent = label.replace(/_/g, ' '); const inputEl = document.createElement('input'); inputEl.type = type; inputEl.value = dataObject[key]; inputEl.addEventListener('change', (e) => { dataObject[key] = (type === 'number') ? parseFloat(e.target.value) : e.target.value; if (key === 'name') document.getElementById(dataObject.id).textContent = e.target.value; }); row.appendChild(labelEl); row.appendChild(inputEl); return row; }
    function setupArrowheadMarker() { const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs'); const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker'); marker.setAttribute('id', 'arrowhead'); marker.setAttribute('viewBox', '0 0 10 10'); marker.setAttribute('refX', '8'); marker.setAttribute('refY', '5'); marker.setAttribute('markerWidth', '6'); marker.setAttribute('markerHeight', '6'); marker.setAttribute('orient', 'auto-start-reverse'); const path = document.createElementNS('http://www.w3.org/2000/svg', 'path'); path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z'); marker.appendChild(path); defs.appendChild(marker); svg.appendChild(defs); }

    function handleTabClick(event) {
        const clickedTab = event.target;
        const targetPaneId = clickedTab.dataset.tab;

        // Update button active state
        tabButtons.forEach(button => button.classList.remove('active'));
        clickedTab.classList.add('active');

        // Update pane visibility
        document.querySelectorAll('.tab-pane').forEach(pane => {
            if (pane.id === targetPaneId) {
                pane.classList.add('active');
            } else {
                pane.classList.remove('active');
            }
        });
    }

    // --- Charting Functions ---
    function initializeCharts() {
        const timeSeriesCtx = timeSeriesChartCanvas.getContext('2d');
        timeSeriesChart = new Chart(timeSeriesCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Final Component Outflow (m^3/s)',
                    data: [],
                    borderColor: 'rgb(75, 192, 192)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: 'Time Step' } },
                    y: { title: { display: true, text: 'Value' } }
                }
            }
        });

        const profileCtx = profileChartCanvas.getContext('2d');
        profileChart = new Chart(profileCtx, {
            type: 'line',
            data: {
                labels: [], // This will be distance along the reach
                datasets: [{
                    label: 'Water Surface Elevation (m)',
                    data: [], // This will be the Z values
                    borderColor: 'rgb(255, 99, 132)',
                    tension: 0.1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { title: { display: true, text: 'Distance Along Reach (m)' } },
                    y: { title: { display: true, text: 'Elevation (m)' } }
                }
            }
        });
    }
    function addDataToChart(chart, label, data) { if (Array.isArray(label)) { chart.data.labels = label; } else { chart.data.labels.push(label); } if (Array.isArray(data)) { chart.data.datasets[0].data = data; } else { chart.data.datasets[0].data.push(data); } chart.update(); }
    function resetChart(chart, newLabel) { chart.data.labels = []; chart.data.datasets.forEach((dataset) => { dataset.data = []; dataset.label = newLabel; }); chart.update(); }
});
