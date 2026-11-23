# Findings: tp3-triangle-4k on three nodes

Durable results of the runs in [`PROGRESS.md`](../../PROGRESS.md), as a reference. Versions: the
tag `spark-ds41f-1120` (vLLM `19f2c20e` with candidate-62's 702 patches), the shape
`tp3-triangle-4k`, kernel `7.0.0-1019-nvidia` with 4 KiB pages, driver 580.178.04. Hardware:
three DGX Spark nodes (GB10, 128 GB of unified memory a node, MemTotal 123.18 GiB), tensor
parallel 3 over a triangle of direct RoCE cables. spark1 is the head. The site runs without display
carve-out weights, without a GID pin and without the GLP vector
([`experiments/lab/README.md`](../../experiments/lab/README.md)). The site's firmware and memory
policy differ from the recipe's ([`PROGRESS.md`](../../PROGRESS.md), "Setup"). Memory figures are
GiB of 1,024 MiB.

Unless a section says otherwise, each figure comes from a window (a block of time on the three
nodes set aside for one set of runs) with no other traffic. The client sent requests direct to the
engine, and each setting ran after one restart. A figure is compared only with figures from the
same window: between two windows the same shape read 7% to 9% apart on cold prefill at 131K and
250K.

## Settings that helped

| Setting (base value) | Effect | Conditions |
|---|---|---|
| `--max-num-batched-tokens 6144` with `--long-prefill-token-threshold 6096` (4096 and 4048), the values of the parent shape `tp3-triangle` | cold prefill 131K 18.2 s against 20.2 s, 250K 34.5 s against 39.3 s; decode, warm turn and depth unchanged; a stream beside a 131K fill 8.6 tok/s for the 22.0 s of the fill; the head's lowest `MemAvailable` 0.5 GiB lower, over different loads (seven measurements at 6,144 against a six-session revisit at the base values) | a cold request to an idle engine, sent twice a size, the slower run reported; the recipe measured the budget's trade-off for `tp3-triangle` in `experiments/2026-10-19-prefill-budget-tp3` |
| `--max-model-len 1048576` (262144) | starts in 201 s; a 960,824-token prompt fills in 140.4 s (6,843 tok/s) with the planted code found; the head's lowest `MemAvailable` 6.15 GiB, against 6.26 and 6.14 GiB at 393K and 524K | stock 4 KiB kernel, with the budget above; at each context one start, one long prompt, a 131K prefill, a decode measurement and (at 524K and 1M) a warm turn |
| `--kv-cache-memory-bytes` 2.7, 3.2 or 3.5 GiB (2.2 GiB) | more sessions kept at 2.7 and 3.2 GiB (see "Session capacity"); not measured at 3.5 GiB | the head's start low fell 580 MiB from 2.2 to 2.7 GiB and 1,018 MiB from 2.7 to 3.2 GiB, one start a pool |
| reasoning effort 50 in place of `high` (75) | hard tasks: 30 of 30 runs pass at 50 and 30 of 30 at 75; reasoning tokens 0.74 of 75's at the median of 30 seed-matched pairs; 2,037 s against 3,038 s for the 30 requests | client traffic beside, 2 streams at a time; runs 1 and 2 of a cell ran the efforts one after another, runs 3 to 5 interleaved the efforts |

No cost of a longer context shows in these single runs: the head's lowest `MemAvailable` in the
row was 6.05, 6.26, 6.14 and 6.15 GiB at 262,144, 393,216, 524,288 and 1,048,576 tokens. At the 2.2
GiB pool, 2 full 1M contexts fit at once by the recipe's count (10,367 pool blocks; a 1M request
holds 4,142). At 3.5 GiB the engine counts 16,494 blocks, room for 3. On this shape a
1,048,576-token context ran on the stock 4 KiB-page kernel. The 64 KiB-page kernel was not tested
on this site, and the recipe qualifies this shape at 262,144 tokens.

## Settings that did not help

