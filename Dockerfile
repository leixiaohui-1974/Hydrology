# Multi-stage Dockerfile for Hydrology Framework
# Supports both development and production environments

# Stage 1: Base Python environment
FROM python:3.9-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    libhdf5-dev \
    libnetcdf-dev \
    libgdal-dev \
    gdal-bin \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r hydrology && useradd -r -g hydrology hydrology

# Set working directory
WORKDIR /app

# Stage 2: Development environment
FROM base as development

# Install development dependencies
RUN apt-get update && apt-get install -y \
    vim \
    htop \
    tree \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt requirements-dev.txt ./

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements-dev.txt

# Copy source code
COPY . .

# Change ownership to hydrology user
RUN chown -R hydrology:hydrology /app

# Switch to non-root user
USER hydrology

# Expose ports
EXPOSE 8080 8081 5000

# Default command for development
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0", "--port=5000", "--debug"]

# Stage 3: Production environment
FROM base as production

# Copy requirements
COPY requirements.txt ./

# Install only production dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install gunicorn

# Copy source code (excluding development files)
COPY src/ ./src/
COPY gui/ ./gui/
COPY config/ ./config/
COPY api/ ./api/
COPY *.py ./
COPY *.md ./

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/output && \
    chown -R hydrology:hydrology /app

# Switch to non-root user
USER hydrology

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Production command
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "api.main:app"]

# Stage 4: Testing environment
FROM development as testing

# Install additional testing tools
RUN pip install pytest-cov pytest-xdist pytest-mock

# Copy test files
COPY tests/ ./tests/

# Run tests by default
CMD ["python", "-m", "pytest", "tests/", "-v", "--cov=src", "--cov-report=html", "--cov-report=term"]

# Stage 5: Documentation environment
FROM base as docs

# Install documentation dependencies
RUN pip install sphinx sphinx-rtd-theme sphinx-autodoc-typehints

# Copy documentation source
COPY docs/ ./docs/
COPY src/ ./src/

# Build documentation
RUN cd docs && make html

# Serve documentation
EXPOSE 8000
CMD ["python", "-m", "http.server", "8000", "--directory", "docs/_build/html"]

# Default target is production
FROM production as final