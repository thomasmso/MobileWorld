"""Aggregate BidFileRenameTask results per model across pass@k runs."""

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "traj_logs/baseline")
TASK = "BidFileRenameTask"

for model_dir in sorted(p for p in root.iterdir() if p.is_dir()):
    rows = []
    for run_dir in sorted(model_dir.glob("run_*")):
        task_dir = run_dir / TASK
        result = task_dir / "result.txt"
        if not result.exists():
            rows.append((run_dir.name, None, None, None, "not finished", None))
            continue
        text = result.read_text()
        score = float(re.search(r"score:\s*([\d.]+)", text).group(1))
        reason = re.search(r"reason:\s*(.*)", text)
        reason = reason.group(1).strip() if reason else ""
        traj = json.loads((task_dir / "traj.json").read_text())["0"]
        steps = len(traj["traj"])
        usage = traj.get("token_usage") or {}
        tokens = usage.get("total_tokens") or usage.get("prompt_tokens")
        log = next(task_dir.glob("thread_*.log")).read_text()
        stamps = re.findall(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", log, re.M)
        duration = None
        if stamps:
            from datetime import datetime

            fmt = "%Y-%m-%d %H:%M:%S"
            duration = (datetime.strptime(stamps[-1], fmt) - datetime.strptime(stamps[0], fmt)).seconds / 60
        rows.append((run_dir.name, score, steps, duration, reason, tokens))

    done = [r for r in rows if r[1] is not None]
    successes = sum(1 for r in done if r[1] >= 1.0)
    print(f"\n## {model_dir.name}")
    for name, score, steps, dur, reason, tokens in rows:
        if score is None:
            print(f"  {name}: {reason}")
            continue
        dur_s = f"{dur:.1f} min" if dur is not None else "?"
        tok_s = f", {tokens:,} tokens" if tokens else ""
        print(f"  {name}: score={score} steps={steps} time={dur_s}{tok_s} | {reason[:100]}")
    if done:
        n = len(done)
        print(
            f"  => success {successes}/{n} ({successes / n:.0%}), pass@{n}={'yes' if successes else 'no'}, "
            f"avg steps {sum(r[2] for r in done) / n:.1f}, "
            f"avg time {sum(r[3] or 0 for r in done) / n:.1f} min"
        )