| Setting (base value) | Effect | Verdict |
|---|---|---|
| `--long-prefill-token-threshold 2000` (4048) | cold prefill 131K 28.1 s against 20.2 s. A stream beside a fill ran faster during the fill (14.9 to 16.3 tok/s against 11.0), but the fill took 37.8 s against 25.7 s, so the stream lost more time to the fill: about 29 s against 21 s | rejected |
| `--prefix-cache-retention-interval 2048` (512) | 9 of 18 long sessions kept (1.61M tokens) against 8 (1.39M); a warm turn on a 131K session 0.78 s against 0.57 s | not adopted |
| reasoning effort 25 | 29 of 30 hard tasks; the same median reasoning ratio as 50 (0.74 of 75) and 8% less time than 50 (1,874 s against 2,037 s); client traffic beside | one more miss than 50 |
| reasoning effort 10 | 9 of 12 hard tasks (the probability task twice, the schedule once); client traffic beside | too low |
| thinking off | 22 of 30 short tasks; the counting and weekday tasks failed 3 of 3; client traffic beside | not for checkable tasks |
| temperature 0.8 or 0.6, or top_p 0.95, against long reasoning tails | 0 tails in 90 replies each, against 1 in 90 at the default (p 0.5); client traffic beside | no effect shown |

## Session capacity

A row fills 18 long sessions (3.28M tokens, a prefix of each session's own) and revisits the
sessions newest first until two in a row miss. Each row ran once.

| KV pool a rank | Context and budget | Sessions kept | Tokens kept | The head's lowest `MemAvailable` in the row |
|---|---|---|---|---|
| 2.2 GiB, retention 512 | 262,144, budget 4,096 | 8 | about 1.39M | not read |
| 2.2 GiB, retention 2,048 | 262,144, budget 4,096 | 9 | about 1.61M | not read |
| 2.7 GiB | 1,048,576, budget 6,144 | 10 | about 1.74M | 5.56 GiB (4.89 GiB under overload) |
| 3.2 GiB | 1,048,576, budget 6,144 | 11 | about 2.16M | 4.80 GiB |
| 3.5 GiB | 1,048,576, budget 6,144 | not measured | about 2.4M (an estimate from the rows above, about 0.77M a GiB) | 6.13 GiB at the start, 5.08 GiB under 4 x 500K, 4.15 GiB on client traffic to 2026-11-23T00:04Z |

The arm `tp3-4k-b6144-m1m` (1,048,576 tokens, 2.2 GiB) read 5.85 GiB at the lowest over the
long-context tickets. No revisit row ran at 3.5 GiB. The 3.5 GiB readings come from the trial,
after the site applied two items of the recipe's host baseline on 2026-11-22
([`PROGRESS.md`](../../PROGRESS.md), "Setup").

- A kept session answered in 0.4 to 0.6 s. A lost session took 11 to 38 s to fill again; a 500K
  session takes about 70 s.
- Kept state costs about 1,600 to 1,700 bytes a token a rank. At the start of the 3.5 GiB pool the
  pool's own count is 3,808,295 tokens, about 987 bytes a token. The start figure counts mostly
  compressed positions, and a session also keeps checkpoints of the window layers. The pool is a
  full copy on each rank, so spark1's `MemAvailable` bounds the pool.
- Overload, 2.7 GiB pool: eight streams, each on a 499.5K-token context of the stream's own, asked
  4M tokens of the pool. All eight requests completed, and the engine logged no error. The engine
  filled one prompt at a time, and the first tokens came after 2.4, 83, 164, 242, 321, 403, 483 and
  562 s.
- Depth cost about 2% of decode speed in one run on the 2.7 GiB pool: eight streams on 1.15M
  tokens together decoded at 187.9 tok/s, against 192.1 tok/s on 30K contexts.

## Memory on the head

spark1 runs the API server and the engine core, so the head has less `MemAvailable` than spark2 and
spark3. Snapshot 12 minutes after the engine start on the 3.5 GiB pool (about 10 minutes after the
API was ready), under client traffic with 5 requests running (GiB):

| Line | spark1 | spark2, spark3 |
|---|---:|---:|
| MemTotal | 123.18 | 123.18 |
| GPU, worker process | 101.59 | 101.79 to 101.91 |
| Anonymous | 5.48 | 3.73 to 3.77 |
| Page cache | 6.92 | 6.74 to 6.99 |
| Slab | 2.43 | 2.40 to 2.45 |
| In no `/proc/meminfo` line | 3.85 | 3.99 to 4.20 |
| MemFree | 2.81 | 3.96 to 4.20 |
| MemAvailable | 5.22 | 7.00 to 7.01 |

- The head's anonymous memory is 1.71 to 1.75 GiB above the anonymous memory of spark2 and
  spark3: the API server (RSS 1,431 MiB) and the engine core (RSS 1,268 MiB) run only on the head.
  That difference explains most of the head's 1.79 GiB deficit in `MemAvailable`.
- Margins on the 3.5 GiB pool: the start low of 6.13 GiB sat 1.13 GiB above the recipe's startup
  guard of 5 GiB. Against the steady guard of 3 GiB, the head kept 2.08 GiB under the 4 x 500K
  probe (5.08 GiB). In the first half hour of client traffic the head kept 1.48 GiB (4.48 GiB). The
  lowest one-minute sample to 2026-11-23T00:04Z, 4.15 GiB at 22:31Z, left 1.15 GiB.
- On client traffic, ten-minute means of the head's `MemAvailable` fell from 5.42 GiB to 5.07 GiB
  in the first hour, then held at 4.91 to 5.06 GiB from 17:20Z to 18:20Z. The median of the 480
  one-minute samples from 15:59Z to 2026-11-23T00:04Z was 4.97 GiB. The API server's RSS grew from
  1,431 MiB at 15:55Z to 1,699 MiB at 18:00Z, then in steps to 1,773 MiB at 20:19Z and 1,826 MiB
  at 23:53Z. To 18:20Z the engine core and the rank-0 worker stayed flat, and so did the page
  cache from 17:23Z, when the page cache's sampling began.
- The site sets `vm.min_free_kbytes` to 1 GiB (1,048,576 kB). On the 4 KiB kernel the recipe
  leaves the kernel's value. On the 64 KiB kernel the recipe sets 45,166 kB, a value that
  `host/kernel-memory/README.md` gives as the reserve observed on the original 4 KiB profile. By
  computation from the kernel's watermarks, `MemAvailable` leaves out about 3.2 GiB on this site
  (1.99 GiB of watermark reserve and 1.25 GiB of page cache held back). The same computation with
  the recipe's reserve gives about 1 GiB (an estimate). The guards read `MemAvailable`.
- Upstream's reference record for this shape
  (`manifests/benchmarks/2026-11-20-spark-ds41f-1120-tp34k.json`, `memory.dgx1.min_available_gib`)
  reads the head's lowest `MemAvailable` at 11.28 GiB. The record names the image
  `spark-ds41f:candidate-61-r2` and the overlay
  `experiments/2026-11-16-c61-decode/tp3-triangle-4k-dev.json`. The record's live warnings show the
  64 KiB-page kernel `7.0.0-1019-nvidia-64k` on all three nodes. The three bench runs on this site,
  with the release image `spark-ds41f:1120` on the 4 KiB kernel, read 7.39, 7.11 and 7.65 GiB. The
  page size and the image differ. The site's firmware and memory policy also differ from the
  recipe's, so the margins here hold for this site only.

## Reasoning effort

- The engine takes `chat_template_kwargs.reasoning_effort` as an integer from 1 to 100 or as a
  label. By the vLLM fork's code (`REASONING_EFFORT_MAPPINGS` in
  `vllm/tokenizers/deepseek_v41_encoding.py`, tree `8fc99ca7`), `minimal` and `low` render as 50,
  `medium`, `high` and `xhigh` as 75, and `max` and `ultra` as 100. `"none"` turns thinking off in
  `vllm/tokenizers/deepseek_v41.py` of the same tree, outside the mapping. No rendered prompt was
  read on this site. The string `"30"` gets HTTP 400.
