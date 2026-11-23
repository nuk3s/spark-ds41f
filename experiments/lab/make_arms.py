#!/usr/bin/env python3
"""make_arms.py [ROOT] [--check]: write the tuning arms of experiments/lab/.

Each arm is the recipe's own overlay format (scripts/recipe.py, ``overlay``): the arm extends
config/cluster.json at the shape tp3-triangle-4k and changes the value of serving flags that the
base passes once. No arm needs an image build; each arm needs one restart. ROOT is the repository
root (default: two folders above this file). --check prints the arms and writes nothing. The
script reads JSON with the standard library only and runs no code of the recipe.

Settings, against the base shape:
  r2048   --prefix-cache-retention-interval 2048 (512 in the base): more retention checkpoints
          kept in the pool, so more long sessions stay cached.
  c2000   --long-prefill-token-threshold 2000 (4,048 in the base): shorter prefill chunks beside
          decoding streams.
  b6144   --max-num-batched-tokens 6144 with the threshold 6,096 (4,096 and 4,048 in the base).
  m393k, m524k, m786k, m1m   --max-model-len 393216, 524288, 786432 or 1048576 (262,144 in the
          base).
  kv27 to kv40   --kv-cache-memory-bytes for a pool of 2.7 to 4.0 GiB a rank (2.2 GiB in the
          base), on b6144 with m1m only.
Measured results: docs/lab/findings.md.

Exit status: 0 written or checked; 1 when a flag is not in the base's serve_args once with a
value; 2 on a usage error.
"""
import itertools
import json
import os
import sys

BASE = {"config": "config/cluster.json", "shape": "tp3-triangle-4k"}
RETENTION = {"": {}, "r2048": {"--prefix-cache-retention-interval": "2048"}}
PREFILL = {"": {}, "c2000": {"--long-prefill-token-threshold": "2000"},
           "b6144": {"--max-num-batched-tokens": "6144", "--long-prefill-token-threshold": "6096"}}
CONTEXT = {"": {}, "m393k": {"--max-model-len": "393216"}, "m524k": {"--max-model-len": "524288"},
           "m786k": {"--max-model-len": "786432"}, "m1m": {"--max-model-len": "1048576"}}
NOTES = {"r2048": "prefix-cache retention every 2,048 tokens", "c2000": "prefill chunks of 2,000 tokens",
         "b6144": "prefill budget 6,144 with chunks of 6,096", "m393k": "context 393,216",
         "m524k": "context 524,288", "m786k": "context 786,432", "m1m": "context 1,048,576"}

# KV pool arms on the arm tp3-4k-b6144-m1m (budget 6,144, context 1,048,576). The values are
# bytes a rank: 2.7 GiB rounded down, 3.2 and 3.7 GiB rounded to the nearest byte, 3.5 and 4.0 GiB
# exact.
EXTRA = {
    "tp3-4k-b6144-m1m-kv27": ("b6144", "m1m", {"--kv-cache-memory-bytes": "2899102924"}, "KV pool 2.7 GiB"),
    "tp3-4k-b6144-m1m-kv32": ("b6144", "m1m", {"--kv-cache-memory-bytes": "3435973837"}, "KV pool 3.2 GiB"),
    "tp3-4k-b6144-m1m-kv35": ("b6144", "m1m", {"--kv-cache-memory-bytes": "3758096384"}, "KV pool 3.5 GiB"),
    "tp3-4k-b6144-m1m-kv37": ("b6144", "m1m", {"--kv-cache-memory-bytes": "3972844749"}, "KV pool 3.7 GiB"),
    "tp3-4k-b6144-m1m-kv40": ("b6144", "m1m", {"--kv-cache-memory-bytes": "4294967296"}, "KV pool 4.0 GiB"),
}


def arms():
    out = {}
    for name, (pre, ctx, more, note) in EXTRA.items():
        options = dict(PREFILL[pre])
        options.update(CONTEXT[ctx])
        options.update(more)
        out[name] = {"extends": dict(BASE),
                     "notes": "lab arm of tp3-triangle-4k: %s; %s; %s." % (NOTES[pre], NOTES[ctx], note),
                     "serve_options": options}
    for r, p, m in itertools.product(RETENTION, PREFILL, CONTEXT):
        parts = [x for x in (r, p, m) if x]
        if not parts:
            continue
        options = {}
        for table, key in ((RETENTION, r), (PREFILL, p), (CONTEXT, m)):
            options.update(table[key])
        out["tp3-4k-" + "-".join(parts)] = {
            "extends": dict(BASE),
            "notes": "lab arm of tp3-triangle-4k: " + "; ".join(NOTES[x] for x in parts) + ".",
            "serve_options": options,
        }
    return out


def main(argv):
    check = "--check" in argv
    args = [a for a in argv if a != "--check"]
    if len(args) > 1 or any(a.startswith("-") for a in args):
        sys.stderr.write(__doc__)
        return 2
    root = args[0] if args else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
    with open(os.path.join(root, BASE["config"]), encoding="utf-8") as f:
        serve_args = json.load(f)["serve_args"]
    made = arms()
    for name, arm in sorted(made.items()):
        for flag in arm["serve_options"]:
            i = serve_args.index(flag) if serve_args.count(flag) == 1 else -1
            if i < 0 or i + 1 == len(serve_args) or serve_args[i + 1].startswith("--"):
                sys.stderr.write("make_arms: %s sets %s, which the base's serve_args do not pass once "
                                 "with a value\n" % (name, flag))
                return 1
    if not check:
        folder = os.path.join(root, "experiments", "lab")
        os.makedirs(folder, exist_ok=True)
        for name, arm in sorted(made.items()):
            with open(os.path.join(folder, name + ".json"), "w", encoding="utf-8") as f:
                json.dump(arm, f, indent=1, sort_keys=True)
                f.write("\n")
    for name, arm in sorted(made.items()):
        print("%s %s" % (name, json.dumps(arm["serve_options"], sort_keys=True)))
    sys.stderr.write("make_arms: %d arms %s\n" % (len(made), "checked" if check else "written to experiments/lab/"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
