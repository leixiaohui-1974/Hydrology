import geopandas as gpd
from sqlalchemy import create_engine, text

def load_from_db(db_params: dict, query: str) -> gpd.GeoDataFrame:
    """
    Loads spatial data from a PostGIS database into a GeoDataFrame.

    Args:
        db_params (dict): A dictionary containing database connection parameters.
                          Expected keys: 'user', 'password', 'host', 'port', 'dbname'.
        query (str): The SQL query to execute for retrieving the data.
                     The query must select a geometry column for GeoDataFrame creation.

    Returns:
        gpd.GeoDataFrame: A GeoDataFrame containing the result of the query.
    """
    try:
        # Construct the database URL from parameters
        db_url = (
            f"postgresql+psycopg2://{db_params['user']}:{db_params['password']}"
            f"@{db_params['host']}:{db_params['port']}/{db_params['dbname']}"
        )

        print(f"Connecting to database: {db_params['host']}/{db_params['dbname']}")

        # Create a SQLAlchemy engine
        engine = create_engine(db_url)

        # Use GeoPandas to execute the query and load data
        # 'text()' is used to ensure the query is treated as a safe SQL text statement
        gdf = gpd.read_postgis(text(query), engine, geom_col='geometry')

        print(f"Successfully loaded {len(gdf)} features from the database.")

        return gdf

    except ImportError:
        raise ImportError("Loading from a database requires 'SQLAlchemy', 'GeoAlchemy2', and 'psycopg2-binary'. Please install them.")
    except Exception as e:
        print(f"An error occurred while connecting to or querying the database: {e}")
        raise