- The effort text sits at the start of the rendered prompt, in thinking mode only. By the template,
  the next turn of each thinking session misses the whole cached prefix once after any change of
  effort, from a client or a gateway (not measured).
- Short checkable tasks: from 10 to 75 the median reasoning length stays between 57 and 85 tokens
  and the median time between 2.6 and 3.8 s, with no trend across efforts. Each cell ran 3 times,
  and the engine's load changed between the settings.
- Hard checkable tasks (six tasks, 5 runs a cell): reasoning tokens at the median 1,236 at 25,
  1,311 at 50, 1,853 at 75. Effort 100, two runs a cell, wrote about twice the tokens of 25 to 50.
- A slice of a task battery (23 cells, the same seeds): 20 pass at 50 and 18 at 75, with 52% fewer
  reasoning tokens in sum at 50. Each cell ran once an effort, so the pass counts cannot be told
  from noise.

## Long reasoning tails

An easy prompt at effort 75 sometimes writes a long reasoning tail: in 1 run of 10 at the default
sampling, with client traffic beside, 2,796 reasoning tokens and 142.6 s. Over 360 replies on three
easy prompts, with client traffic beside (a median of 6 requests running), a tail of more than 600
reasoning tokens came in 1 of 90 at temperature 1.0 and top_p 1.0. Each other setting had 0 tails in
90: temperature 0.8, temperature 0.6, and temperature 1.0 with top_p 0.95 (p 0.5). The tail rate is
about 1% to 5% of easy requests, and no sampling setting is shown to change the rate.

