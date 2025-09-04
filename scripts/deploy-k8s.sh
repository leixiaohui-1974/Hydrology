#!/bin/bash

# Hydrology Framework Kubernetes Deployment Script
# This script automates the deployment of the Hydrology framework to Kubernetes

set -euo pipefail

# Configuration
NAMESPACE="hydrology"
APP_NAME="hydrology-framework"
CONTEXT=""
DRY_RUN=false
VERBOSE=false
ENVIRONMENT="production"
IMAGE_TAG="latest"
REGISTRY=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Help function
show_help() {
    cat << EOF
Hydrology Framework Kubernetes Deployment Script

Usage: $0 [OPTIONS] COMMAND

Commands:
    deploy      Deploy the application
    upgrade     Upgrade existing deployment
    rollback    Rollback to previous version
    status      Check deployment status
    logs        Show application logs
    cleanup     Remove all resources
    validate    Validate Kubernetes manifests

Options:
    -n, --namespace NAMESPACE    Kubernetes namespace (default: hydrology)
    -c, --context CONTEXT        Kubernetes context
    -e, --environment ENV        Environment (dev/staging/prod) (default: production)
    -t, --tag TAG               Docker image tag (default: latest)
    -r, --registry REGISTRY     Docker registry URL
    --dry-run                   Show what would be done without executing
    -v, --verbose               Verbose output
    -h, --help                  Show this help message

Examples:
    $0 deploy
    $0 deploy --environment staging --tag v1.2.3
    $0 upgrade --tag v1.3.0
    $0 rollback
    $0 status
    $0 cleanup --dry-run

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -n|--namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            -c|--context)
                CONTEXT="$2"
                shift 2
                ;;
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -t|--tag)
                IMAGE_TAG="$2"
                shift 2
                ;;
            -r|--registry)
                REGISTRY="$2"
                shift 2
                ;;
            --dry-run)
                DRY_RUN=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            deploy|upgrade|rollback|status|logs|cleanup|validate)
                COMMAND="$1"
                shift
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    if [[ -z "${COMMAND:-}" ]]; then
        log_error "No command specified"
        show_help
        exit 1
    fi
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed or not in PATH"
        exit 1
    fi
    
    # Check if helm is installed (optional)
    if ! command -v helm &> /dev/null; then
        log_warning "helm is not installed - some features may not be available"
    fi
    
    # Check kubectl context
    if [[ -n "$CONTEXT" ]]; then
        kubectl config use-context "$CONTEXT"
    fi
    
    # Verify cluster connectivity
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster"
        exit 1
    fi
    
    log_success "Prerequisites check passed"
}

