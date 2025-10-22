#syntax=docker/dockerfile:1.4

FROM ollama/ollama:latest

SHELL ["/bin/bash", "-c"]

# <<-'EOT' is Bash semantics for heredocs with no expansion (literal text), but allows tab stripping.
COPY --chmod=500 <<-'EOT' ./pull.sh
	echo "Checking $CLTL_LLM on $OLLAMA_HOST...";
	if /bin/ollama show "$CLTL_LLM" --modelfile >/dev/null 2>&1; then
		echo "Model '$CLTL_LLM' already present.";
	else
		echo "Pulling '$CLTL_LLM'...";
		/bin/ollama pull "$CLTL_LLM";
	fi
EOT

ENTRYPOINT /pull.sh