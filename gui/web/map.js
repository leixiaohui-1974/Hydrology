/**
 * JavaScript file for 2D Map Visualization.
 *
 * This file contains all the logic for initializing and updating the Leaflet map
 * that displays the results of the 2D hydraulic model.
 *
 * It handles:
 * - Map initialization and tile layers.
 * - Rendering the 2D mesh (triangles).
 * - Coloring the mesh based on water depth.
 * - Displaying a color legend.
 * - Drawing velocity vectors.
 * - Handling user interaction (e.g., clicking on a cell).
 */

// --- Map State Variables ---
let leafletMap = null;     // The main Leaflet map object.
let meshLayer = null;      // A Leaflet FeatureGroup for the mesh polygons.
let meshFaceLayers = [];   // An array holding each individual polygon layer.
let velocityLayer = null;  // A Leaflet LayerGroup for the velocity arrows.

// --- 2D Map Visualization Functions ---

/**
 * Initializes the Leaflet map instance.
 * This function is called once when the application loads. It sets up the
 * base map tiles and creates a layer group for velocity vectors.
 * It uses a MutationObserver to ensure the map is only initialized when its
 * container tab becomes visible, preventing sizing issues.
 */
function initialize2DMap() {
    const mapContainer = document.getElementById('leaflet-map');
    if (mapContainer && leafletMap === null) {
        // Use a MutationObserver to initialize the map only when the tab is visible
        const observer = new MutationObserver((mutationsList, obs) => {
            for (const mutation of mutationsList) {
                if (mutation.type === 'attributes' && mutation.attributeName === 'class') {
                    if (mapContainer.parentElement.classList.contains('active')) {
                        leafletMap = L.map('leaflet-map').setView([40.7128, -74.0060], 13);
                        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                            maxZoom: 19,
                            attribution: '© OpenStreetMap contributors'
                        }).addTo(leafletMap);
                        velocityLayer = L.layerGroup().addTo(leafletMap);
                        obs.disconnect(); // Stop observing once the map is initialized
                    }
                }
            }
        });
        observer.observe(mapContainer.parentElement, { attributes: true });
    }
}

function getColor(d, min_d, max_d) {
    // Calculate intensity, ensuring it's between 0 and 1
    const intensity = Math.max(0, Math.min(1, (d - min_d) / (max_d - min_d + 1e-9)));
    // Interpolate color from blue (low) to a lighter blue (high)
    const r = 150 - Math.floor(intensity * 150);
    const g = 150 - Math.floor(intensity * 150);
    const b = 255;
    return `rgb(${r}, ${g}, ${b})`;
}

function updateLegend(min_d, max_d) {
    const legend = document.getElementById('map-legend');
    legend.innerHTML = '<strong>Water Depth (m)</strong><br>';
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
    const min_h = 0; // Assuming minimum depth is 0

    meshFaceLayers.forEach((layer, i) => {
        if (h_data[i] !== undefined) {
            const depth = h_data[i];
            layer.setStyle({
                fillColor: getColor(depth, min_h, max_h),
                fillOpacity: depth > 0.001 ? 0.6 : 0.0 // Transparent if depth is negligible
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

    // A simple scaling factor for arrow length. This might need tuning.
    const arrowScale = 0.5;

    for (let i = 0; i < triangles.length; i++) {
        // Only draw arrows for cells with significant depth
        if (h_data[i] > 0.1) {
            const u = u_data[i];
            const v = v_data[i];
            const speed = Math.sqrt(u * u + v * v);

            if (speed > 0.01) {
                const triangle = triangles[i];
                // Calculate centroid of the triangle
                const p1 = points[triangle[0]];
                const p2 = points[triangle[1]];
                const p3 = points[triangle[2]];
                const centroid_lon = (p1[0] + p2[0] + p3[0]) / 3;
                const centroid_lat = (p1[1] + p2[1] + p3[1]) / 3;

                // Calculate the end point of the arrow
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
            const popupContent = `<b>Water Depth:</b> ${depth.toFixed(3)} m`;
            L.popup()
                .setLatLng(polygon.getBounds().getCenter())
                .setContent(popupContent)
                .openOn(leafletMap);
        });

        return polygon;
    });

    meshLayer = L.featureGroup(meshFaceLayers).addTo(leafletMap);
    // Fit map to the mesh bounds
    setTimeout(() => {
        if (meshLayer.getBounds().isValid()) {
            leafletMap.fitBounds(meshLayer.getBounds().pad(0.1));
        }
    }, 100); // Delay to ensure the map is ready
}

/**
 * Main function to render the 2D simulation results on the map.
 * This is the entry point for all 2D visualization updates.
 *
 * @param {object} results - The full simulation results object from the backend.
 * @param {object} nodeDataStore - The frontend's store of node data.
 */
function render2DResults(results, nodeDataStore) {
    let result2d = null;
    // Find the specific results for the 2D model component.
    for (const compName in results) {
        const nodeId = Object.keys(nodeDataStore).find(id => nodeDataStore[id].name === compName);
        if (nodeId && nodeDataStore[nodeId].type === 'HydraulicModel2D') {
            result2d = results[compName];
            break;
        }
    }
    // If no 2D results, hide the map controls.
    if (!result2d) {
        document.getElementById('map-controls').style.display = 'none';
        return;
    }

    // Show controls and render the mesh.
    document.getElementById('map-controls').style.display = 'flex';
    render2DMesh(result2d, results, nodeDataStore);

    // Configure the time slider based on the number of timesteps.
    const slider = document.getElementById('time-slider');
    const num_steps = result2d.h.length;
    slider.max = num_steps > 0 ? num_steps - 1 : 0;
    slider.value = 0;
    // Add listener to update map colors when the slider is moved.
    slider.addEventListener('input', (e) => updateMapColors(parseInt(e.target.value, 10), results, nodeDataStore));

    // Perform the initial coloring for the first timestep.
    updateMapColors(0, results, nodeDataStore);
}
