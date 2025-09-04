#!/bin/bash

# Hydrology Framework Docker Build and Push Script
# This script automates the building and pushing of Docker images

set -euo pipefail

# Configuration
IMAGE_NAME="hydrology/framework"
REGISTRY=""
TAG="latest"
BUILD_ARGS=""
PLATFORM="linux/amd64"
PUSH=false
NO_CACHE=false
VERBOSE=false
DRY_RUN=false
TARGET="production"

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
Hydrology Framework Docker Build Script

Usage: $0 [OPTIONS]

Options:
    -i, --image IMAGE           Docker image name (default: hydrology/framework)
    -r, --registry REGISTRY     Docker registry URL
    -t, --tag TAG              Image tag (default: latest)
    -p, --platform PLATFORM    Target platform (default: linux/amd64)
    --target TARGET            Build target (development/production/testing/docs) (default: production)
    --build-arg ARG=VALUE      Build argument (can be used multiple times)
    --push                     Push image to registry after build
    --no-cache                 Build without using cache
    --multi-arch               Build for multiple architectures
    --dry-run                  Show what would be done without executing
    -v, --verbose              Verbose output
    -h, --help                 Show this help message

Examples:
    $0 --tag v1.2.3 --push
    $0 --target development --tag dev-latest
    $0 --registry myregistry.com --image myorg/hydrology --tag v1.0.0 --push
    $0 --build-arg VERSION=1.2.3 --build-arg ENV=production --push
    $0 --multi-arch --tag latest --push

EOF
}

# Parse command line arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            -i|--image)
                IMAGE_NAME="$2"
                shift 2
                ;;
            -r|--registry)
                REGISTRY="$2"
                if [[ ! "$REGISTRY" =~ /$ ]]; then
                    REGISTRY="$REGISTRY/"
                fi
                shift 2
                ;;
            -t|--tag)
                TAG="$2"
                shift 2
                ;;
            -p|--platform)
                PLATFORM="$2"
                shift 2
                ;;
            --target)
                TARGET="$2"
                shift 2
                ;;
            --build-arg)
                if [[ -n "$BUILD_ARGS" ]]; then
                    BUILD_ARGS="$BUILD_ARGS --build-arg $2"
                else
                    BUILD_ARGS="--build-arg $2"
                fi
                shift 2
                ;;
            --push)
                PUSH=true
                shift
                ;;
            --no-cache)
                NO_CACHE=true
                shift
                ;;
            --multi-arch)
                PLATFORM="linux/amd64,linux/arm64"
                shift
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
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Docker is installed and running
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running"
        exit 1
    fi
    
    # Check if buildx is available for multi-platform builds
    if [[ "$PLATFORM" == *","* ]]; then
        if ! docker buildx version &> /dev/null; then
            log_error "Docker buildx is required for multi-platform builds"
            exit 1
        fi
    fi
    
    log_success "Prerequisites check passed"
}

# Get version information
get_version_info() {
    local version="unknown"
    local commit="unknown"
    local date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    # Try to get version from git
    if command -v git &> /dev/null && git rev-parse --git-dir &> /dev/null; then
        commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        
        # Try to get version from git tag
        if git describe --tags --exact-match &> /dev/null; then
            version=$(git describe --tags --exact-match)
        elif git describe --tags &> /dev/null; then
            version=$(git describe --tags)
        else
            version="dev-$commit"
        fi
    fi
    
    # Add version build args
    BUILD_ARGS="$BUILD_ARGS --build-arg VERSION=$version"
    BUILD_ARGS="$BUILD_ARGS --build-arg COMMIT=$commit"
    BUILD_ARGS="$BUILD_ARGS --build-arg BUILD_DATE=$date"
    
    log_info "Version: $version, Commit: $commit, Date: $date"
}

# Validate Dockerfile
validate_dockerfile() {
    log_info "Validating Dockerfile..."
    
    if [[ ! -f "Dockerfile" ]]; then
        log_error "Dockerfile not found in current directory"
        exit 1
    fi
    
    # Check if target stage exists
    if ! grep -q "^FROM .* as $TARGET" Dockerfile; then
        log_error "Target stage '$TARGET' not found in Dockerfile"
        exit 1
    fi
    
    log_success "Dockerfile validation passed"
}

