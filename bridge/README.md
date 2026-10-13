# ChatGPT to local llama.cpp bridge

This bridge gives the ChatGPT development conversation practical access to the user's local llama.cpp without exposing any inbound network port.

Security model:
- worker only contacts the local endpoint supplied on its command line
- jobs cannot choose another URL
- jobs cannot execute shell commands
- supported operations are limited to llama_chat, collect_files, run_tests, and run_acceptance
- file collection is confined to the repository root
- jobs/results travel through the dedicated gpt-runtime Git branch

Start from the normal MiniMax H3 checkout:

    python tools/chatgpt_llama_bridge.py

Default llama.cpp endpoint is http://127.0.0.1:8080

For another port:

    python tools/chatgpt_llama_bridge.py --endpoint http://127.0.0.1:PORT

The first launch creates .chatgpt_bridge_worktree, checks out the gpt-runtime mailbox branch there, verifies /v1/models, and starts polling.

Leave the process running while ChatGPT is doing prompt experiments. On Windows, Ctrl+Q stops the active job, publishes its partial result to gpt-runtime, and then exits the bridge. Ctrl+C (or Ctrl+Break) remains an immediate emergency stop and does not guarantee result publication.

## Local test execution

The bridge also supports two fixed, allowlisted execution jobs.

`run_tests` runs only Python unittest module names under `tests.*` against a detached worktree synchronized to the latest `origin/gpt-test-branch`.

`run_acceptance` runs `tests/acceptance/run_acceptance.py` in prompt-generation mode against the allowlisted code branch supplied by `code_branch` (currently `world-state-rebuild`; legacy baseline `gpt-arc-refresh` is also available). Set `benchmark` to `tests/acceptance/gold/amy_medieval_tavern_six.json` for the current six-segment acceptance. The mailbox and results remain on `gpt-runtime`. It uses the main checkout's project virtualenv when present and defaults to `amy.jpg` plus model selector `mistral`. The newest `acceptance_run.json` and `run.log` are copied into the mailbox result automatically. During each acceptance run, the bridge also streams LM Studio model input/output plus prediction stats via `lms log stream --source model --filter input,output --json --stats` and publishes the complete capture as `files/developer_log.jsonl` (with `files/developer_log.stderr.log` for capture diagnostics).

The bridge does not accept arbitrary shell commands.
