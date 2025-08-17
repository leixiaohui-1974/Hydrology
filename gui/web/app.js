document.addEventListener('DOMContentLoaded', () => {
    const paletteItems = document.querySelectorAll('.component-item');
    const canvas = document.getElementById('canvas');
    const svg = document.getElementById('connections-svg');
    const propertiesContent = document.getElementById('properties-content');
    const saveButton = document.getElementById('save-button');

    let nodeIdCounter = 0;
    let sourceNodeForConnection = null;
    let selectedNode = null;

    // --- Data Store ---
    const nodeDataStore = {};
    const connections = [];

    // --- Event Listeners ---
    paletteItems.forEach(item => {
        item.addEventListener('dragstart', e => event.dataTransfer.setData('text/plain', e.target.dataset.type));
    });
    canvas.addEventListener('dragover', e => e.preventDefault());
    canvas.addEventListener('drop', e => {
        e.preventDefault();
        createNode(e.dataTransfer.getData('text/plain'), e.clientX, e.clientY);
    });
    saveButton.addEventListener('click', handleSave);

    // --- Main Functions ---
    function createNode(type, x, y) {
        nodeIdCounter++;
        const nodeId = `node-${nodeIdCounter}`;
        const nodeName = `${type}_${nodeIdCounter}`;
        nodeDataStore[nodeId] = { id: nodeId, name: nodeName, type: type, params: getDefaultParams(type) };

        const nodeEl = document.createElement('div');
        nodeEl.className = 'canvas-node';
        nodeEl.id = nodeId;
        nodeEl.textContent = nodeName;

        const canvasRect = canvas.getBoundingClientRect();
        nodeEl.style.left = `${x - canvasRect.left - 60}px`;
        nodeEl.style.top = `${y - canvasRect.top - 25}px`;

        nodeEl.addEventListener('click', handleNodeClick);
        canvas.appendChild(nodeEl);
    }

    function handleNodeClick(event) {
        const clickedNodeEl = event.target;
        event.stopPropagation();
        if (sourceNodeForConnection) {
            if (sourceNodeForConnection !== clickedNodeEl) createConnection(sourceNodeForConnection, clickedNodeEl);
            sourceNodeForConnection.classList.remove('selected-source');
            sourceNodeForConnection = null;
        } else {
            if (selectedNode) selectedNode.classList.remove('selected');
            selectedNode = clickedNodeEl;
            selectedNode.classList.add('selected');
            renderProperties(selectedNode.id);
        }
    }

    function createConnection(sourceNode, targetNode) {
        connections.push({ from: sourceNode.id, to: targetNode.id });
        console.log('Stored connections:', connections);
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        const sourceRect = sourceNode.getBoundingClientRect();
        const targetRect = targetNode.getBoundingClientRect();
        const canvasRect = canvas.getBoundingClientRect();
        const x1 = sourceRect.left + sourceRect.width / 2 - canvasRect.left;
        const y1 = sourceRect.top + sourceRect.height / 2 - canvasRect.top;
        const x2 = targetRect.left + targetRect.width / 2 - canvasRect.left;
        const y2 = targetRect.top + targetRect.height / 2 - canvasRect.top;
        line.setAttribute('x1', x1); line.setAttribute('y1', y1);
        line.setAttribute('x2', x2); line.setAttribute('y2', y2);
        line.setAttribute('stroke', 'black'); line.setAttribute('stroke-width', '2');
        line.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(line);
    }

    function renderProperties(nodeId) {
        propertiesContent.innerHTML = '';
        if (!nodeId) {
            propertiesContent.innerHTML = '<p>Select a component to see its properties.</p>';
            return;
        }
        const nodeData = nodeDataStore[nodeId];
        propertiesContent.appendChild(createPropertyInput('Name', 'name', nodeData, 'text'));
        for (const key in nodeData.params) {
            propertiesContent.appendChild(createPropertyInput(key, key, nodeData.params, 'number'));
        }
    }

    function handleSave() {
        console.log("Save button clicked. Preparing data for Python.");
        const dataToSend = {
            nodes: nodeDataStore,
            connections: connections
        };
        // Call the exposed Python function
        eel.save_config_to_yaml(dataToSend)(response => {
            alert(response); // Show the response from Python (e.g., "Saved successfully")
        });
    }

    // --- Helper Functions ---
    function getDefaultParams(type) {
        switch(type) {
            case 'RiverReach': return { slope: 0.001, manning_n: 0.03, length: 1000, width: 20 };
            case 'Catchment': return { CN: 75 };
            case 'Gate': return { opening_height: 1.0, width: 10, C_d: 0.6 };
            case 'Pump': return { a: -0.05, b: 0, c: 5.0 };
            case 'Junction': return {};
            default: return {};
        }
    }

    function createPropertyInput(label, key, dataObject, type) {
        const row = document.createElement('div');
        row.className = 'property-row';
        const labelEl = document.createElement('label');
        labelEl.textContent = label.replace(/_/g, ' ');
        const inputEl = document.createElement('input');
        inputEl.type = type;
        inputEl.value = dataObject[key];
        inputEl.addEventListener('change', (e) => {
            dataObject[key] = (type === 'number') ? parseFloat(e.target.value) : e.target.value;
            if (key === 'name') document.getElementById(dataObject.id).textContent = e.target.value;
        });
        row.appendChild(labelEl);
        row.appendChild(inputEl);
        return row;
    }

    // --- Initial Setup ---
    canvas.addEventListener('click', () => {
        if (selectedNode) selectedNode.classList.remove('selected');
        if (sourceNodeForConnection) sourceNodeForConnection.classList.remove('selected-source');
        selectedNode = null;
        sourceNodeForConnection = null;
        renderProperties(null);
    });

    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'arrowhead');
    marker.setAttribute('viewBox', '0 0 10 10');
    marker.setAttribute('refX', '8');
    marker.setAttribute('refY', '5');
    marker.setAttribute('markerWidth', '6');
    marker.setAttribute('markerHeight', '6');
    marker.setAttribute('orient', 'auto-start-reverse');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M 0 0 L 10 5 L 0 10 z');
    marker.appendChild(path);
    defs.appendChild(marker);
    svg.appendChild(defs);
});
