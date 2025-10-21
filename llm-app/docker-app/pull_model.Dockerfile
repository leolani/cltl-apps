#syntax=docker/dockerfile:1.4

FROM ollama/ollama:latest

SHELL ["/bin/bash", "-c"]

COPY <<-EOT ./pull.sh
  echo "Checking $LLM on $OLLAMA_HOST...";
  if /bin/ollama show "$LLM" --modelfile >/dev/null 2>&1; then
    echo "Model '$LLM' already present.";
  else
    /bin/ollama pull "$LLM";
  fi
EOT

ENTRYPOINT /pull.sh