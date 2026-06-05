#!/bin/bash

# Operations script for RAG system
# Usage: ./bin/ops.sh [start|stop|restart|logs|status]

set -e

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PID_FILE="$PROJECT_ROOT/.flask.pid"
LOG_FILE="$PROJECT_ROOT/logs/flask.log"
ENV_FILE="$PROJECT_ROOT/.env"

# Flask settings
HOST="${FLASK_HOST:-127.0.0.1}"
PORT="${FLASK_PORT:-5000}"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Ensure logs directory exists
mkdir -p "$(dirname "$LOG_FILE")"

# Load environment if exists
if [ -f "$ENV_FILE" ]; then
    export $(cat "$ENV_FILE" | grep -v '^#' | xargs)
fi

start() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Flask is already running (PID: $PID)${NC}"
            return 1
        else
            rm -f "$PID_FILE"
        fi
    fi

    echo -e "${GREEN}Starting Flask server...${NC}"

    # Start Flask in background
    cd "$PROJECT_ROOT"
    nohup uv run python run.py > "$LOG_FILE" 2>&1 &

    echo $! > "$PID_FILE"

    sleep 2

    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}Flask started successfully (PID: $PID)${NC}"
            echo -e "Access: ${GREEN}http://$HOST:$PORT${NC}"
            return 0
        fi
    fi

    echo -e "${RED}Failed to start Flask${NC}"
    return 1
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo -e "${YELLOW}Flask is not running${NC}"
        return 0
    fi

    PID=$(cat "$PID_FILE")

    if ps -p "$PID" > /dev/null 2>&1; then
        echo -e "${GREEN}Stopping Flask (PID: $PID)...${NC}"
        kill "$PID"
        sleep 1

        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${YELLOW}Force stopping...${NC}"
            kill -9 "$PID"
        fi

        rm -f "$PID_FILE"
        echo -e "${GREEN}Flask stopped${NC}"
    else
        echo -e "${YELLOW}Flask was not running (stale PID file)${NC}"
        rm -f "$PID_FILE"
    fi
}

restart() {
    stop
    sleep 1
    start
}

logs() {
    if [ ! -f "$LOG_FILE" ]; then
        echo -e "${YELLOW}No log file found${NC}"
        return 1
    fi

    tail -f "$LOG_FILE"
}

status() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if ps -p "$PID" > /dev/null 2>&1; then
            echo -e "${GREEN}Flask is running (PID: $PID)${NC}"
            echo -e "Access: ${GREEN}http://$HOST:$PORT${NC}"
            echo "Log file: $LOG_FILE"
            return 0
        else
            echo -e "${RED}Flask is not running (stale PID file)${NC}"
            return 1
        fi
    else
        echo -e "${RED}Flask is not running${NC}"
        return 1
    fi
}

# Main
case "${1:-}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|logs|status]"
        exit 1
        ;;
esac
