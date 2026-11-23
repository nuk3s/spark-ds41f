# Progress on a three-node triangle

A dated log, newest first, of the runs of `spark-ds41f-1120` at one site with three DGX Spark
nodes. Durable results: [`docs/lab/findings.md`](docs/lab/findings.md). Work that could go
upstream: [`docs/lab/upstream-candidates.md`](docs/lab/upstream-candidates.md).

## Setup

| Item | Value |
|---|---|
| Recipe | tag `spark-ds41f-1120` (`d3d40d94`), image built from source on spark2 (19 minutes) |
| Shape | `tp3-triangle-4k`, with the arms of [`experiments/lab/`](experiments/lab/README.md) |
| vLLM | `local-inference-lab/vllm` `19f2c20e` with candidate-62's series: 702 patches, tree `8fc99ca7` |
| Model | DeepSeek-V4.1-Flash-1017, revision `1bae0e10` |
| Nodes | three DGX Spark (GB10), 128 GB of unified memory a node (MemTotal 123.18 GiB) |
| Firmware | UEFI Display Reserved Memory (the size of the display carve-out) set to 0.5 GB, which adds 1.495 GiB to MemTotal against the firmware's default |
| Host | kernel `7.0.0-1019-nvidia` with 4 KiB pages, driver 580.178.04 |
| Memory policy | `vm.min_free_kbytes` 1 GiB (1,048,576 kB); the recipe sets 45,166 kB on the 64 KiB kernel only, a value that `host/kernel-memory/README.md` gives as the reserve observed on the original 4 KiB profile |
| Fabric | a triangle of three direct cables, RoCE, tensor parallel 3 |
| Roles | spark1 is the head (rank 0, API server, engine core); spark2 and spark3 hold ranks 1 and 2 |

Site settings that differ from the recipe: display carve-out weights off on `tp3-triangle-4k`, no
GID pin, no GLP vector and fan control off (details in
[`experiments/lab/README.md`](experiments/lab/README.md)). On the hosts, `nvidia-drm` mode setting
is off and NVMe interrupt coalescing is on. Two items of the recipe's host baseline (the table of
host changes in `docs/setup.md`) were applied on the three nodes on 2026-11-22, after the three
bench runs. The twelve services that `doctor --live` reports as unused on a headless inference node
have been disabled since 13:45Z ("Headless boot: the trade-off"). The NVMe power-state (APST)
timeouts have been the recommended 2,000 ms and 60,000 ms since 15:41Z, in place of the kernel's
100 ms and 2,000 ms. The recipe's setup guide reports 3% more throughput on TP3 at 8 streams with
the drive kept awake. The effect of the APST change was not measured on this site.

Numbers below come from the engine's own counters and `/metrics`, `MemAvailable` from
`/proc/meminfo` on each node (GiB of 1,024 MiB), and request timings at the client. A window, in
this log, is a block of time on the three nodes set aside for the runs of one entry. Unless an
entry says otherwise, each row ran direct to the engine with no other traffic.

## Log

### 2026-11-22 20:22Z: disk tier for session state, CPU-only tests

- **Run.** Seven patches (0830 to 0836) for the disk backend of the vLLM fork's
  `SimpleCPUOffloadConnector`, tested on a CPU-only x86-64 machine against the vLLM fork at tree
  `8fc99ca7`. The patches are unreleased work, so the test figures are not published here
  (`AGENTS.md`, "Hold benchmarks of unreleased work").
- **Finding.** Without patch 0832, a CPU or disk hit could end closer than 128 tokens to the prompt
  end. The CED decoder windows and the DSpark drafter windows replay 128 tokens, so by the vLLM
  fork's code such a hit runs the decoder and the drafter on a partial window with no error. The
  CPU-only scheduler test of patch 0836 produces such a hit. No model ran on the CPU-only machine,
  and no changed answer has been observed. Local hits never had this gap.
- **Status.** Tested on a CPU-only machine; not run on hardware. The patches, the arms and the test
  plan are prepared for a branch `kvtier`, not yet published.

### 2026-11-22 20:18Z: at most 8 images a request

