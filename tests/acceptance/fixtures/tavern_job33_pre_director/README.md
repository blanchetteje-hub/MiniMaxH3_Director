# Job 33 pre-Director replay fixture

Captured from bridge job
`accept-world-state-rebuild-tavern-20261011-33-director-baseline`.
The pre-Director WorldState has zero completed Segments and its SHA-256 matches
the first captured `director_raw_scene` request. The fixture stores the accepted
planning/canon inputs, canonical WorldState, Subject/Picture identity mappings,
location data, and the first Director request as an exact replay check. It does
not restore legacy ledgers or the failed Director attempt.

Example prompt-only invocation:

```sh
python minimax.py 8 6 0.5 --refresh 999999 --vision-continuity 0 --model gpt --image1 amy.jpg --pre-director-replay-fixture tests/acceptance/fixtures/tavern_job33_pre_director/replay.json
```

The replay option forces prompt-only mode. The fixture is temporary test data;
remove it when this replay path is no longer needed.