# Validate Kubernetes manifests
validate_manifests() {
    log_info "Validating Kubernetes manifests..."
    
    local k8s_dir="../k8s"
    local errors=0
    
    for file in "$k8s_dir"/*.yaml; do
        if [[ -f "$file" ]]; then
            log_info "Validating $file"
            if ! kubectl apply --dry-run=client -f "$file" &> /dev/null; then
                log_error "Validation failed for $file"
                ((errors++))
            fi
        fi
    done
    
    if [[ $errors -eq 0 ]]; then
        log_success "All manifests are valid"
    else
        log_error "$errors manifest(s) failed validation"
        exit 1
    fi
}

# Create namespace if it doesn't exist
ensure_namespace() {
    log_info "Ensuring namespace '$NAMESPACE' exists..."
    
    if ! kubectl get namespace "$NAMESPACE" &> /dev/null; then
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would create namespace: $NAMESPACE"
        else
            kubectl create namespace "$NAMESPACE"
            log_success "Created namespace: $NAMESPACE"
        fi
    else
        log_info "Namespace '$NAMESPACE' already exists"
    fi
}

# Apply Kubernetes manifests
apply_manifests() {
    log_info "Applying Kubernetes manifests..."
    
    local k8s_dir="../k8s"
    local kubectl_cmd="kubectl apply -f"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        kubectl_cmd="kubectl apply --dry-run=client -f"
    fi
    
    # Apply in specific order
    local files=(
        "namespace.yaml"
        "configmap.yaml"
        "secrets.yaml"
        "storage.yaml"
        "deployment.yaml"
        "service.yaml"
        "ingress.yaml"
    )
    
    for file in "${files[@]}"; do
        local filepath="$k8s_dir/$file"
        if [[ -f "$filepath" ]]; then
            log_info "Applying $file"
            if [[ "$VERBOSE" == "true" ]]; then
                $kubectl_cmd "$filepath"
            else
                $kubectl_cmd "$filepath" &> /dev/null
            fi
        else
            log_warning "File not found: $filepath"
        fi
    done
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Manifests would be applied"
    else
        log_success "All manifests applied successfully"
    fi
}

# Wait for deployment to be ready
wait_for_deployment() {
    log_info "Waiting for deployment to be ready..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would wait for deployment readiness"
        return
    fi
    
    local timeout=300  # 5 minutes
    
    if kubectl wait --for=condition=available --timeout=${timeout}s deployment/hydrology-app -n "$NAMESPACE"; then
        log_success "Deployment is ready"
    else
        log_error "Deployment failed to become ready within ${timeout} seconds"
        exit 1
    fi
}

# Deploy function
deploy() {
    log_info "Starting deployment of $APP_NAME to $ENVIRONMENT environment..."
    
    validate_manifests
    ensure_namespace
    apply_manifests
    wait_for_deployment
    
    log_success "Deployment completed successfully!"
    
    # Show status
    show_status
}

# Upgrade function
upgrade() {
    log_info "Upgrading $APP_NAME..."
    
    # Update image tag in deployment
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would update image tag to: $IMAGE_TAG"
    else
        kubectl set image deployment/hydrology-app hydrology-app="${REGISTRY}hydrology/framework:${IMAGE_TAG}" -n "$NAMESPACE"
        kubectl rollout status deployment/hydrology-app -n "$NAMESPACE"
    fi
    
    log_success "Upgrade completed successfully!"
}

# Rollback function
rollback() {
    log_info "Rolling back $APP_NAME..."
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would rollback deployment"
    else
        kubectl rollout undo deployment/hydrology-app -n "$NAMESPACE"
        kubectl rollout status deployment/hydrology-app -n "$NAMESPACE"
    fi
    
    log_success "Rollback completed successfully!"
}

# Show status
show_status() {
    log_info "Deployment status:"
    
    echo "\n=== Pods ==="
    kubectl get pods -n "$NAMESPACE" -l app=hydrology-app
    
    echo "\n=== Services ==="
    kubectl get services -n "$NAMESPACE"
    
    echo "\n=== Ingress ==="
    kubectl get ingress -n "$NAMESPACE"
    
    echo "\n=== PVCs ==="
    kubectl get pvc -n "$NAMESPACE"
}

# Show logs
show_logs() {
    log_info "Showing application logs..."
    
    kubectl logs -f deployment/hydrology-app -n "$NAMESPACE" --tail=100
}

# Cleanup function
cleanup() {
    log_warning "This will delete all resources in namespace '$NAMESPACE'"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would delete namespace: $NAMESPACE"
        return
    fi
    
    read -p "Are you sure? (y/N): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kubectl delete namespace "$NAMESPACE"
        log_success "Cleanup completed"
    else
        log_info "Cleanup cancelled"
    fi
}

# Main function
main() {
    parse_args "$@"
    check_prerequisites
    
    case "$COMMAND" in
        deploy)
            deploy
            ;;
        upgrade)
            upgrade
            ;;
        rollback)
            rollback
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        cleanup)
            cleanup
            ;;
        validate)
            validate_manifests
            ;;
        *)
            log_error "Unknown command: $COMMAND"
            show_help
            exit 1
            ;;
    esac
}

# Run main function
main "$@"