- **Why.** The head's API server decodes every image of a request in host memory. The shape
  accepts 67 images a request (`--limit-mm-per-prompt {"image":67}`) of up to 16,777,216 pixels
  each. Under the 4 x 500K overload probe the head had 2.08 GiB above the recipe's 3 GiB steady
  guard. On client traffic the margin was 1.48 GiB at the lowest in the first half hour and 1.16
  GiB at the lowest one-minute sample to 18:23Z. On `spark-ds41f-1025` the recipe measured 61 to 74
  MiB in flight for a 12 MP photo, 310 MiB at 48 MP and 790 MiB for one image at 178.9 MP. Four
  JPEGs at 178.9 MP peaked at 5.2 GiB. That one point gives a peak factor of 1.69 over the
  single-image figure. From those figures, 8 JPEG images at the pixel cap take about 1.3 GiB and
  16 about 2.6 GiB; PNG with alpha takes about 1.6 times more (estimates; not measured on this
  site).
- **Change.** The API gateway in front of the engine passes the newest 8 images of a request and
  replaces each older image with a short text marker. No engine restart.
- **Check.** Through the gateway, with thinking on and with thinking off, the model saw all 8
  images of an 8-image request. In a 10-image request the model saw the newest 8 and reported
  images 1 and 2 as removed.

### 2026-11-22 19:17Z: reasoning effort 50 in place of `high`

The engine takes the effort in `chat_template_kwargs` as `reasoning_effort`, an integer from 1 to
100 or a label. By the vLLM fork's code (`REASONING_EFFORT_MAPPINGS` in
`vllm/tokenizers/deepseek_v41_encoding.py`, tree `8fc99ca7`), `minimal` and `low` render as 50,
`medium`, `high` and `xhigh` as 75, and `max` and `ultra` as 100. `"none"` turns thinking off in
`vllm/tokenizers/deepseek_v41.py` of the same tree, outside the mapping. No rendered prompt was
read on this site. The string `"30"` is refused with HTTP 400. All runs below went direct to the
engine, 2 streams at a time, with client traffic beside the runs.

- **Short tasks** (ten checkable tasks, 3 runs a cell, 16:05Z to 16:11Z):

  | Setting | Passes of 30 | Reasoning tokens, median / max | Total, median s | Total, p90 s |
  |---|---|---|---|---|
  | thinking off | 22 | 0 / 0 | 1.0 | 3.3 |
  | effort 10 | 30 | 85 / 334 | 3.8 | 9.4 |
  | effort 25 | 30 | 57 / 190 | 2.9 | 5.7 |
  | effort 50 | 29 | 66 / 204 | 2.6 | 6.6 |
  | effort 75 (`high`) | 29 | 78 / 295 | 3.0 | 7.8 |
  | effort 100 | 30 | 111 / 640 | 3.8 | 12.3 |

  Thinking off failed the counting task and the weekday task 3 of 3, and one run each of two
  arithmetic tasks. The misses at 50 and 75 are the same tool task: two calls where the check
  wanted one. From 10 to 75 the reasoning length and the time show no trend across efforts on these
  tasks. The engine's load changed between the settings: a median of 4 requests running at effort
  10 and with thinking off, 3 at the others.
- **Hard tasks** (a logic grid, a two-worker schedule, a dice probability, one planted bug in a
  163-line module, a SQL question, a minimum-moves puzzle; 5 runs a cell, 30 requests an effort,
  16:22Z to 18:07Z). Runs 1 and 2 ran the efforts one after another, with a median of 2 requests
  running on the engine. Runs 3 to 5 interleaved the efforts, with a median of 4 to 4.5 running.

  | Effort | Passes of 30 | Reasoning tokens, median | Total s, median / sum |
  |---|---|---|---|
  | 25 | 29 | 1,236 | 41.4 / 1,874 |
  | 50 | 30 | 1,311 | 47.2 / 2,037 |
  | 75 (`high`) | 30 | 1,853 | 90.1 / 3,038 |

  Paired on task and seed, the ratio of reasoning tokens at 50 to reasoning tokens at 75 has a
  median of 0.74 (interquartile range 0.61 to 0.92). Of the 30 pairs, 25 are under 1. Effort 10
  failed 3 of 12 in the first two runs a cell. In those two runs a cell, effort 100 wrote about
  twice the reasoning tokens of efforts 25 to 50, on a busier engine (a median of 6 requests
  running).
