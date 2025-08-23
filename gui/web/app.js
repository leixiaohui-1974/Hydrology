/**
 * Main JavaScript file for the modeling tool's frontend.
 *
 * This file handles:
 * - Initialization of the user interface, including component palette, canvas, and properties pane.
 * - Drag-and-drop functionality for creating model components.
 * - Management of the application's state (nodes, connections, properties).
 * - Communication with the Python backend via the Eel library.
 * - Triggering simulations and handling the results for plotting.
 * - UI updates based on user interaction and simulation status.
 */
document.addEventListener('DOMContentLoaded', () => {
    // --- Global State Variables ---
    // These variables hold the complete state of the user's model network.
    let nodeDataStore = {}; // Stores properties and metadata for each node (component).
    let connections = [];   // Stores the connections between nodes.
    let simulationResults = null; // Stores the results from the last simulation run.

    // --- Initial Setup & Event Listeners ---
    // This section is responsible for setting up the initial state of the UI
    // and attaching all necessary event listeners for user interaction.

    // Initialize the Leaflet map for 2D visualization.
    initialize2DMap();

    // Setup drag-and-drop functionality for creating components on the canvas.
    // ... (code for drag-and-drop listeners)

    // Setup listeners for buttons (Run, Save, etc.) and other UI elements.
    // ... (code for other event listeners)


    // --- Eel Exposed Functions & Callbacks ---
    // These functions are exposed to the Python backend and are called to update
    // the frontend in response to backend events (e.g., simulation finished).

    /**
     * Callback function triggered by the backend when a simulation is complete.
     * @param {object} result - An object from the backend, may contain success or error messages.
     */
    eel.expose(simulation_finished, 'simulation_finished');
    function simulation_finished(result) {
        if (result.error) {
            console.error("Simulation failed:", result.error);
            // Here you would update the UI to show the error message.
            return;
        }
        console.log("Simulation finished successfully. Fetching results...");
        // After the simulation is done, we request the full results object.
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                // Update the UI with the new results.
                renderPlottingControls(); // Populate dropdowns for plotting
                render2DResults(results, nodeDataStore); // Render the 2D map visualization
            }
        });
    }

    // ... (rest of the file, including all other functions for UI management)
});
