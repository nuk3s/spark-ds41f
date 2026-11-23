# Tuning arms for tp3-triangle-4k on three nodes

Arms of the recipe's shape `tp3-triangle-4k` at the tag `spark-ds41f-1120`, for one site. The site
has three DGX Spark nodes (GB10, 128 GB of unified memory a node) on the stock 4 KiB-page kernel.
The nodes run tensor parallel 3 over a triangle of three direct RoCE cables. Each arm is an overlay
in the recipe's format (`docs/lab.md`, "Runs"). An arm extends `config/cluster.json` at the shape
and changes the value of one to four serving flags in `serve_options`. No arm needs an image build,
and each arm needs one restart:

```sh
bin/spark --cluster-config experiments/lab/tp3-4k-b6144-m1m.json cluster start --apply
```

Without `--apply`, the command prints a plan; read the `live:` and `shape:` lines first. A
`spark-ds41f` container on the nodes, running or stopped, needs `--replace`; `cluster stop` keeps
the container unless `--remove` is given. A `shape:` line that reads `CHANGES` (node count, tensor
parallel size, context or KV pool) needs `--change-shape` as well (`docs/lab.md`, the `measure`
entry).

The folder holds arms for one site, not an experiment record in the layout of
`experiments/README.md`: the measurements are in `docs/lab/findings.md`, and the raw run records
are not published.

`make_arms.py` writes the 34 files from three tables and checks that each flag appears once with a
value in the base's `serve_args`. `python3 experiments/lab/make_arms.py --check` prints the arms and
writes nothing.

## Settings

| Part of the name | Flag | Value | Base value |
|---|---|---|---|
| `r2048` | `--prefix-cache-retention-interval` | 2048 | 512 |
| `c2000` | `--long-prefill-token-threshold` | 2000 | 4048 |
| `b6144` | `--max-num-batched-tokens` and `--long-prefill-token-threshold` | 6144 and 6096 | 4096 and 4048 |
| `m393k`, `m524k`, `m786k`, `m1m` | `--max-model-len` | 393216, 524288, 786432, 1048576 | 262144 |
| `kv27`, `kv32`, `kv35`, `kv40` | `--kv-cache-memory-bytes` | 2.7, 3.2, 3.5, 4.0 GiB a rank | 2.2 GiB (2362232012) |
| `kv37` | `--kv-cache-memory-bytes` | 3.7 GiB a rank (3972844749) | 2.2 GiB |

Each mix of one retention value (none or `r2048`), one prefill value (none, `c2000` or `b6144`)
and one context value (none or one `m` value) has an arm, 29 in all (`tp3-4k-r2048-b6144-m786k`,
for example). The 5 pool arms exist only on `tp3-4k-b6144-m1m`.

## Arms that ran

Nine of the 34 arms ran on this site, in the log entries of `PROGRESS.md` named below. The other
25 have not run. Measurements: `docs/lab/findings.md`.

| Arm | Log entry | Result |
|---|---|---|
| `tp3-4k-b6144` | 2026-11-22 02:53Z | cold 131K prefill 18.2 s against 20.2 s |
| `tp3-4k-b6144-m393k`, `tp3-4k-b6144-m524k` | 2026-11-22 02:53Z | one start, one long prompt, a 131K prefill and a decode measurement each; a warm turn on `tp3-4k-b6144-m524k` |
| `tp3-4k-b6144-m1m` | 2026-11-22 02:53Z | a 960,824-token prompt in 140.4 s on the stock kernel |
| `tp3-4k-c2000` | 2026-11-22 02:53Z | cold 131K prefill 28.1 s against 20.2 s |
| `tp3-4k-r2048` | 2026-11-22 02:53Z | 9 of 18 long sessions kept against 8; warm turn on a 131K session 0.78 s against 0.57 s |
| `tp3-4k-b6144-m1m-kv27`, `tp3-4k-b6144-m1m-kv32` | 2026-11-22 02:53Z | 10 and 11 of 18 long sessions kept |
| `tp3-4k-b6144-m1m-kv35` | 2026-11-22 15:52Z | the arm of the trial on the site's client traffic |

## Site settings outside the arms

The site's `config/cluster.json` differs from the tag in four settings besides node addresses and
deployment locations. The edited file is not part of this branch.

- `shapes.tp3-triangle-4k.environment.SPARK_DS41F_DISPLAY_CARVEOUT_WEIGHTS` is `"0"`. The shape
  inherits `"1"` from `tp3-triangle`. The site sets UEFI Display Reserved Memory to 0.5 GB, the
  size of the display carve-out. Patch 0021 places the embedding and output-head tables in the
  carve-out, 842.5 MiB a rank in the patch's description (`patches/vllm/README.md`). The worker
  refuses to start when the carve-out cannot hold the tables.
- `NCCL_IB_GID_INDEX` is removed from `shapes.tp3-triangle.environment`. NCCL and sparknet 0.5.0
  then take each device's IPv4 RoCE v2 GID in the cable subnet, the method that
  `docs/switchless-topology.md` describes, and the hosts' RoCE state stays unchanged. Every
  multi-node shape of the recipe pins slot 3 at the tag, and the release benchmarks ran with the
  pin, so this setting is outside what the recipe qualifies.
- The `glp` block is removed. The GLP vector sits in a gated Hugging Face repository, and the
  site serves the model without the vector.
- `host.fan_control` is `false`. The key is absent at the tag, and the recipe's default is `true`.
