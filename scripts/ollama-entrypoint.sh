#!/bin/bash
set -euo pipefail

# Start Ollama server in background
/bin/ollama serve &
OLLAMA_PID=$!

# Wait for server to be ready
echo "Waiting for Ollama server..."
until curl -sf http://localhost:11434/api/tags > /dev/null 2>&1; do
  sleep 2
done
echo "Ollama server ready."

# Pull model(s) — idempotent, skips if already cached in volume
for MODEL in ${OLLAMA_MODELS//,/ }; do
  echo "Pulling model: $MODEL"
  ollama pull "$MODEL"
done

echo "Model(s) ready. Ollama serving."
wait $OLLAMA_PID
