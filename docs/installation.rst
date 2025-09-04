Installation Guide
==================

This guide will help you install and set up the Hydrology Framework on your system.

System Requirements
-------------------

* Python 3.8 or higher
* Windows, macOS, or Linux
* At least 4GB RAM (8GB recommended)
* 2GB free disk space

Dependencies
------------

The framework requires the following core dependencies:

* NumPy >= 1.20.0
* Pandas >= 1.3.0
* Flask >= 2.0.0
* SQLAlchemy >= 1.4.0

Optional dependencies for advanced features:

* PyTorch >= 1.9.0 (for deep learning models)
* PyTorch Geometric >= 2.0.0 (for GNN models)
* GeoPandas >= 0.10.0 (for spatial data)
* Matplotlib >= 3.4.0 (for visualization)
* Plotly >= 5.0.0 (for interactive plots)

Installation Methods
--------------------

From Source (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~

1. Clone the repository::

    git clone https://github.com/your-org/hydrology-framework.git
    cd hydrology-framework

2. Create a virtual environment::

    python -m venv venv
    
    # On Windows
    venv\Scripts\activate
    
    # On macOS/Linux
    source venv/bin/activate

3. Install dependencies::

    pip install -r requirements.txt

4. Install optional dependencies (if needed)::

    # For deep learning features
    pip install torch torchvision torch-geometric
    
    # For spatial data processing
    pip install geopandas
    
    # For visualization
    pip install matplotlib plotly

Using pip (Future)
~~~~~~~~~~~~~~~~~~

Once published to PyPI::

    pip install hydrology-framework

Using conda (Future)
~~~~~~~~~~~~~~~~~~~~

Once published to conda-forge::

    conda install -c conda-forge hydrology-framework

Docker Installation
~~~~~~~~~~~~~~~~~~~

1. Pull the Docker image::

    docker pull hydrology-framework:latest

2. Run the container::

    docker run -p 5000:5000 hydrology-framework:latest

Verifying Installation
----------------------

To verify that the installation was successful, run::

    python -c "import common.base_model; print('Installation successful!')"

You can also run the test suite::

    python -m pytest tests/

Configuration
-------------

After installation, you may need to configure the framework:

1. Copy the example configuration::

    cp config/example_config.json config/config.json

2. Edit the configuration file to match your system setup.

3. Set environment variables if needed::

    export HYDROLOGY_CONFIG_PATH=/path/to/config.json

Troubleshooting
---------------

Common Issues
~~~~~~~~~~~~~

**Import errors**: Make sure all dependencies are installed and the virtual environment is activated.

**Permission errors**: On Unix systems, you may need to use ``sudo`` for system-wide installation.

**Memory errors**: Ensure you have sufficient RAM, especially when working with large datasets.

Getting Help
~~~~~~~~~~~~

If you encounter issues:

1. Check the `GitHub Issues <https://github.com/your-org/hydrology-framework/issues>`_
2. Consult the :doc:`quickstart` guide
3. Review the :doc:`api/modules` documentation

Next Steps
----------

Once installation is complete, proceed to the :doc:`quickstart` guide to learn how to use the framework.