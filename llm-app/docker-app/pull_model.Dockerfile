#syntax=docker/dockerfile:1.4
FROM ollama/ollama:latest

ENTRYPOINT ["/bin/sh","-c","\
  echo \"Checking $LLM on $OLLAMA_HOST...\"; \
  if /bin/ollama show \"$LLM\" --modelfile >/dev/null 2>&1; then \
    echo \"Model '$LLM' already present.\"; \
    \
  else \
    # Print status update \
    ( while :; do echo \"... pulling '$LLM' ...\"; sleep 5; done ) & T=$!; \
    \
    /bin/ollama pull \"$LLM\"; \
    \
    # Kill status update \
    kill $T 2>/dev/null || true; wait $T 2>/dev/null || true; \
  fi \
"]
