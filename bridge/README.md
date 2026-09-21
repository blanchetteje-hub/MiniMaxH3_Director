# ChatGPT to local llama.cpp bridge

This bridge gives the ChatGPT development conversation practical access to the user's local llama.cpp without exposing any inbound network port.

Security model:
- worker only contacts the local endpoint supplied on its command line
- jobs cannot choose another URL
- jobs cannot execute shell commands
- supported operations are limited to llama_chat and collect_files
- file collection is confined to the repository root
- jobs/results travel through the dedicated gpt-runtime Git branch

Start from the normal MiniMax H3 checkout:

    python tools/chatgpt_llama_bridge.py

Default llama.cpp endpoint is http://127.0.0.1:8080

For another port:

    python tools/chatgpt_llama_bridge.py --endpoint http://127.0.0.1:PORT

The first launch creates .chatgpt_bridge_worktree, checks out the gpt-runtime mailbox branch there, verifies /v1/models, and starts polling.

Leave the process running while ChatGPT is doing prompt experiments. Ctrl+C stops it.
