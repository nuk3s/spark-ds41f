# Upstream candidates

Work from this site that could go to the recipe, in the form each item would take. Nothing here
is submitted. The base is the tag `spark-ds41f-1120`; upstream `main` holds unreleased candidates
past the tag, so each item needs a rebase onto `main` before a pull request. A pull request also
carries a dated record `experiments/YYYY-MM-DD-short-name/` with the base commit, the one variable,
the exact commands and every run (`AGENTS.md`, "Send improvements back"). "The vLLM fork" means
`local-inference-lab/vllm`, the vLLM source that the recipe pins.

## Disk-tier patches 0830 to 0836

Seven patches to the vLLM fork's `SimpleCPUOffloadConnector` (`local-inference-lab/vllm` at
`19f2c20e` with candidate-62's series), written so that the disk backend can keep session state
for DeepSeek-V4.1-Flash on NVMe. Status: tested on a CPU-only machine; no engine has started with
the tier, and the GPU copy path has not run. The series, the arms, the CPU-only tests and the test
plan (`docs/kv-disk-tier.md`, `docs/kv-disk-tier-test-plan.md`) are prepared for a branch
`kvtier`, not yet published. The patches are unreleased work, so no test figure of the series
appears in this file.

- **Form.** A candidate series in the recipe's layout: an experiment folder whose `vllm/series`
  includes candidate-62's series and appends the seven patches. The patches touch only
  `vllm/v1/simple_kv_offload/`, the connector and tests.
- **Before a pull request.** A run on hardware under the test plan. The patches need new numbers:
  on upstream `main`, read at 2026-11-23T01:14Z, patches 0830 to 0857 belong to candidates 63 to 69.
- **Parts that stand alone.** 0830 (slots padded to 4096 bytes under `O_DIRECT`) is needed by any
  model whose block size is not a multiple of 4096 bytes. 0831 (the VMM-safe declaration) is needed
  with `expandable_segments:True`, which the recipe sets. 0832 is a correctness fix (next section).
- **Where else.** The connector lives in the vLLM fork. Whether mainline vLLM carries the same code
  was not checked.

## The replay cap on external hits

In the vLLM fork at tree `8fc99ca7`, a local prefix hit stops at least
`max(1, replay_tokens)` tokens before the prompt end (`vllm/v1/core/kv_cache_manager.py`, line
407; `replay_tokens` is the coordinator's `prefill_replay_tokens`). Without patch 0832, the lookup
of `SimpleCPUOffloadScheduler.get_num_new_matched_tokens` stops at
`request.num_tokens - 1 - num_computed_tokens` (`vllm/v1/simple_kv_offload/manager.py`, line 361)
and applies no replay cap. DeepSeek-V4.1's CED decoder windows (layers 20 to 39) and DSpark
drafter windows (layers 40 to 42) are not prefix-cached and replay 128 tokens
(`vllm/models/deepseek_v4_1/attention.py`, line 137:
`prefill_replay_window=128 if bounded_replay else 0`).

- **Effect.** Hits land on 256-token boundaries. Without 0832, a turn that ends 1 to 127 tokens
  past a boundary gets an external hit that leaves fewer than 128 tokens to compute. The CED decoder
  and the DSpark drafter then rebuild the windows from a short suffix, where the vLLM fork's comment
  (`kv_cache_manager.py`, lines 391 and 392) asks for "the configured suffix needed to rebuild
  request-private decoder state". By the code, the engine logs no error, and the answer can change;
  the CPU-only test of 0836 shows the short replay. No run on hardware has shown a
  changed answer. A preempted request could also take a hit that runs into the request's generated
  tokens.
- **Evidence.** On a CPU-only machine, the scheduler-level test of patch 0836 runs the unmocked
  `KVCacheManager` and `SimpleCPUOffloadScheduler` on the model's layout. With the cap as released,
  some cases of the test take a hit that leaves fewer than 128 tokens to compute. With 0832 the
  disk hit equals the local hit in every case of the test.
- **Reach.** No shape at the tag sets a KV transfer configuration, so no released shape takes this
  path. Another connector's lookup would need the same rule; the other connectors were not checked.
- **Form.** An issue on the recipe with patch 0832 and the test of 0836.

## Documentation notes

- **The head's start margin at larger pools on the 4 KiB kernel.** On `tp3-triangle-4k` with a
  1,048,576-token context and a 6,144 budget, the head's lowest `MemAvailable` during a start was
  7.12, 6.56 and 5.56 GiB at pools of 2.2, 2.7 and 3.2 GiB a rank. Each pool had one start, in one
  window. At 3.5 GiB the start low was 6.13 GiB, 1.13 GiB above the startup guard of 5 GiB. That
  start ran in the trial, after the site applied two items of the recipe's host baseline. The head
  runs 1.79 GiB short of spark2 and spark3: the head's anonymous memory is 1.71 to 1.75 GiB larger,
  from the API server (RSS 1,431 MiB) and the engine core (RSS 1,268 MiB). The site runs a 1 GiB
  `vm.min_free_kbytes` and a 0.5 GB display carve-out. The shape's reference record reads the
  head's lowest `MemAvailable` at 11.28 GiB, on the 64 KiB-page kernel with the image
  `spark-ds41f:candidate-61-r2`. The site's three bench runs, on the 4 KiB kernel with
  `spark-ds41f:1120`, read 7.11 to 7.65 GiB. A line in the setup guide on the head's start low
  against the pool would help a site size the pool.
- **A 1M context on `tp3-triangle-4k`.** Three serving flags, `--max-num-batched-tokens 6144`,
  `--long-prefill-token-threshold 6096` and `--max-model-len 1048576`, ran a 1,048,576-token
  context on the stock kernel at the 2.2 GiB pool. These are the values of the parent shape
  `tp3-triangle`, which serves 1,048,576 tokens on the 64 KiB kernel. A 960,824-token prompt filled
  in 140.4 s. 17 of 17 long-context coding tickets passed, up to about 836K tokens (one run a
  ticket, graded by program, thinking on). The head's lowest `MemAvailable` over the tickets was
  5.85 GiB. At 2.2 GiB the pool holds 2 full 1M contexts at once by the recipe's count (10,367
  blocks; a 1M request holds 4,142). The shape at the tag serves 262,144.
