document.addEventListener('DOMContentLoaded', () => {
    // --- Element Selectors ---
    // ...

    // --- State Variables ---
    // ...

    // --- Initial Setup & Event Listeners ---
    initialize2DMap();
    // ...

    // --- Eel functions ---
    function simulation_finished(result) {
        // ...
        eel.get_results()().then(results => {
            if (results) {
                simulationResults = results;
                renderPlottingControls();
                render2DResults(results, nodeDataStore);
            }
        });
    }

    // ... (rest of the file, including all other functions)
});