## Images

The head's API server decodes every image of a request at the image's source size in host memory.
`serve_args` at the tag accept 67 images a request (`--limit-mm-per-prompt {"image":67}`) of up
to 16,777,216 pixels. On `spark-ds41f-1025` the recipe measured 61 to 74 MiB in flight for a 12 MP
photo, 310 MiB at 48 MP and 790 MiB for one image at 178.9 MP. Four JPEGs at 178.9 MP peaked at
5.2 GiB (`docs/current-state.md`). That one point gives a peak factor of 1.69 over the
single-image figure. From those figures one request can take about 1.3 GiB at 8 JPEG images and
about 2.6 GiB at 16 at the pixel cap; PNG with alpha takes about 1.6 times more (estimates). The
head's margin above the steady guard was 2.08 GiB under the 4 x 500K probe and 1.15 GiB at the
lowest one-minute sample on client traffic to 2026-11-23T00:04Z. No run shows that 8 images a
request at the pixel cap keep the head above the steady guard. The site limits a request to 8
images in front of the engine.

## Starts and disk

- A first start with an empty JIT cache took 25 minutes: 129 s for the weights (94.7 GiB a rank),
  then the Engram tables on disk, 386 kernel compiles and a warm-up of 300 compile keys. The eight
  restarts of the tuning window took 154 to 201 s to a ready API; the two starts of the trial took
  216 s and 154 s.
- An image build from source took 19 minutes on one node.
- Disk a node: model 476 GiB, image 27 GB, Engram tables 66 GiB (written at the first start), JIT
  cache 0.1 to 0.5 GiB.

## The recipe's bench

`bin/spark bench` ran three times on `tp3-triangle-4k` with no arm on 2026-11-22, at 00:47Z,
03:23Z and 06:47Z, with the default suites `quality` and `decode`. Each run passed quality 5 of 5
and marked 4 of the 8 decode rows slower than the reference record (the 95% interval below the
reference record):

| Start (UTC) | Rows marked slower, under the reference record | All 8 rows, under the reference record | The head's lowest `MemAvailable` |
|---|---|---|---|
| 00:47 | 3.6% to 6.3% | 3.6% to 8.4% | 7.39 GiB |
| 03:23 | 4.1% to 6.3% | 1.0% to 6.3% | 7.11 GiB |
| 06:47 | 3.1% to 4.0% | 0.9% to 4.3% | 7.65 GiB |

The bench exited 1 on the gap each time, and the cause is not known. No thermal slowdown and no
swap growth showed; the GPUs reached at most 64 °C. The differences from the reference record,
and the site settings during the three runs that differ from the recipe's:

- the build and the kernel: the reference record names the image `spark-ds41f:candidate-61-r2`
  and shows the 64 KiB-page kernel on all three nodes; the site ran `spark-ds41f:1120` on the
  4 KiB kernel;
- display carve-out weights off and no GID pin;
- `host.fan_control` false: the tag's bench then skips the pre-cool and the performance fan curve
  (`spark_ds41f/bench.py`), and the site's bench records hold empty `cooling` and `fan_curve`
  lists; the reference record shows the fan-curve service already running on the three nodes;
- the twelve idle services on and APST at the kernel's timeouts, two items of the recipe's host
  baseline that the site applied later on 2026-11-22 ([`PROGRESS.md`](../../PROGRESS.md),
  "Setup");
- NVMe interrupt coalescing on, which the setup guide lists as optional.

## Gaps in coverage

- Answer quality beyond program-graded floor tests and one task battery of 2 runs an item.
- More than 8 sequences, a restart of one rank, a soak longer than the trial's first hours.
- A restart after many days of engine uptime. Every start so far came after more than a week of
  host uptime.
- KV pools of 3.7 and 4.0 GiB, a budget of 8,192, the 64 KiB-page kernel with upstream's memory
  saver (`docs/setup.md`, "2. Kernel (64 KiB profiles)").
- The effect of the NVMe power-state change.