# Build Docker image
build_image() {
    local full_image_name="${REGISTRY}${IMAGE_NAME}:${TAG}"
    
    log_info "Building Docker image: $full_image_name"
    log_info "Target: $TARGET"
    log_info "Platform: $PLATFORM"
    
    # Prepare build command
    local build_cmd="docker"
    local build_args=""
    
    # Use buildx for multi-platform builds
    if [[ "$PLATFORM" == *","* ]]; then
        build_cmd="docker buildx build"
        build_args="--platform $PLATFORM"
        
        # Create and use a new builder instance
        if [[ "$DRY_RUN" != "true" ]]; then
            docker buildx create --name hydrology-builder --use 2>/dev/null || true
        fi
    else
        build_cmd="docker build"
        build_args="--platform $PLATFORM"
    fi
    
    # Add build arguments
    build_args="$build_args --target $TARGET"
    build_args="$build_args --tag $full_image_name"
    
    if [[ "$NO_CACHE" == "true" ]]; then
        build_args="$build_args --no-cache"
    fi
    
    if [[ -n "$BUILD_ARGS" ]]; then
        build_args="$build_args $BUILD_ARGS"
    fi
    
    # Add push flag for buildx
    if [[ "$PUSH" == "true" && "$PLATFORM" == *","* ]]; then
        build_args="$build_args --push"
    fi
    
    build_args="$build_args ."
    
    # Execute build command
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would execute: $build_cmd $build_args"
    else
        log_info "Executing: $build_cmd $build_args"
        
        if [[ "$VERBOSE" == "true" ]]; then
            $build_cmd $build_args
        else
            $build_cmd $build_args > /dev/null
        fi
        
        log_success "Image built successfully: $full_image_name"
    fi
}

# Push Docker image
push_image() {
    if [[ "$PUSH" != "true" ]]; then
        return
    fi
    
    # Skip push for multi-platform builds (already pushed during build)
    if [[ "$PLATFORM" == *","* ]]; then
        log_success "Multi-platform image pushed during build"
        return
    fi
    
    local full_image_name="${REGISTRY}${IMAGE_NAME}:${TAG}"
    
    log_info "Pushing Docker image: $full_image_name"
    
    if [[ "$DRY_RUN" == "true" ]]; then
        log_info "[DRY RUN] Would push: $full_image_name"
    else
        if [[ "$VERBOSE" == "true" ]]; then
            docker push "$full_image_name"
        else
            docker push "$full_image_name" > /dev/null
        fi
        
        log_success "Image pushed successfully: $full_image_name"
    fi
}

# Tag additional versions
tag_additional() {
    local full_image_name="${REGISTRY}${IMAGE_NAME}:${TAG}"
    
    # Tag as latest if this is a release tag
    if [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        local latest_tag="${REGISTRY}${IMAGE_NAME}:latest"
        
        log_info "Tagging as latest: $latest_tag"
        
        if [[ "$DRY_RUN" == "true" ]]; then
            log_info "[DRY RUN] Would tag: $latest_tag"
        else
            docker tag "$full_image_name" "$latest_tag"
            
            if [[ "$PUSH" == "true" ]]; then
                docker push "$latest_tag"
                log_success "Latest tag pushed: $latest_tag"
            fi
        fi
    fi
}

# Show image information
show_image_info() {
    if [[ "$DRY_RUN" == "true" ]]; then
        return
    fi
    
    local full_image_name="${REGISTRY}${IMAGE_NAME}:${TAG}"
    
    log_info "Image information:"
    echo "\n=== Image Details ==="
    docker images "$full_image_name" --format "table {{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.CreatedAt}}\t{{.Size}}"
    
    echo "\n=== Image History ==="
    docker history "$full_image_name" --format "table {{.CreatedBy}}\t{{.Size}}" | head -10
}

# Cleanup
cleanup() {
    # Remove builder instance if created
    if [[ "$PLATFORM" == *","* && "$DRY_RUN" != "true" ]]; then
        docker buildx rm hydrology-builder 2>/dev/null || true
    fi
}

# Main function
main() {
    parse_args "$@"
    
    # Set trap for cleanup
    trap cleanup EXIT
    
    check_prerequisites
    validate_dockerfile
    get_version_info
    build_image
    push_image
    tag_additional
    show_image_info
    
    log_success "Docker build process completed successfully!"
}

# Run main function
main "$@"