- **Task battery slice** (18:16Z to 19:20Z): the 23 cells of families B to F of the task battery
  (2026-11-22 06:47Z entry) that had run at 75, with the same seeds, 2 streams at a time, with 1 to
  3 client requests beside.

  | Family | Cells | Pass at 50 | Pass at 75 | Median reasoning tokens, 50 / 75 |
  |---|---|---|---|---|
  | B | 10 | 10 | 10 | 2,292 / 7,325 |
  | C | 4 | 2 | 2 | 19,835 / 34,428 |
  | D | 1 | 1 | 1 | 2,266 / 4,035 |
  | E | 5 | 4 | 3 | 952 / 2,065 |
  | F | 3 | 3 | 2 | 4,393 / 7,537 |
  | all | 23 | 20 | 18 | sum 130,734 / 271,042 |

  By the stop types that the battery records, the misses at 50 are two wrong answers and one stop
  that gave up. The misses at 75 are three wrong answers, one stop that gave up and one stop at the
  turn limit. Neither effort had a tool-call format failure or a stop at the output cap. Four cells
  differ in verdict (three pass only at 50, one only at 75). Each cell ran once an effort, so the
  difference cannot be told from noise. Wall times are not compared: the 75 cells ran 8 streams at
  a time with no other traffic.
- **Change.** Since 19:17Z the API gateway has sent the engine effort 50 on requests that carry
  `high`; the engine still renders `high` as 75. By the vLLM fork's template the effort text sits
  at the start of the rendered prompt, in thinking mode only. A change of effort therefore makes
  the prefix cache miss once for every session on the thinking route, at the session's next turn
  (not measured). A session of 500K tokens then pays a fill of about 70 s.

### 2026-11-22 17:11Z to 17:25Z: long reasoning tails and sampling

