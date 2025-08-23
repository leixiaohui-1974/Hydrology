document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    // ...

    // --- State Variables ---
    let leafletMap = null;
    let meshLayer = null;
    let meshFaceLayers = []; // Store individual polygon layers
    // ...

    // --- Initial Setup & Event Listeners ---
    // ...

    // --- Eel functions ---
    function simulation_finished(result) {
        // ...
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                renderPlottingControls();
                render2DResults(results);
            }
        });
    }

    // --- 2D Map Visualization Functions ---

    function initialize2DMap() {
        const mapContainer = document.getElementById('leaflet-map');
        if (mapContainer && leafletMap === null) {
            const observer = new MutationObserver((mutationsList, obs) => {
                for (const mutation of mutationsList) {
                    if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                        if (mapContainer.parentElement.classList.contains('active')) {
                            leafletMap = L.map('leaflet-map').setView([40.7128, -74.0060], 13);
                            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                                maxZoom: 19,
                                attribution: '© OpenStreetMap contributors'
                            }).addTo(leafletMap);
                            obs.disconnect();
                        }
                    }
                }
            });
            observer.observe(mapContainer.parentElement, { attributes: true });
        }
    }

    function getColor(d, min_d, max_d) {
        const intensity = Math.max(0, Math.min(1, (d - min_d) / (max_d - min_d + 1e-9)));
        const r = 150 - Math.floor(intensity * 150);
        const g = 150 - Math.floor(intensity * 150);
        const b = 255;
        return `rgb(${r}, ${g}, ${b})`;
    }

    function updateMapColors(timestep) {
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
        const min_h = 0;

        meshFaceLayers.forEach((layer, i) => {
            if (h_data[i] !== undefined) {
                const depth = h_data[i];
                layer.setStyle({
                    fillColor: getColor(depth, min_h, max_h),
                    fillOpacity: depth > 0.001 ? 0.6 : 0.0
                });
            }
        });
        document.getElementById('time-label').textContent = timestep;
    }

    function render2DMesh(result2d) {
        if (!leafletMap) return;
        if (meshLayer) {
            leafletMap.removeLayer(meshLayer);
        }
        meshFaceLayers = [];

        const points = result2d.points;
        const triangles = result2d.triangles;

        meshFaceLayers = triangles.map(triangle => {
            const p1 = L.latLng(points[triangle[0]][1], points[triangle[0]][0]);
            const p2 = L.latLng(points[triangle[1]][1], points[triangle[1]][0]);
            const p3 = L.latLng(points[triangle[2]][1], points[triangle[2]][0]);
            return L.polygon([p1, p2, p3], { color: '#3498db', weight: 1 });
        });

        meshLayer = L.featureGroup(meshFaceLayers).addTo(leafletMap);
        setTimeout(() => {
            if (meshLayer.getBounds().isValid()) {
                leafletMap.fitBounds(meshLayer.getBounds().pad(0.1));
            }
        }, 100);
    }

    function render2DResults(results) {
        let result2d = null;
        for (const compName in results) {
            const nodeId = Object.keys(nodeDataStore).find(id => nodeDataStore[id].name === compName);
            if (nodeId && nodeDataStore[nodeId].type === 'HydraulicModel2D') {
                result2d = results[compName];
                break;
            }
        }
        if (!result2d) {
            document.getElementById('map-controls').style.display = 'none';
            return;
        }

        document.getElementById('map-controls').style.display = 'flex';
        render2DMesh(result2d);

        const slider = document.getElementById('time-slider');
        const num_steps = result2d.h.length;
        slider.max = num_steps > 0 ? num_steps - 1 : 0;
        slider.value = 0;
        slider.addEventListener('input', (e) => updateMapColors(parseInt(e.target.value, 10)));

        updateMapColors(0);
    }

    // ... (rest of the file, including all other functions)
});
