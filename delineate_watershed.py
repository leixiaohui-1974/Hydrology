from pysheds.grid import Grid
import matplotlib.pyplot as plt
import numpy as np

def main():
    # 1. Load the DEM
    grid = Grid()
    dem = grid.read_raster('gis_data/dem.tif')
    print("DEM loaded.")

    # 2. Pre-processing
    # Fill depressions
    flooded_dem = grid.fill_depressions(dem)
    print("DEM pre-processing complete.")

    # 3. Calculate Flow Direction and Accumulation
    # Use the D-infinity routing algorithm, which can be more robust
    dirmap = grid.flowdir(flooded_dem, routing='dinf')
    # Flow accumulation
    acc = grid.accumulation(dirmap, routing='dinf')
    print(f"Max accumulation: {acc.max()}")
    print("Flow direction and accumulation calculated.")

    # 4. Delineate a single catchment
    # Specify outlet point
    x, y = -122.05, 49.01

    # Snap outlet to the nearest high-accumulation cell
    try:
        # Lowered threshold to 5, suitable for dinf accumulation values
        snapped_outlet = grid.snap_to_mask(acc > 5, (x, y), return_dist=False)

        # Delineate the catchment
        catch = grid.catchment(dirmap=dirmap, x=snapped_outlet[0], y=snapped_outlet[1], xytype='coordinate')

        # Clip the grid to the catchment area for visualization
        grid.clip_to(catch)
        clipped_catch = grid.view(catch, apply_mask=True)
        print("Catchment successfully delineated.")
    except IndexError:
        print("Error: Could not snap outlet. Accumulation is likely zero or too low.")
        clipped_catch = None

    # 5. Visualize the results for debugging
    fig, axes = plt.subplots(1, 3, figsize=(18, 6))

    axes[0].imshow(flooded_dem, cmap='terrain')
    axes[0].set_title('Flooded DEM')

    axes[1].imshow(dirmap, cmap='viridis')
    axes[1].set_title('Flow Direction (dinf)')

    # Use logarithmic scale only if there's something to see
    if acc.max() > 0:
        norm = plt.cm.colors.LogNorm()
    else:
        norm = None

    im = axes[2].imshow(acc, cmap='jet', norm=norm)
    axes[2].set_title('Flow Accumulation')

    if clipped_catch is not None:
        axes[0].imshow(clipped_catch, cmap='viridis', alpha=0.5)
        axes[0].set_title('Flooded DEM with Catchment')

    plt.colorbar(im, ax=axes[2], label='Upstream Cells')
    plt.tight_layout()
    plt.savefig('results/delineation_debug_plot.png')
    print("Debug plot saved to results/delineation_debug_plot.png")

if __name__ == "__main__":
    main()
