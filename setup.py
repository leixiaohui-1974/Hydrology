from setuptools import setup, find_packages

setup(
    name="hydro_model_suite",
    version="1.0",
    packages=find_packages(),
    author="Jules",
    author_email="jules@example.com",
    description="A suite of coupled hydrological and hydraulic models.",
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