- **Run.** Three easy prompts at effort 75, 30 seeds a cell, the settings interleaved, 2 streams
  at a time direct to the engine. Client traffic ran beside (a median of 6 requests running when a
  test request was sent). A tail is a reply with more than 600 reasoning tokens. The times in
  seconds include the client load.

  | Sampling | Tails of 90 | Reasoning tokens, median / p90 / max | Total s, median / p90 / max |
  |---|---|---|---|
  | temperature 1.0, top_p 1.0 (the engine's default) | 1 | 86 / 183 / 681 | 3.9 / 7.7 / 32.9 |
  | temperature 0.8 | 0 | 78.5 / 188 / 269 | 3.4 / 7.7 / 14.8 |
  | temperature 0.6 | 0 | 75 / 184 / 355 | 3.2 / 7.3 / 13.8 |
  | temperature 1.0, top_p 0.95 | 0 | 78 / 185 / 450 | 3.6 / 10.0 / 20.4 |

  All 360 replies passed. Fisher's exact test, one-sided, the default against each other setting:
  p 0.5. An earlier run on one of the prompts gave 1 tail in 10 at the default against 0 in 20 at
  temperatures 0.6 and 0.2 (p 0.33). Pooled with 2 tails in 3 requests of the same prompt through
  the gateway at the cutover, the count was 3 in 13 against 0 in 20 (p about 0.05). The larger run
  does not repeat that lead.
- **Result.** The tail is rare (about 1% to 5% of easy requests). These data show no sampling
  setting that removes the tail, so sampling stays at the model card's values.

### 2026-11-22 15:52Z: the trial, first hours

The arm `tp3-4k-b6144-m1m-kv35` (budget 6,144, context 1,048,576, KV pool 3.5 GiB a rank, 8
sequences) took client traffic from 15:52Z: requests from the site's own clients through an API
gateway. The clients send coding, chat, long-session and batch traffic. Nothing on the client side
changed.

- **Start.** The shape `tp3-triangle-4k` as configured on the site (context 262,144, KV pool 2.2
  GiB) started in 216 s. The switch to the 3.5 GiB pool took 154 s to a ready API. Lowest
  `MemAvailable` during that start: spark1 6.13 GiB, spark2 7.21, spark3 7.06. The recipe's
  startup guard acts at 5 GiB, so the head's margin at the start was 1.13 GiB.
- **Overload probe** (15:45Z to 15:51Z). Four sessions of 499.5K tokens each, filled one by one in
  70.1 to 70.7 s each, then sent at once. The four decoded at 30.5 tok/s in all. First token: 1.3 s
  median, 72.8 s at most (three sessions came from the cache, one was filled again). All four
  requests completed with no engine error. Lowest `MemAvailable`: spark1 5.08 GiB, spark2 6.91,
  spark3 6.40.
- **KV pool against the head's `MemAvailable`**, every pool measured so far (the first three rows
  from the tuning window's 18-session row, the last from this trial; one run a row):

  | KV pool a rank | Context and budget | Tokens kept | spark1 lowest `MemAvailable` in the row |
  |---|---|---|---|
  | 2.2 GiB | 262,144, budget 4,096 | about 1.39M (8 of 18 sessions) | not read during the row |
  | 2.7 GiB | 1,048,576, budget 6,144 | about 1.74M (10 of 18) | 5.56 GiB; 4.89 GiB under 8 x 500K |
  | 3.2 GiB | 1,048,576, budget 6,144 | about 2.16M (11 of 18) | 4.80 GiB |
  | 3.5 GiB | 1,048,576, budget 6,144 | about 2.4M (an estimate; not measured) | 6.13 GiB at the start; 5.08 GiB under 4 x 500K; 4.16 GiB on client traffic to 18:23Z |

  No revisit row ran at 3.5 GiB, so the last row does not compare directly with the rows above.
- **Counters from the engine start (15:42Z) to 16:25Z.** 491 requests: 63 at the cutover (the
  probe and 11 API checks), about 186 requests of the effort tests (2026-11-22 19:17Z entry) and
  about 240 client requests. 482 ended on `stop` and 9 on `length` (8 of the 9 from the probe). 87%
  of the 26.8M prompt tokens came from the prefix cache, about 96% without the cutover requests.
  Mean time to first token 1.63 s, mean end to end 15.9 s, mean queue 0.05 s. Decode was about 90%
  of the mean request time, about 95% without the cutover requests. Requests running: 3.6 on
  average and 5 at most; no request waited. KV pool use 15% at most. Drafter acceptance 67%.
- **Half-hour periods from 16:25Z** (the requests of the effort and sampling tests, 16:05Z to
  18:07Z, and of the task battery slice from 18:16Z are in the counts):

  | Period (UTC) | Requests | From the cache | Mean TTFT | Mean end to end | Running mean / max | KV use max | spark1 lowest `MemAvailable` |
  |---|---|---|---|---|---|---|---|
  | 16:25 to 16:51 | 195 | 98% | 0.91 s | 27.5 s | 3.6 / 7 | 13% | 4.73 GiB |
  | 16:51 to 17:21 | 543 | 97% | 0.67 s | 20.9 s | 6.4 / 8 | 24% | 4.16 GiB |
  | 17:22 to 17:53 | 292 | 98% | 0.96 s | 41.4 s | 6.5 / 8 | 23% | 4.31 GiB |
  | 17:53 to 18:23 | 225 | 99% | 0.81 s | 30.0 s | 3.5 / 5 | 18% | 4.28 GiB |

  No request waited, and no period had an error, an abort or a stop for repetition. Drafter
  acceptance stayed at 67% to 70%.
- **Head memory.** Ten-minute means of `MemAvailable` on spark1 fell from 5.42 GiB (16:00Z to
  16:10Z) to 5.07 GiB (17:00Z to 17:10Z), with dips to 4.16 GiB (4,259 MiB at 17:21Z, the lowest
  one-minute sample to 18:23Z). The on-host samplers of spark2 and spark3 read 6.43 and 6.26 GiB
  at the lowest to 17:22Z. From 17:20Z to 18:20Z the head's means held at 4.91 to 5.06 GiB. The
  API server process grew from 1,431 MiB (15:55Z) to 1,630 MiB (17:22Z) and to 1,699 MiB (18:00Z).
  The engine core and the rank-0 worker stayed flat; the page cache and the kernel's memory, sampled
  from 17:23Z, stayed flat from then on. The cause of the API server's growth was not isolated. The
  process decodes images and tokenizes prompts. The head's memory is sampled every minute while the
  trial runs.
- **Later readings, to 2026-11-23T00:04Z.** The API server grew on in steps, to 1,773 MiB at 20:19Z
  and 1,826 MiB at 23:53Z. The head's lowest one-minute sample from 15:59Z was 4,253 MiB (4.15 GiB)
  at 22:31Z, 1.15 GiB above the steady guard. The median of the 480 samples was 4.97 GiB.

### 2026-11-22 06:47Z to 09:17Z: bench and task battery at `high`

- **Bench** (06:47Z, `tp3-triangle-4k` with no arm, before the battery). The recipe's bench
  marked 4 of 8 decode rows slower than the reference record, by 3.1% to 4.0%, and exited 1. All 8
  rows read 0.9% to 4.3% under. Quality 5 of 5. The head's lowest `MemAvailable` in the bench was
  7.65 GiB.
- **Run.** A battery of multi-turn tasks with tools in a sandbox, graded by program, in six
  families (A to F; the battery is not published). Each item ran twice, with a seed a run, on
  `tp3-4k-b6144-m1m` (KV pool 2.2 GiB) with 8 streams at a time and no other traffic. Settings:
  thinking on, `reasoning_effort` `high`, `max_tokens` 32,000. 35 of 46 runs finished before the
  window ended.
- **Figures.** Passed, with every stop counted as a failure: family A 7 of 11 (4 ended at the
  battery's 60-minute wall), B 10 of 10, C 2 of 4, D 1 of 1, E 3 of 5, F 2 of 3; 25 of 34 in all.
  One more family A run ended at the client's 900 s HTTP timeout. No reply hit the 32,000-token cap.
  Median reasoning tokens a run (for an even count, the mean of the two middle runs): A 49,120 (12
  runs), C 34,428, B 7,325, F 7,537, D 4,035, E 2,065. The family A median is a floor: the run
  that hit the HTTP timeout holds a partial count of 47,156, one of the two middle values. The
  median wall time of a family A run is 3,114 s, the mean of two finished runs of 2,775 and
  3,452 s. The 5 runs that ended on the 60-minute wall or the HTTP timeout are the 5 longest, so
  the wall median holds.
- **Result.** The battery's wall limit ended family A runs that were still calling tools.

### 2026-11-22 02:53Z to 06:20Z: tuning window

Each setting ran after one restart, and every figure of this entry comes from this window. A prefill
row sends a cold request to an idle engine twice a size and reports the slower run. At 131K and
250K, the two runs of a row agreed to 1% or 2%. At 14K the two runs at the base values read 2.38
and 2.99 s, so the 14K figures are not compared. The same shape read 7% to 9% apart between two
windows at 131K and 250K (22.2 s and 20.2 s for a cold 131K prefill), so only figures of the same
window are compared.

| Setting (base value) | Result | Verdict |
|---|---|---|
| Prefill budget 6,144 and long-prefill threshold 6,096 (4,096 and 4,048) | cold prefill 131K 18.2 s against 20.2 s, 250K 34.5 s against 39.3 s; decode, warm turn and depth unchanged; a stream beside a 131K fill 8.6 tok/s for the 22.0 s of the fill; head memory 0.5 GiB lower, over different loads (seven measurements at 6,144 against a six-session revisit at the base values) | adopted |
| Context 393,216 (262,144) | start 200 s; a 380,583-token prompt in 53.3 s, the planted code found; head lowest 6.26 GiB | ran once |
| Context 524,288 | start 200 s; a 499,495-token prompt in 69.8 s, code found; head lowest 6.14 GiB | ran once |
| Context 1,048,576 | start 201 s; a 960,824-token prompt in 140.4 s (6,843 tok/s), code found; head lowest 6.15 GiB | adopted |
| Long-prefill threshold 2,000 (4,048) | cold prefill 131K 28.1 s against 20.2 s; a stream beside a fill ran faster during the fill (14.9 to 16.3 tok/s against 11.0), but the fill took 37.8 s against 25.7 s, so the stream lost more time to the fill: about 29 s against 21 s | rejected |
| Retention 2,048 (512) | 9 of 18 long sessions kept (1.61M tokens) against 8 (1.39M); warm turn on 131K sessions 0.78 s against 0.57 s | not adopted |
| KV pool 2.7 GiB (2.2 GiB) | 10 of 18 sessions kept (1.74M tokens); head lowest 5.56 GiB | an option |
| KV pool 3.2 GiB | 11 of 18 sessions kept (2.16M tokens); head lowest 4.80 GiB | an option |

Each context ran one start, one long prompt, a 131K prefill, a decode measurement and, at 524,288
and 1,048,576, a warm turn. The budget, the threshold and the context of the adopted rows are the
values of the parent shape `tp3-triangle`. The 1,048,576-token context and every KV pool above
2.2 GiB are outside what the recipe qualifies for `tp3-triangle-4k` (262,144 tokens, 2.2 GiB).

The arm `tp3-4k-b6144-m1m` with the 2.2 GiB pool then read:

| Row | Figure |
|---|---|
| Cold prefill 14K, 131K, 250K | 2.19 s, 17.8 s, 34.1 s |
| One stream at 200K depth, thinking on | 89.9 tok/s |
| Decode at 2, 4 and 8 streams on 30K contexts, thinking on | 103.3, 146.5 and 193.7 tok/s in all |
| First token at 8 streams, median | 1.52 s |
| Warm turn on a cached 200K context, time to first token | 0.55 s |
| One stream beside a 131K fill, thinking off | 9.9 tok/s for the 21.9 s of the fill |
| Codes planted in the cold prefill texts | 6 of 6 found |
| Tool scenarios (six, temperature 0) | 5 of 6 (one extra read-only call) |

- **Long-context coding.** 17 of 17 program-graded tickets passed, thinking on, one run a ticket.
  Tokens in context on every turn: about 132K for 10 tickets, 391K for 2, 652K for 2 and 836K for
  3. The first ticket of each context size warmed the cache in 17.7, 53.4, 91.7 and
  120.5 s. A later ticket of the same size found the context in the cache and started in about half
  a second. The head's lowest `MemAvailable` over the tickets was 5.85 GiB.
- **Session capacity.** A row filled 18 long sessions (3.28M tokens, each with a prefix of the
  session's own), then revisited the sessions newest first until two in a row missed. A kept
  session answered in 0.4 to 0.6 s; a lost session took 11 to 38 s to fill again. On
  `tp3-4k-b6144-m1m` the head's lowest `MemAvailable` during a start was 7.12, 6.56 and 5.56 GiB at
  pools of 2.2, 2.7 and 3.2 GiB (one start a pool).
- **Depth** (2.7 GiB pool). Eight streams on long contexts (1.15M tokens together, six of the
  streams at 131K to 250K) decoded at 187.9 tok/s, about 2% under the 192.1 tok/s on 30K contexts
  (one run each).
- **Overload** (2.7 GiB pool). Eight streams at once, each on a 499.5K-token context of the
  stream's own: 4M tokens asked of the pool. All eight requests completed, and the engine logged no
  error. The engine filled one prompt at a time (2 running and 6 waiting at most). First tokens
  came after 2.4 s (the one context still cached), then 83, 164, 242, 321, 403, 483 and 562 s. A
  stream that decoded beside a fill ran at 10 to 13 tok/s. The head's lowest `MemAvailable` was
  4.89 GiB.
- **Starts.** Eight restarts took 154 to 201 s each to a ready API. None failed, and no memory
  guard acted.
- **Bench** (03:23Z, `tp3-triangle-4k` with no arm). The recipe's bench marked 4 of 8 decode rows
  slower than the reference record, by 4.1% to 6.3%, and exited 1. All 8 rows read 1.0% to 6.3%
  under. Quality 5 of 5. The head's lowest `MemAvailable` in the bench was 7.11 GiB.
- **Change.** `tp3-4k-b6144-m1m` became the arm for further work.

### 2026-11-21 23:38Z to 2026-11-22 01:04Z: first window at 262,144 tokens

- **Run.** The shape `tp3-triangle-4k` as released: context 262,144, 8 sequences, KV pool 2.2 GiB,
  built from source and started on the three nodes. Display carve-out weights stayed off, with no
  GID pin. No reboot, and no package, kernel or driver change.
- **Figures** (cold prefill: the slower of two cold requests a size; the decode and depth streams
  with thinking on; the stream beside a fill with thinking off):

  | Row | Figure |
  |---|---|
  | Cold prefill 14K, 131K, 250K | 3.40 s, 22.17 s, 42.05 s |
  | One stream at 200K depth | 86.1 tok/s |
  | Decode at 2, 4 and 8 streams | 100.5, 136.4 and 179.2 tok/s in all; at 8, the median stream decoded at 23.6 tok/s after the stream's first token |
  | First token at 8 streams, median | 1.64 s |
  | Warm turn on a cached 200K and 30K context | 0.54 s and 0.40 s |
  | One stream beside a 131K fill | 11.0 tok/s for the 26.6 s of the fill |

  Planted codes 6 of 6. Two 128K coding tasks passed. Extraction with `json_schema` 3 of 3 valid
  at 110 tok/s. Six reasoning-replay conversations returned HTTP 200 on every turn. Tool scenarios
  5 of 6: in a synthetic transfer scenario the model called `lookup_account`, `get_balance`,
  `transfer` where the probe expected `lookup_account`, `transfer`. The final answer was correct,
  and the same call order came back at temperature 0 in a second run.
- **The recipe's bench** (00:47Z; aggregate tok/s, short contexts):

  | Streams | Prose | Code | Under the reference record, prose and code |
  |---|---|---|---|
  | 1 | 59.8 | 75.4 | 3.6% and 4.1% |
  | 2 | 105.3 | 125.5 | 6.1% and 7.3% |
  | 4 | 184.5 | 247.5 | 8.4% and 6.3% |
  | 8 | 348.5 | 355.4 | 7.2% and 3.8% |

  The bench marked 4 of the 8 rows slower (the 95% interval below the reference record): prose at
  1 and 2 streams, code at 1 and 4 streams. The bench exited 1 on the gap. The cause of the gap is
  not known (Open questions). Quality 5 of 5. No thermal slowdown and no swap growth showed, and the GPUs
  reached at most 64 °C. The head's lowest `MemAvailable` in the bench was 7.39 GiB.
- **Start and disk.** The first start took 25 minutes: 129 s for the weights (94.7 GiB a rank),
  then the Engram tables on disk, then 386 kernel compiles and a warm-up of 300 compile keys. For
  r6u, an earlier baseline, the recipe gives 180 s to ready with every JIT cache empty and 186
  TileLang compiles at TP3 (`docs/current-state.md`). This first start also wrote the Engram
  tables. Lowest `MemAvailable` with the engine up: spark1 6.5 GiB, spark2 and spark3 8.2. Disk a
  node: model 476 GiB, image 27 GB, Engram tables 66 GiB (written at the first start), JIT cache
  0.1 GiB.
- **Change.** The shape runs on this site; the tuning window followed.

## Open questions

- The gap to the bench's reference record: 0.9% to 8.4% under across the 8 decode rows of three
  runs, with 4 rows a run marked slower. The reference record names the image
  `spark-ds41f:candidate-61-r2` and shows the 64 KiB-page kernel on all three nodes; the three runs
  ran `spark-ds41f:1120` on the 4 KiB kernel. During all three runs the twelve idle services were
  on and APST ran at the kernel's timeouts; both are now set as the recipe's host baseline asks.
  Other site settings in those runs: NVMe interrupt coalescing on, display carve-out weights off,
  no GID pin and `host.fan_control` false. With that key false, the tag's bench skips the pre-cool
  and the performance fan curve (`spark_ds41f/bench.py`), and the site's bench records hold empty
  `cooling` and `fan_curve` lists. A bench run on the current host state would separate the idle
  services and APST from the rest.
- Head memory over days: the API server's growth, and the start margin for a restart after many
  days of engine uptime. Every start so far came after more than a week of host uptime. At
  2026-11-22T15:55Z, a container on each node had run for 3 weeks (spark1, spark2) and 9 days
  (spark3). Issue #1272 reports, at another site, the head's `MemAvailable` before a start falling
  with host uptime until the startup guard failed; a reboot restored the reading.
- Exposure to the Engram row-reader fault reported on 1120 in issue #1036, with a prefill budget of
  6,144 and a long-prefill threshold of 6,096: not tested.
- The largest KV pool that client traffic allows: 3.5 GiB runs; 3.7 and 4.0 GiB have not run.
- The extra read-only tool call before a write: the same call order came back in a second run at
  temperature 0. Whether a client treats the call as an error is open.
- The disk tier on hardware: the GPU copy path, token equivalence after a disk hit, restore time
  and decode beside a restore.
- 3.85 to 4.20 GiB a node that no line of `/proc/meminfo` accounts for, in one snapshot
  (15:54:59Z); the owner of that memory is not measured.
- The rebase onto upstream `main`: 86 commits past the tag at 2026-11-23T01:14Z, the newest a
  promotion of `spark-ds41f-1122`, which had no GitHub release at that time.

## Branches

| Branch | Content |
|---|---|
| `lab` | this log, [`docs/lab/`](docs/lab/), the tuning arms in [`experiments/lab/`](experiments/lab/README.md) and the notes at the top of [`README.md`](README.md); based on the tag `spark-ds41f-1120` |
| `kvtier` | prepared, not yet published: `lab` plus the disk-tier patches 0830 to 0836, the disk-tier arms, the CPU-only test tools, `docs/kv-disk-tier.md` and `docs/kv-disk-tier-test-plan.md` |
| `main` | upstream `main` as last synced, with no commits of this repository |

This repository holds no tags. The tag `spark-ds41f-1120` is upstream's
([release page](https://github.com/christopherowen/spark-ds41f/releases/tag/spark-ds41f-1120)).