- **Reasoning effort.** `reasoning_effort` takes an integer from 1 to 100 or a label; the string
  `"30"` gets HTTP 400. By the vLLM fork's code (`REASONING_EFFORT_MAPPINGS`, tree `8fc99ca7`),
  `minimal` and `low` render as 50, `medium`, `high` and `xhigh` as 75, and `max` and `ultra` as
  100. `"none"` turns thinking off in `vllm/tokenizers/deepseek_v41.py` of the same tree, outside
  the mapping. The effort text sits at the start of the prompt in thinking mode, so by the template
  a change of effort misses the cached prefix of every thinking session once.
- **Bench reference.** The shape's reference record
  (`manifests/benchmarks/2026-11-20-spark-ds41f-1120-tp34k.json`) names the image
  `spark-ds41f:candidate-61-r2` and the overlay
  `experiments/2026-11-16-c61-decode/tp3-triangle-4k-dev.json`. The record's live warnings show the
  64 KiB-page kernel `7.0.0-1019-nvidia-64k` on all three nodes. The recipe's README gives the
  record's 11.28 / 13.17 GiB as "Min free RAM (head / workers)" in the row of `tp3-triangle-4k` (4
  KiB). `bin/spark bench` ran three times on `tp3-triangle-4k` with no arm, with `spark-ds41f:1120`
  on the 4 KiB kernel. The runs read 0.9% to 8.4% under the reference record across the 8 decode
  rows. Each run marked 4 rows slower and exited 1. The site runs display carve-out weights off and
  no GID pin, and both settings held in every start. All three runs came before the site disabled
  the twelve idle services and set the recommended APST timeouts. The site sets `host.fan_control`
  false, so the bench ran with no pre-cool and no performance fan curve (`spark_ds41f/bench.py`;
  empty `cooling` and `fan_curve` lists in the site's bench records).

## Watched upstream issues

- **#1036** (XID 43 on 1107). A comment of 2026-11-22 on the issue reports the Engram row reader
  failing on 1120 at a four-node `tp4-ring` site with 64 KiB pages, with a 16,192-token chunk on
  rank 0. Not observed on this site, with a prefill budget of 6,144 and a long-prefill threshold of
  6,096. The overload test's engine log held no error, and no request ended on an engine error in
  the trial's first hours. Whether the smaller chunk lowers the exposure was not tested.
- **#1272.** At a second site, the head's `MemAvailable` before a start reads about 113 GiB after a
  fresh boot and 109.5 to 110.4 GiB after a long uptime. `cluster start` then fails the startup
  guard until a reboot. Every start on this site came after more than a week of host uptime. At
  2026-11-22T15:55Z, a container on each node had run for 3 weeks (spark1, spark2) and 9 days
  (spark3). With no engine running, the head read 113.56 to 115.51 GiB `MemAvailable` (six readings,
  2026-11-21T22:59Z to 2026-11-22T15:41Z), and every start passed the startup guard. The site's
  MemTotal is 123.18 GiB with a 0.5 GB display carve-out, so these readings do not compare directly
  with the issue's. A restart after many days of engine uptime has not run. On the trial's engine
  the API server's RSS grew from 1,431 MiB at 15:55Z to 1,826 MiB at 23:53Z. That growth under load
  is a different quantity from the issue's reading before a start.
