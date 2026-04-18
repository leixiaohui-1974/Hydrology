# Hydrology Framework - Docker & Kubernetes Deployment Guide

This guide provides comprehensive instructions for deploying the Hydrology Framework using Docker and Kubernetes.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Deployment](#docker-deployment)
- [Kubernetes Deployment](#kubernetes-deployment)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Security](#security)

## Prerequisites

### For Docker Deployment
- Docker Engine 20.10+
- Docker Compose 2.0+
- 4GB+ RAM
- 10GB+ disk space

### For Kubernetes Deployment
- Kubernetes 1.21+
- kubectl configured
- Helm 3.0+ (optional)
- 8GB+ RAM across cluster
- 50GB+ persistent storage

## Docker Deployment

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-org/hydrology.git
   cd hydrology
   ```

2. **Build the Docker image:**
   ```bash
   chmod +x scripts/build-docker.sh
   ./scripts/build-docker.sh --tag latest
   ```

3. **Start the application:**
   ```bash
   docker-compose up -d
   ```

4. **Access the application:**
   - Web GUI: http://localhost:80/gui
   - API: http://localhost:80/api
   - Health Check: http://localhost:80/health

### Environment-Specific Deployments

#### Development Environment
```bash
# Start development environment with hot reloading
docker-compose --profile dev up -d

# Access development services
# Flask Dev Server: http://localhost:5000
# GUI Dev Server: http://localhost:8081
# API Server: http://localhost:8080
```

#### Production Environment
```bash
# Create production environment file
cp .env.example .env.prod
# Edit .env.prod with production values

# Deploy to production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

#### Testing Environment
```bash
# Run tests in containers
docker-compose --profile test up --abort-on-container-exit

# View test coverage
docker-compose exec hydrology-test cat htmlcov/index.html
```

### Docker Build Options

The `build-docker.sh` script supports multiple build targets:

```bash
# Development build with debugging tools
./scripts/build-docker.sh --target development --tag dev-latest

# Production build (optimized)
./scripts/build-docker.sh --target production --tag v1.0.0 --push

# Testing build with test dependencies
./scripts/build-docker.sh --target testing --tag test-latest

# Documentation build
./scripts/build-docker.sh --target docs --tag docs-latest

# Multi-architecture build
./scripts/build-docker.sh --multi-arch --tag latest --push
```

### Docker Compose Profiles

- **Default**: Core application services (app, database, cache, nginx)
- **dev**: Development tools and hot reloading
- **test**: Testing environment with test database
- **docs**: Documentation server
- **monitoring**: Prometheus and Grafana
- **ssl**: SSL certificate management

## Kubernetes Deployment

### Quick Start

1. **Prepare the cluster:**
   ```bash
   # Create namespace and apply basic configuration
   kubectl apply -f k8s/namespace.yaml
   ```

2. **Configure secrets:**
   ```bash
   # Edit secrets with your values
   cp k8s/secrets.yaml k8s/secrets-local.yaml
   # Update base64 encoded values in secrets-local.yaml
   kubectl apply -f k8s/secrets-local.yaml
   ```

3. **Deploy the application:**
   ```bash
   chmod +x scripts/deploy-k8s.sh
   ./scripts/deploy-k8s.sh deploy
   ```

4. **Check deployment status:**
   ```bash
   ./scripts/deploy-k8s.sh status
   ```

### Kubernetes Deployment Script

The `deploy-k8s.sh` script provides comprehensive deployment management:

```bash
# Deploy to production
./scripts/deploy-k8s.sh deploy --environment production

# Deploy to staging with specific image tag
./scripts/deploy-k8s.sh deploy --environment staging --tag v1.2.3

# Upgrade existing deployment
./scripts/deploy-k8s.sh upgrade --tag v1.3.0

# Rollback to previous version
./scripts/deploy-k8s.sh rollback

# View application logs
./scripts/deploy-k8s.sh logs

# Validate manifests without applying
./scripts/deploy-k8s.sh validate

# Dry run deployment
./scripts/deploy-k8s.sh deploy --dry-run

# Clean up all resources
./scripts/deploy-k8s.sh cleanup
```

### Kubernetes Components

#### Core Components
- **Namespace**: Isolated environment for the application
- **ConfigMaps**: Application configuration
- **Secrets**: Sensitive data (passwords, API keys)
- **Deployments**: Application pods with rolling updates
- **Services**: Internal service discovery and load balancing
- **Ingress**: External access and SSL termination
- **PersistentVolumes**: Data persistence

#### Storage
- **StorageClasses**: Different performance tiers (SSD, HDD)
- **PersistentVolumeClaims**: Storage requests
- **VolumeSnapshots**: Backup and recovery

#### Networking
- **NetworkPolicies**: Security and traffic control
- **Ingress Controllers**: External traffic routing
- **Service Mesh**: Advanced traffic management (optional)

## Configuration

### Environment Variables

Key configuration options:

```bash
# Application
FLASK_ENV=production
SECRET_KEY=your-secret-key
JWT_SECRET_KEY=your-jwt-secret

# Database
DATABASE_URL=postgresql://user:pass@host:5432/db
POSTGRES_PASSWORD=secure-password

# Cache
REDIS_URL=redis://host:6379/0
REDIS_PASSWORD=redis-password

# External Services
WEATHER_API_KEY=your-weather-api-key
MAPS_API_KEY=your-maps-api-key

# Email
MAIL_SERVER=smtp.gmail.com
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### Scaling Configuration

#### Docker Compose Scaling
```bash
# Scale application instances
docker-compose up -d --scale hydrology-app=3

# Scale with resource limits
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

#### Kubernetes Scaling
```bash
# Manual scaling
kubectl scale deployment hydrology-app --replicas=5 -n hydrology

# Horizontal Pod Autoscaler
kubectl autoscale deployment hydrology-app --cpu-percent=70 --min=2 --max=10 -n hydrology

# Vertical Pod Autoscaler (if installed)
kubectl apply -f k8s/vpa.yaml
```

## Monitoring

### Docker Monitoring

```bash
# Start monitoring stack
docker-compose --profile monitoring up -d

# Access monitoring services
# Prometheus: http://localhost:9090
# Grafana: http://localhost:3000 (admin/admin123)
```

### Kubernetes Monitoring

```bash
# Deploy monitoring components
kubectl apply -f k8s/monitoring/

# Port forward to access services
kubectl port-forward svc/prometheus 9090:9090 -n hydrology
kubectl port-forward svc/grafana 3000:3000 -n hydrology
```

### Health Checks

- **Liveness Probe**: `/health` - Application health
- **Readiness Probe**: `/ready` - Ready to serve traffic
- **Startup Probe**: `/health` - Initial startup check

### Metrics

- Application metrics: `/metrics`
- Database metrics: PostgreSQL exporter
- Cache metrics: Redis exporter
- Infrastructure metrics: Node exporter

## Troubleshooting

### Common Issues

#### Docker Issues

1. **Port conflicts:**
   ```bash
   # Check port usage
   netstat -tulpn | grep :8080
   
   # Use different ports
   docker-compose -f docker-compose.yml -f docker-compose.override.yml up -d
   ```

2. **Permission issues:**
   ```bash
   # Fix file permissions
   sudo chown -R $USER:$USER .
   chmod +x scripts/*.sh
   ```

3. **Memory issues:**
   ```bash
   # Increase Docker memory limit
   # Docker Desktop: Settings > Resources > Memory
   
   # Check container memory usage
   docker stats
   ```

#### Kubernetes Issues

1. **Pod startup failures:**
   ```bash
   # Check pod status
   kubectl get pods -n hydrology
   
   # View pod logs
   kubectl logs -f deployment/hydrology-app -n hydrology
   
   # Describe pod for events
   kubectl describe pod <pod-name> -n hydrology
   ```

2. **Storage issues:**
   ```bash
   # Check PVC status
   kubectl get pvc -n hydrology
   
   # Check storage class
   kubectl get storageclass
   
   # Check persistent volumes
   kubectl get pv
   ```

3. **Network issues:**
   ```bash
   # Check services
   kubectl get svc -n hydrology
   
   # Check ingress
   kubectl get ingress -n hydrology
   
   # Test internal connectivity
   kubectl exec -it <pod-name> -n hydrology -- curl http://postgres-service:5432
   ```

### Debugging Commands

```bash
# Docker debugging
docker-compose logs -f hydrology-app
docker exec -it hydrology-app bash
docker inspect hydrology-app

# Kubernetes debugging
kubectl logs -f deployment/hydrology-app -n hydrology
kubectl exec -it deployment/hydrology-app -n hydrology -- bash
kubectl describe deployment hydrology-app -n hydrology
```

## Security

### Docker Security

1. **Use non-root user:**
   ```dockerfile
   USER hydrology
   ```

2. **Read-only root filesystem:**
   ```dockerfile
   RUN mkdir -p /app/tmp
   VOLUME ["/app/tmp"]
   ```

3. **Security scanning:**
   ```bash
   # Scan image for vulnerabilities
   docker scan hydrology/framework:latest
   
   # Use Trivy for comprehensive scanning
   trivy image hydrology/framework:latest
   ```

### Kubernetes Security

1. **Pod Security Standards:**
   ```yaml
   securityContext:
     runAsNonRoot: true
     runAsUser: 1000
     readOnlyRootFilesystem: true
   ```

2. **Network Policies:**
   ```bash
   kubectl apply -f k8s/network-policies.yaml
   ```

3. **RBAC:**
   ```bash
   kubectl apply -f k8s/rbac.yaml
   ```

4. **Secret Management:**
   ```bash
   # Use external secret management
   kubectl apply -f k8s/external-secrets.yaml
   ```

### Best Practices

- Use specific image tags, not `latest`
- Regularly update base images
- Scan images for vulnerabilities
- Use secrets for sensitive data
- Implement network policies
- Enable audit logging
- Use service mesh for advanced security

## Backup and Recovery

### Database Backup

```bash
# Docker backup
docker exec hydrology-postgres pg_dump -U hydrology hydrology_db > backup.sql

# Kubernetes backup
kubectl exec deployment/postgres -n hydrology -- pg_dump -U hydrology hydrology_db > backup.sql

# Automated backup with volume snapshots
kubectl apply -f k8s/backup-cronjob.yaml
```

### Disaster Recovery

```bash
# Restore from backup
docker exec -i hydrology-postgres psql -U hydrology hydrology_db < backup.sql

# Kubernetes restore
kubectl exec -i deployment/postgres -n hydrology -- psql -U hydrology hydrology_db < backup.sql
```

## Performance Tuning

### Resource Optimization

```yaml
# Kubernetes resource requests and limits
resources:
  requests:
    cpu: 200m
    memory: 256Mi
  limits:
    cpu: 1000m
    memory: 1Gi
```

### Database Tuning

```yaml
# PostgreSQL configuration
shared_buffers: 256MB
effective_cache_size: 1GB
maintenance_work_mem: 64MB
max_connections: 100
```

### Cache Optimization

```yaml
# Redis configuration
maxmemory: 256mb
maxmemory-policy: allkeys-lru
```

## Support

For issues and questions:

- GitHub Issues: [Repository Issues](https://github.com/your-org/hydrology/issues)
- Documentation: [Full Documentation](https://docs.hydrology.example.com)
- Community: [Discussion Forum](https://github.com/your-org/hydrology/discussions)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.