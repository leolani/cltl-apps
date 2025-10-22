#syntax=docker/dockerfile:1.4

FROM ollama/ollama:latest

SHELL ["/bin/bash", "-c"]

# <<-'EOT' is Bash semantics for heredocs with no expansion (literal text), but allows tab stripping.
COPY --chmod=500 <<-'EOT' ./pull.sh
	echo "Checking $LLM on $OLLAMA_HOST...";
	if /bin/ollama show "$LLM" --modelfile >/dev/null 2>&1; then
		echo "Model '$LLM' already present.";
	else
		echo "Pulling '$LLM'...";
		/bin/ollama pull "$LLM";
	fi
EOT

ENTRYPOINT /pull.sh