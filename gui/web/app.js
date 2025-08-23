document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    const paletteItems = document.querySelectorAll('.component-item');
    const canvas = document.getElementById('canvas');
    const svg = document.getElementById('connections-svg');
    const propertiesContent = document.getElementById('properties-content');
    // ... (all other selectors)

    // --- State Variables ---
    let nodeIdCounter = 0;
    let sourceNodeForConnection = null;
    let sourceNodeForLateralConnection = null;
    let selectedNode = null;
    let selectedLateralLink = null;
    const nodeDataStore = {};
    const connections = [];
    const lateralConnections = [];
    let isLateralMode = false;
    // ... (all other state variables)

    // --- Initial Setup ---
    initializeCharts();
    setupArrowheadMarker();

    // --- Event Listeners ---
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Shift') {
            isLateralMode = true;
            canvas.classList.add('lateral-mode');
        }
    });
    document.addEventListener('keyup', (e) => {
        if (e.key === 'Shift') {
            isLateralMode = false;
            canvas.classList.remove('lateral-mode');
            if (sourceNodeForLateralConnection) {
                sourceNodeForLateralConnection.classList.remove('selected-source');
                sourceNodeForLateralConnection = null;
            }
        }
    });
    // ... (all other event listeners)
    canvas.addEventListener('click', clearSelection);


    // --- Eel functions and other logic as before ---
    // ...

    // --- Main UI Functions ---
    function gatherUIData() {
        const guiData = {
            nodes: nodeDataStore,
            connections: connections,
            lateral_connections: lateralConnections, // Add the new links
            monitored_components: monitoredComponents,
            sim_params: { dt_seconds: 60, num_steps: 100 },
            data_sources: dataSourcesStore,
            global_inputs: [],
            areal_precipitation: {},
            preprocessing: {}
        };
        // ... (rest of the function)
        return guiData;
    }

    // ... (handleRun, handleSave, etc.)

    // --- Node and Property Functions ---
    function createNode(type, x, y) { /* ... implementation ... */ }

    function handleNodeClick(event) {
        event.stopPropagation();
        const clickedNodeEl = event.target;

        // Deselect any selected link
        selectedLateralLink = null;
        document.querySelectorAll('#connections-svg line').forEach(l => l.style.stroke = (l.getAttribute('stroke-dasharray') ? '#3498db' : 'black'));

        if (isLateralMode) {
            if (sourceNodeForLateralConnection) {
                const sourceType = nodeDataStore[sourceNodeForLateralConnection.id].type;
                const targetType = nodeDataStore[clickedNodeEl.id].type;
                if ((sourceType === 'HydraulicModel' && targetType === 'HydraulicModel2D') || (sourceType === 'HydraulicModel2D' && targetType === 'HydraulicModel')) {
                    createLateralConnection(sourceNodeForLateralConnection, clickedNodeEl);
                } else {
                    alert('Lateral connections must be between a River (HydraulicModel) and a 2D Area.');
                }
                sourceNodeForLateralConnection.classList.remove('selected-source');
                sourceNodeForLateralConnection = null;
            } else {
                const sourceType = nodeDataStore[clickedNodeEl.id].type;
                if (sourceType === 'HydraulicModel' || sourceType === 'HydraulicModel2D') {
                    sourceNodeForLateralConnection = clickedNodeEl;
                    sourceNodeForLateralConnection.classList.add('selected-source');
                } else {
                    alert('Lateral connection source must be a River or a 2D Area.');
                }
            }
        } else {
            if (sourceNodeForConnection) {
                if (sourceNodeForConnection !== clickedNodeEl) createConnection(sourceNodeForConnection, clickedNodeEl);
                sourceNodeForConnection.classList.remove('selected-source');
                sourceNodeForConnection = null;
            } else {
                if (selectedNode) selectedNode.classList.remove('selected');
                selectedNode = clickedNodeEl;
                selectedNode.classList.add('selected');
                renderProperties(selectedNode.id, null);
            }
        }
    }

    function createConnection(sourceNode, targetNode) {
        connections.push({ from: sourceNode.id, to: targetNode.id });
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        const sourceRect = sourceNode.getBoundingClientRect();
        const targetRect = targetNode.getBoundingClientRect();
        const canvasRect = canvas.getBoundingClientRect();
        const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;
        line.setAttribute('x1', x1); line.setAttribute('y1', y1); line.setAttribute('x2', x2); line.setAttribute('y2', y2);
        line.setAttribute('stroke', 'black');
        line.setAttribute('stroke-width', '2');
        line.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(line);
    }

    function createLateralConnection(sourceNode, targetNode) {
        const linkId = `lat-link-${lateralConnections.length}`;
        const newLink = { id: linkId, from: sourceNode.id, to: targetNode.id, params: { bank_elevation: 10.0, weir_coeff: 1.6 } };
        lateralConnections.push(newLink);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        const sourceRect = sourceNode.getBoundingClientRect();
        const targetRect = targetNode.getBoundingClientRect();
        const canvasRect = canvas.getBoundingClientRect();
        const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;
        line.setAttribute('x1', x1); line.setAttribute('y1', y1); line.setAttribute('x2', x2); line.setAttribute('y2', y2);
        line.setAttribute('stroke', '#3498db');
        line.setAttribute('stroke-width', '3');
        line.setAttribute('stroke-dasharray', '5,5');
        line.setAttribute('id', linkId);
        line.addEventListener('click', (e) => {
            e.stopPropagation();
            if (selectedNode) selectedNode.classList.remove('selected');
            selectedNode = null;
            selectedLateralLink = newLink;
            document.querySelectorAll('#connections-svg line').forEach(l => l.style.stroke = (l.id === linkId) ? '#e74c3c' : (l.getAttribute('stroke-dasharray') ? '#3498db' : 'black'));
            renderProperties(null, newLink);
        });
        svg.appendChild(line);
    }

    function renderProperties(nodeId, link) {
        propertiesContent.innerHTML = '';
        plottingControls.style.display = 'none';
        propertiesContent.style.display = 'block';

        if (nodeId) {
            const nodeData = nodeDataStore[nodeId];
            propertiesContent.appendChild(createPropertyInput('Name', 'name', nodeData, 'text'));
            // ... (rest of node property logic from previous steps)
        } else if (link) {
            const title = document.createElement('h4');
            title.textContent = `Lateral Link: ${link.id}`;
            propertiesContent.appendChild(title);
            for (const key in link.params) {
                propertiesContent.appendChild(createPropertyInput(key, key, link.params, 'number'));
            }
        } else {
            propertiesContent.innerHTML = '<p>Select a component or link to see its properties.</p>';
        }
    }

    function clearSelection() {
        if (selectedNode) selectedNode.classList.remove('selected');
        if (sourceNodeForConnection) sourceNodeForConnection.classList.remove('selected-source');
        if (sourceNodeForLateralConnection) sourceNodeForLateralConnection.classList.remove('selected-source');
        selectedNode = null;
        sourceNodeForConnection = null;
        sourceNodeForLateralConnection = null;
        selectedLateralLink = null;
        document.querySelectorAll('#connections-svg line').forEach(l => l.style.stroke = (l.getAttribute('stroke-dasharray') ? '#3498db' : 'black'));
        renderProperties(null, null);
        if (simulationResults) { renderPlottingControls(); }
    }

    function getDefaultParams(type) { /* ... implementation from previous step ... */ }
    function createPropertyInput(label, key, dataObject, type) { /* ... implementation ... */ }
    // ... (rest of the file)
});
