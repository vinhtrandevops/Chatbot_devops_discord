#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print with color
print_message() {
    color=$1
    message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if Docker is running
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        print_message $RED "Error: Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Stop and remove existing container if it exists
cleanup() {
    print_message $YELLOW "Cleaning up existing containers..."
    docker stop discord-bot >/dev/null 2>&1
    docker rm discord-bot >/dev/null 2>&1
}

# Build the Docker image
build() {
    print_message $YELLOW "Building Docker image..."
    docker build -t discord-bot:latest .
    
    if [ $? -eq 0 ]; then
        print_message $GREEN "Docker image built successfully!"
        return 0
    else
        print_message $RED "Failed to build Docker image."
        return 1
    fi
}

# Run the container
run() {
    print_message $YELLOW "Starting Discord bot container..."
    docker run -d \
        --name discord-bot \
        --restart unless-stopped \
        discord-bot:latest
    
    if [ $? -eq 0 ]; then
        print_message $GREEN "Discord bot container is running!"
        print_message $YELLOW "Showing logs:"
        docker logs -f discord-bot
        return 0
    else
        print_message $RED "Failed to start the container."
        return 1
    fi
}

# Show menu
show_menu() {
    clear
    print_message $BLUE "╔════════════════════════════════════╗"
    print_message $BLUE "║      Discord Bot Docker Menu       ║"
    print_message $BLUE "╠════════════════════════════════════╣"
    print_message $BLUE "║                                    ║"
    print_message $BLUE "║  1. Build Docker Image            ║"
    print_message $BLUE "║  2. Build and Run Container       ║"
    print_message $BLUE "║  3. Show Container Logs           ║"
    print_message $BLUE "║  4. Stop Container                ║"
    print_message $BLUE "║  5. Exit                         ║"
    print_message $BLUE "║                                    ║"
    print_message $BLUE "╚════════════════════════════════════╝"
    echo ""
    print_message $YELLOW "Please enter your choice [1-5]: "
}

# Show container logs
show_logs() {
    if docker ps -q -f name=discord-bot >/dev/null 2>&1; then
        print_message $YELLOW "Container logs:"
        docker logs discord-bot
    else
        print_message $RED "Container is not running!"
    fi
}

# Stop container
stop_container() {
    if docker ps -q -f name=discord-bot >/dev/null 2>&1; then
        print_message $YELLOW "Stopping container..."
        docker stop discord-bot
        print_message $GREEN "Container stopped successfully!"
    else
        print_message $RED "Container is not running!"
    fi
}

# Main loop
while true; do
    show_menu
    read -r choice
    
    case $choice in
        1)
            check_docker
            build
            print_message $YELLOW "Press Enter to continue..."
            read
            ;;
        2)
            check_docker
            cleanup
            if build; then
                run
            fi
            ;;
        3)
            show_logs
            print_message $YELLOW "Press Enter to continue..."
            read
            ;;
        4)
            stop_container
            print_message $YELLOW "Press Enter to continue..."
            read
            ;;
        5)
            print_message $GREEN "Goodbye!"
            exit 0
            ;;
        *)
            print_message $RED "Invalid option! Please try again."
            sleep 2
            ;;
    esac
done