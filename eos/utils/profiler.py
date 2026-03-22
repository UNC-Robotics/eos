"""
Lightweight function profiler for EOS.

Activated via the ``--profile`` CLI flag.  Uses ``sys.setprofile`` to
intercept every function call/return *within the eos package* and
collects per-function statistics.

On exit, prints a console summary and writes an interactive HTML report
with clickable histograms and percentile breakdowns.
"""

import atexit
import datetime
import json
import math
import os
import sys
import threading
import time
import tracemalloc
from collections import defaultdict
from itertools import pairwise
from pathlib import Path

_EOS_PKG_DIR = str(Path(__file__).resolve().parent.parent)


class _Stats:
    __slots__ = ("count", "durations", "max_ms", "min_ms", "total_ms")

    def __init__(self) -> None:
        self.count = 0
        self.total_ms = 0.0
        self.min_ms = float("inf")
        self.max_ms = 0.0
        self.durations: list[float] = []


_stats: dict[str, _Stats] = defaultdict(_Stats)
_call_stacks: dict[int, list[tuple[str, int]]] = defaultdict(list)
_lock = threading.Lock()
_active = False

# --- Memory profiling state ---
_mem_enabled = False
_mem_filter_eos_only = True
_mem_samples: list[tuple[float, float]] = []
_mem_snapshots: list[tuple[float, dict[str, int]]] = []  # (elapsed_s, {location: size})
_mem_lock = threading.Lock()
_mem_thread: threading.Thread | None = None
_mem_stop_event = threading.Event()
_mem_start_time: float = 0.0
_mem_baseline_snapshot: tracemalloc.Snapshot | None = None
_MEM_SAMPLE_INTERVAL = 2.0
_MEM_SNAPSHOT_INTERVAL = 10.0
_TRACEMALLOC_NFRAMES = 1
_TOP_ALLOCATORS = 100
_PAGE_SIZE: int | None = None


def _get_rss_mb() -> float:
    """Return current process RSS in megabytes."""
    global _PAGE_SIZE  # noqa: PLW0603
    try:
        with Path("/proc/self/statm").open("rb") as f:
            parts = f.readline().split()
        if _PAGE_SIZE is None:
            _PAGE_SIZE = os.sysconf("SC_PAGE_SIZE")
        return int(parts[1]) * _PAGE_SIZE / (1024 * 1024)
    except (FileNotFoundError, OSError, IndexError):
        import resource  # noqa: PLC0415 (platform fallback)

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _take_tracemalloc_snapshot(elapsed: float) -> None:
    """Take a tracemalloc snapshot and store per-location sizes."""
    try:
        snap = tracemalloc.take_snapshot()
        if _mem_filter_eos_only:
            snap = snap.filter_traces([tracemalloc.Filter(True, f"{_EOS_PKG_DIR}/*")])
        stats = snap.statistics("lineno")
        sizes: dict[str, int] = {}
        for stat in stats[:_TOP_ALLOCATORS]:
            frame = stat.traceback[0]
            try:
                rel = str(Path(frame.filename).relative_to(_EOS_PKG_DIR))
            except ValueError:
                rel = frame.filename
            sizes[f"{rel}:{frame.lineno}"] = stat.size
        with _mem_lock:
            _mem_snapshots.append((round(elapsed, 1), sizes))
    except Exception:  # noqa: S110
        pass


def _mem_sampler() -> None:
    """Background thread: periodically sample RSS and take tracemalloc snapshots."""
    next_snapshot = _MEM_SNAPSHOT_INTERVAL
    while not _mem_stop_event.wait(timeout=_MEM_SAMPLE_INTERVAL):
        elapsed = time.monotonic() - _mem_start_time
        rss = _get_rss_mb()
        with _mem_lock:
            _mem_samples.append((round(elapsed, 3), round(rss, 2)))
        if elapsed >= next_snapshot:
            _take_tracemalloc_snapshot(elapsed)
            next_snapshot = elapsed + _MEM_SNAPSHOT_INTERVAL


def _hook(frame, event: str, _arg) -> None:
    filename = frame.f_code.co_filename
    if _EOS_PKG_DIR not in filename:
        return

    tid = threading.get_ident()

    if event == "call":
        _call_stacks[tid].append(
            (
                f"{filename}:{frame.f_code.co_name}",
                time.perf_counter_ns(),
            )
        )
    elif event == "return":
        stack = _call_stacks.get(tid)
        if not stack:
            return
        key, start_ns = stack.pop()
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        with _lock:
            stats = _stats[key]
            stats.count += 1
            stats.total_ms += elapsed_ms
            stats.min_ms = min(stats.min_ms, elapsed_ms)
            stats.max_ms = max(stats.max_ms, elapsed_ms)
            stats.durations.append(elapsed_ms)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start(*, memory: bool = False, memory_all: bool = False) -> None:
    """
    Start profiling. Safe to call more than once.

    Args:
        memory: Enable memory profiling (RSS sampling + tracemalloc).
        memory_all: Track all Python allocations, not just EOS code.
    """
    global _active, _mem_enabled, _mem_filter_eos_only  # noqa: PLW0603
    global _mem_thread, _mem_start_time, _mem_baseline_snapshot  # noqa: PLW0603
    if _active:
        return
    _active = True
    sys.setprofile(_hook)
    threading.setprofile(_hook)

    # Memory profiling (opt-in)
    if memory or memory_all:
        _mem_enabled = True
        _mem_filter_eos_only = not memory_all
        tracemalloc.start(_TRACEMALLOC_NFRAMES)
        _mem_baseline_snapshot = tracemalloc.take_snapshot()
        _mem_start_time = time.monotonic()
        with _mem_lock:
            _mem_samples.append((0.0, round(_get_rss_mb(), 2)))
        _mem_stop_event.clear()
        _mem_thread = threading.Thread(target=_mem_sampler, name="eos-mem-sampler", daemon=True)
        _mem_thread.start()

    atexit.register(report)


def stop() -> None:
    """Remove profile hooks."""
    global _active, _mem_thread  # noqa: PLW0603
    if not _active:
        return
    _active = False
    sys.setprofile(None)
    threading.setprofile(None)

    # Stop memory sampling (tracemalloc stays alive for report())
    if _mem_enabled:
        _mem_stop_event.set()
        if _mem_thread is not None:
            _mem_thread.join(timeout=2.0)
            _mem_thread = None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _short_name(full_path: str) -> str:
    """Convert absolute ``/path/to/eos/foo/bar.py:func`` to ``foo/bar.py:func``."""
    path_part, _, func = full_path.rpartition(":")
    try:
        rel = str(Path(path_part).relative_to(_EOS_PKG_DIR))
    except ValueError:
        rel = path_part
    return f"{rel}:{func}"


_MS_PER_S = 1000


def _fmt_duration(ms: float) -> str:
    if ms >= _MS_PER_S:
        return f"{ms / _MS_PER_S:.2f}s"
    if ms >= 1:
        return f"{ms:.2f}ms"
    return f"{ms * 1000:.1f}\u00b5s"


_KIB = 1024
_MIB = 1024 * 1024
_GIB = 1024 * 1024 * 1024


def _fmt_bytes(b: float) -> str:
    if abs(b) >= _GIB:
        return f"{b / _GIB:.2f} GB"
    if abs(b) >= _MIB:
        return f"{b / _MIB:.2f} MB"
    if abs(b) >= _KIB:
        return f"{b / _KIB:.2f} KB"
    return f"{b:.0f} B"


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------


def _percentile(sorted_data: list[float], p: float) -> float:
    n = len(sorted_data)
    if n == 0:
        return 0.0
    idx = p / 100 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


_MIN_HISTOGRAM_POINTS = 2


def _histogram(sorted_data: list[float], num_bins: int = 50) -> tuple[list[float], list[int]]:
    if len(sorted_data) < _MIN_HISTOGRAM_POINTS:
        return [sorted_data[0], sorted_data[0]], [len(sorted_data)]
    lo, hi = sorted_data[0], sorted_data[-1]
    if lo == hi:
        return [lo, hi], [len(sorted_data)]
    bin_width = (hi - lo) / num_bins
    edges = [lo + i * bin_width for i in range(num_bins + 1)]
    counts = [0] * num_bins
    for value in sorted_data:
        counts[min(int((value - lo) / bin_width), num_bins - 1)] += 1
    return edges, counts


def _build_func_data(name: str, stats: _Stats) -> dict:
    sorted_durations = sorted(stats.durations)
    n = len(sorted_durations)
    mean = stats.total_ms / stats.count if stats.count else 0
    variance = sum((d - mean) ** 2 for d in sorted_durations) / (n - 1) if n > 1 else 0

    percentiles = {}
    for p in (25, 50, 75, 90, 95, 99):
        percentiles[f"p{p}"] = _percentile(sorted_durations, p) if n else 0

    edges, hist_counts = _histogram(sorted_durations) if n else ([0, 0], [0])

    return {
        "name": name,
        "count": stats.count,
        "total_ms": round(stats.total_ms, 4),
        "mean_ms": round(mean, 4),
        "min_ms": round(stats.min_ms, 4) if stats.min_ms != float("inf") else 0,
        "max_ms": round(stats.max_ms, 4),
        "stdev_ms": round(math.sqrt(variance), 4),
        "percentiles": {k: round(v, 4) for k, v in percentiles.items()},
        "histogram": {"edges": [round(e, 4) for e in edges], "counts": hist_counts},
    }


_MIN_TREND_SAMPLES = 2
_TREND_GROWING_THRESHOLD = 0.75
_TREND_SHRINKING_THRESHOLD = 0.25


def _growth_trend(sizes: list[int]) -> str:
    """Classify allocation trend from a series of sizes."""
    if len(sizes) < _MIN_TREND_SAMPLES:
        return "unknown"
    increases = sum(1 for a, b in pairwise(sizes) if b > a)
    ratio = increases / (len(sizes) - 1)
    if ratio >= _TREND_GROWING_THRESHOLD:
        return "growing"
    if ratio <= _TREND_SHRINKING_THRESHOLD:
        return "shrinking"
    return "stable"


def _build_memory_data() -> dict:
    """Build memory profiling data for the report."""
    with _mem_lock:
        samples = list(_mem_samples)
        snapshots = list(_mem_snapshots)

    # Take one final RSS sample + snapshot
    if _mem_start_time:
        elapsed = time.monotonic() - _mem_start_time
        samples.append((round(elapsed, 3), round(_get_rss_mb(), 2)))
        _take_tracemalloc_snapshot(elapsed)
        with _mem_lock:
            snapshots = list(_mem_snapshots)

    rss_values = [s[1] for s in samples]
    start_rss = rss_values[0] if rss_values else 0
    end_rss = rss_values[-1] if rss_values else 0
    peak_rss = max(rss_values) if rss_values else 0

    # Build final allocator data from tracemalloc diff against baseline
    allocators = []
    try:
        snap = tracemalloc.take_snapshot()
        if _mem_filter_eos_only:
            snap = snap.filter_traces([tracemalloc.Filter(True, f"{_EOS_PKG_DIR}/*")])
        if _mem_baseline_snapshot is not None:
            baseline = _mem_baseline_snapshot
            if _mem_filter_eos_only:
                baseline = baseline.filter_traces([tracemalloc.Filter(True, f"{_EOS_PKG_DIR}/*")])
            diff_stats = snap.compare_to(baseline, "lineno")
        else:
            diff_stats = snap.statistics("lineno")

        for stat in diff_stats[:_TOP_ALLOCATORS]:
            frame = stat.traceback[0]
            try:
                rel_path = str(Path(frame.filename).relative_to(_EOS_PKG_DIR))
            except ValueError:
                rel_path = frame.filename
            location = f"{rel_path}:{frame.lineno}"

            # Collect per-snapshot sizes for this location to compute trend
            location_sizes = [s_sizes.get(location, 0) for _, s_sizes in snapshots]

            entry: dict = {
                "location": location,
                "size": stat.size,
                "size_str": _fmt_bytes(stat.size),
                "count": stat.count,
                "trend": _growth_trend(location_sizes) if len(snapshots) >= _MIN_TREND_SAMPLES else "unknown",
                "sizes": location_sizes,
            }
            if _mem_baseline_snapshot is not None:
                entry["size_diff"] = stat.size_diff
                entry["size_diff_str"] = ("+" if stat.size_diff >= 0 else "") + _fmt_bytes(abs(stat.size_diff))
                entry["count_diff"] = stat.count_diff
            allocators.append(entry)
    except Exception:  # noqa: S110
        pass  # tracemalloc may not be active; degrade gracefully
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    return {
        "samples": samples,
        "start_rss_mb": round(start_rss, 2),
        "end_rss_mb": round(end_rss, 2),
        "peak_rss_mb": round(peak_rss, 2),
        "growth_rss_mb": round(end_rss - start_rss, 2),
        "snapshot_times": [t for t, _ in snapshots],
        "allocators": allocators,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def report(top_n: int = 100) -> None:
    """Print console summary and write interactive HTML report."""
    global _mem_enabled  # noqa: PLW0603
    # Build memory data before stop() so tracemalloc is still active
    mem_data = _build_memory_data() if _mem_enabled else None
    stop()
    if not _stats and not (mem_data and mem_data["samples"]):
        return

    items = [(_short_name(key), stats) for key, stats in _stats.items()]
    by_total = sorted(items, key=lambda x: x[1].total_ms, reverse=True)

    # Console summary (top 10)
    print(f"\n{'=' * 90}")  # noqa: T201
    print("  EOS PROFILING REPORT  (top 10 by total time)")  # noqa: T201
    print(f"{'=' * 90}")  # noqa: T201
    print(f"  {'Function':<50} {'Calls':>8} {'Total':>10} {'Mean':>10} {'p95':>10}")  # noqa: T201
    sep = "\u2500" * 90
    print(f"  {sep}")  # noqa: T201
    for name, stats in by_total[:10]:
        sd = sorted(stats.durations)
        print(  # noqa: T201
            f"  {name:<50} {stats.count:>8,} {_fmt_duration(stats.total_ms):>10} "
            f"{_fmt_duration(stats.total_ms / stats.count):>10} {_fmt_duration(_percentile(sd, 95)):>10}"
        )
    print(f"{'=' * 90}")  # noqa: T201

    # Memory summary
    if mem_data and mem_data["samples"]:
        print(  # noqa: T201
            f"  Memory: start={mem_data['start_rss_mb']:.1f}MB "
            f"end={mem_data['end_rss_mb']:.1f}MB "
            f"peak={mem_data['peak_rss_mb']:.1f}MB "
            f"growth={mem_data['growth_rss_mb']:+.1f}MB"
        )
        print(f"{'=' * 90}")  # noqa: T201

    # Build HTML data
    all_data = {name: _build_func_data(name, stats) for name, stats in items}
    functions_data = [all_data[name] for name, _ in by_total[:top_n]]

    now = datetime.datetime.now(tz=datetime.UTC)
    data_json = json.dumps(
        {
            "functions": functions_data,
            **({"memory": mem_data} if mem_data else {}),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )

    html = _HTML_TEMPLATE.replace("/*__DATA__*/null", data_json)

    out_path = Path(f"eos_profile_{now.strftime('%Y%m%d_%H%M%S')}.html")
    out_path.write_text(html)
    print(f"\n  [Profiler] Interactive report: {out_path.resolve()}\n")  # noqa: T201

    _stats.clear()
    _call_stacks.clear()
    if _mem_enabled:
        _mem_samples.clear()
        _mem_snapshots.clear()
        _mem_enabled = False
    atexit.unregister(report)


# ---------------------------------------------------------------------------
# HTML template (self-contained report with embedded JS/CSS)
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EOS Profile Report</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0 }
body { font-family: system-ui, -apple-system, sans-serif; background: #f8f9fa; color: #212529; padding: 1.5rem 2rem }
h1 { font-size: 1.4rem; font-weight: 700 }
.ts { color: #868e96; font-size: .85rem; margin-bottom: 1.5rem }
h2 { font-size: 1.05rem; color: #495057; margin: 2rem 0 .5rem; padding-bottom: .3rem; border-bottom: 2px solid #dee2e6 }
table { width: 100%; border-collapse: collapse; font-size: .82rem; table-layout: fixed }
th { background: #e9ecef; text-align: left; padding: .45rem .5rem; font-weight: 600;
     position: sticky; top: 0; white-space: nowrap; cursor: pointer; user-select: none }
th:hover { background: #dde1e5 }
th .arrow { font-size: .7rem; margin-left: 3px; color: #868e96 }
td { padding: .35rem .5rem; border-bottom: 1px solid #eee;
     overflow: hidden; text-overflow: ellipsis; white-space: nowrap }
.r { text-align: right }
.m { font-family: 'SF Mono', 'Cascadia Code', 'Fira Code', monospace; font-size: .78rem }
.fn-col { width: 38% }
.clickable { cursor: pointer }
.clickable:hover { background: #e8f4f8 }
.detail { padding: 1rem 1.5rem; background: #fff; border: 1px solid #dee2e6;
         border-radius: 6px; margin: .25rem 0 .75rem }
.stats-row { display: flex; gap: .75rem; margin-bottom: 1rem; flex-wrap: wrap }
.stat-card { background: #f1f3f5; border-radius: 4px; padding: .4rem .7rem; text-align: center; min-width: 90px }
.stat-label { font-size: .65rem; color: #868e96; text-transform: uppercase; letter-spacing: .04em }
.stat-value { font-size: .95rem; font-weight: 600; font-family: monospace }
.detail-body { display: flex; gap: 2rem; align-items: flex-start; flex-wrap: wrap }
.pct-table { min-width: 170px }
.pct-table h4, .hist-wrap h4 { font-size: .8rem; color: #495057; margin-bottom: .4rem }
.pct-table table { width: auto; font-size: .78rem }
.pct-table td { padding: .2rem .5rem; border-bottom: 1px solid #f1f3f5 }
.pct-table tr:nth-child(even) { background: #f8f9fa }
canvas { border: 1px solid #e9ecef; border-radius: 4px; background: #fff }
.legend { display: flex; gap: 1rem; margin-top: .4rem; font-size: .7rem; color: #495057 }
.legend span::before { content: ''; display: inline-block; width: 12px;
                       height: 3px; margin-right: 4px; vertical-align: middle }
.lp50::before { background: #2b8a3e }
.lp95::before { background: #e67700 }
.lp99::before { background: #c92a2a }
.mem-summary { display: flex; gap: 1rem; margin: 1rem 0; flex-wrap: wrap }
.mem-card { background: #e3f2fd; border-radius: 6px; padding: .6rem 1rem; text-align: center; min-width: 120px }
.mem-card .stat-label { color: #5c6bc0 }
.mem-card.growth-pos { background: #fbe9e7 }
.mem-card.growth-neg { background: #e8f5e9 }
.mem-chart-wrap { margin: 1rem 0 }
.mem-chart-wrap h4, .alloc-section h4 { font-size: .85rem; color: #495057; margin-bottom: .4rem }
.alloc-section { margin-top: 1.5rem }
.alloc-section td.gp { color: #c62828 }
.alloc-section td.gn { color: #2e7d32 }
.show-ctl { display: inline-block; margin-left: .75rem; font-size: .78rem; font-weight: 400; color: #495057 }
.show-ctl select { font-size: .78rem; padding: .1rem .3rem; border: 1px solid #ced4da; border-radius: 3px }
</style>
</head>
<body>
<h1>EOS Profiling Report</h1>
<div class="ts" id="ts"></div>
<div id="mem-section" style="display:none">
  <h2>Memory</h2>
  <div id="mem-summary" class="mem-summary"></div>
  <div class="mem-chart-wrap">
    <h4>RSS Over Time</h4>
    <canvas id="mem-chart" width="900" height="300"></canvas>
  </div>
  <div class="alloc-section">
    <h4>Top Memory Allocators
      <span id="alloc-sort-label" style="font-weight:400;font-size:.8rem;color:#868e96"></span>
      <span class="show-ctl">Show
        <select id="alloc-limit" onchange="renderAllocators()">
          <option value="10">10</option><option value="25">25</option>
          <option value="50">50</option><option value="100" selected>100</option>
          <option value="0">All</option>
        </select>
      </span>
    </h4>
    <div id="alloc-tbl"></div>
  </div>
</div>
<h2>Top Functions
  <span id="sort-label" style="font-weight:400;font-size:.85rem;color:#868e96">(sorted by Total desc)</span>
  <span class="show-ctl">Show
    <select id="fn-limit" onchange="render()">
      <option value="10">10</option><option value="25">25</option>
      <option value="50">50</option><option value="100" selected>100</option>
      <option value="0">All</option>
    </select>
  </span>
</h2>
<div id="tbl"></div>
<script>
const D = /*__DATA__*/null;
document.getElementById('ts').textContent = D.timestamp;

function fmt(ms) {
  if (ms >= 1000) return (ms / 1000).toFixed(2) + 's';
  if (ms >= 1) return ms.toFixed(2) + 'ms';
  return (ms * 1000).toFixed(1) + '\\u00b5s';
}

function statCard(label, value) {
  return '<div class="stat-card"><div class="stat-label">' + label +
         '</div><div class="stat-value">' + value + '</div></div>';
}

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/'/g, "\\\\'");
}

const COLS = [
  ['Calls',  'count',           f => f.count.toLocaleString()],
  ['Total',  'total_ms',        f => fmt(f.total_ms)],
  ['Mean',   'mean_ms',         f => fmt(f.mean_ms)],
  ['Min',    'min_ms',          f => fmt(f.min_ms)],
  ['Max',    'max_ms',          f => fmt(f.max_ms)],
  ['p50',    'percentiles.p50', f => fmt(f.percentiles.p50)],
  ['p95',    'percentiles.p95', f => fmt(f.percentiles.p95)],
  ['p99',    'percentiles.p99', f => fmt(f.percentiles.p99)],
];

function getVal(obj, dottedKey) {
  let v = obj;
  for (const k of dottedKey.split('.')) v = v[k];
  return v;
}

let curSort = { key: 'total_ms', desc: true };
const openSet = new Set();

function sortData(data) {
  return [...data].sort((a, b) => {
    const va = getVal(a, curSort.key), vb = getVal(b, curSort.key);
    if (typeof va === 'string') return curSort.desc ? vb.localeCompare(va) : va.localeCompare(vb);
    return curSort.desc ? vb - va : va - vb;
  });
}

function arrow(key) {
  if (curSort.key !== key) return '<span class="arrow"></span>';
  return '<span class="arrow">' + (curSort.desc ? '\\u25bc' : '\\u25b2') + '</span>';
}

function onSort(key) {
  if (curSort.key === key) curSort.desc = !curSort.desc;
  else { curSort.key = key; curSort.desc = true; }
  render();
}

function render() {
  var limit = parseInt(document.getElementById('fn-limit').value) || 0;
  const all = sortData(D.functions);
  const sorted = limit > 0 ? all.slice(0, limit) : all;
  let h = '<table><thead><tr>';
  h += '<th class="fn-col" onclick="onSort(\\'name\\')">Function' + arrow('name') + '</th>';
  COLS.forEach(([label, key]) => {
    h += '<th class="r" onclick="onSort(\\'' + key + '\\')">' + label + arrow(key) + '</th>';
  });
  h += '</tr></thead><tbody>';

  sorted.forEach((f, i) => {
    const rid = 'r-' + i;
    const nameEsc = esc(f.name);
    h += '<tr class="clickable" onclick="toggle(\\'' + rid + "','" + nameEsc + '\\')">'
       + '<td class="m" title="' + nameEsc + '">' + nameEsc + '</td>';
    COLS.forEach(([,, fmtFn]) => { h += '<td class="r m">' + fmtFn(f) + '</td>'; });
    h += '</tr>';

    const isOpen = openSet.has(f.name);
    h += '<tr id="' + rid + '" style="display:' + (isOpen ? '' : 'none') + '">'
       + '<td colspan="9"><div class="detail"><div class="stats-row">';
    h += statCard('Count', f.count.toLocaleString());
    h += statCard('Total', fmt(f.total_ms));
    h += statCard('Mean', fmt(f.mean_ms));
    h += statCard('Stdev', fmt(f.stdev_ms));
    h += statCard('Min', fmt(f.min_ms));
    h += statCard('Max', fmt(f.max_ms));
    h += '</div><div class="detail-body">';

    h += '<div class="pct-table"><h4>Percentiles</h4><table>';
    for (const [k, v] of Object.entries(f.percentiles)) {
      h += '<tr><td><b>' + k + '</b></td><td class="m">' + fmt(v) + '</td></tr>';
    }
    h += '</table></div>';

    h += '<div class="hist-wrap"><h4>Duration Distribution</h4>'
       + '<canvas id="cv-' + rid + '" width="640" height="260"></canvas>'
       + '<div class="legend"><span class="lp50">p50</span>'
       + '<span class="lp95">p95</span><span class="lp99">p99</span></div>'
       + '</div></div></div></td></tr>';
  });

  h += '</tbody></table>';
  document.getElementById('tbl').innerHTML = h;

  sorted.forEach((f, i) => {
    if (openSet.has(f.name)) {
      const cv = document.getElementById('cv-r-' + i);
      if (cv) drawHist(cv, f);
    }
  });

  const col = COLS.find(([, k]) => k === curSort.key);
  const label = curSort.key === 'name' ? 'Function' : (col ? col[0] : curSort.key);
  document.getElementById('sort-label').textContent =
    '(sorted by ' + label + (curSort.desc ? ' desc' : ' asc') + ')';
}

function toggle(rid, fname) {
  const row = document.getElementById(rid);
  if (row.style.display === 'none') {
    row.style.display = '';
    openSet.add(fname);
    const cv = document.getElementById('cv-' + rid);
    if (cv && !cv.dataset.drawn) {
      const f = D.functions.find(x => x.name === fname);
      if (f) drawHist(cv, f);
      cv.dataset.drawn = '1';
    }
  } else {
    row.style.display = 'none';
    openSet.delete(fname);
  }
}

const PLINES = [
  { key: 'p50', color: '#2b8a3e' },
  { key: 'p95', color: '#e67700' },
  { key: 'p99', color: '#c92a2a' },
];

function drawHist(canvas, f) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height;
  const pad = { t: 22, r: 14, b: 32, l: 14 };
  const plotW = W - pad.l - pad.r, plotH = H - pad.t - pad.b;
  const { edges, counts } = f.histogram;
  const maxCount = Math.max(...counts);
  const numBins = counts.length;
  const binW = plotW / numBins;

  ctx.clearRect(0, 0, W, H);

  for (let i = 0; i < numBins; i++) {
    const barH = maxCount > 0 ? (counts[i] / maxCount) * plotH : 0;
    const x = pad.l + i * binW;
    ctx.fillStyle = counts[i] > 0 ? '#74c0fc' : '#f1f3f5';
    ctx.fillRect(x, pad.t + plotH - barH, Math.max(binW - 1, 1), barH);
  }

  const lo = edges[0], hi = edges[edges.length - 1], range = hi - lo;
  if (range > 0) {
    PLINES.forEach(({ key, color }) => {
      const v = f.percentiles[key];
      const x = pad.l + ((v - lo) / range) * plotW;
      ctx.save();
      ctx.strokeStyle = color; ctx.lineWidth = 1.5; ctx.setLineDash([4, 3]);
      ctx.beginPath(); ctx.moveTo(x, pad.t); ctx.lineTo(x, pad.t + plotH); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color; ctx.font = '11px system-ui'; ctx.textAlign = 'center';
      ctx.fillText(fmt(v), x, pad.t - 5);
      ctx.restore();
    });
  }

  ctx.strokeStyle = '#ced4da'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + plotH);
  ctx.lineTo(pad.l + plotW, pad.t + plotH); ctx.stroke();

  ctx.fillStyle = '#868e96'; ctx.font = '11px system-ui';
  ctx.textAlign = 'left';   ctx.fillText(fmt(lo), pad.l, H - 8);
  ctx.textAlign = 'right';  ctx.fillText(fmt(hi), W - pad.r, H - 8);
  ctx.textAlign = 'center'; ctx.fillText('duration', W / 2, H - 8);
}

// --- Memory profiling ---

function fmtMB(mb) {
  if (mb >= 1024) return (mb / 1024).toFixed(2) + ' GB';
  if (mb >= 1) return mb.toFixed(1) + ' MB';
  return (mb * 1024).toFixed(0) + ' KB';
}

function fmtBytes(b) {
  var a = Math.abs(b);
  if (a >= 1073741824) return (b / 1073741824).toFixed(2) + ' GB';
  if (a >= 1048576) return (b / 1048576).toFixed(2) + ' MB';
  if (a >= 1024) return (b / 1024).toFixed(1) + ' KB';
  return b + ' B';
}

function memCard(label, value, cls) {
  return '<div class="mem-card' + (cls ? ' ' + cls : '') + '"><div class="stat-label">' + label +
         '</div><div class="stat-value">' + value + '</div></div>';
}

function renderMemory() {
  var mem = D.memory;
  if (!mem || !mem.samples || mem.samples.length === 0) return;
  document.getElementById('mem-section').style.display = '';

  var gc = mem.growth_rss_mb >= 0 ? 'growth-pos' : 'growth-neg';
  var gs = (mem.growth_rss_mb >= 0 ? '+' : '') + fmtMB(mem.growth_rss_mb);
  var dur = mem.samples.length > 1 ? mem.samples[mem.samples.length - 1][0] : 0;
  var durStr = dur >= 60 ? (dur / 60).toFixed(1) + 'm' : dur.toFixed(0) + 's';
  var h = memCard('Start RSS', fmtMB(mem.start_rss_mb))
        + memCard('End RSS', fmtMB(mem.end_rss_mb))
        + memCard('Peak RSS', fmtMB(mem.peak_rss_mb))
        + memCard('Growth', gs, gc)
        + memCard('Duration', durStr);
  document.getElementById('mem-summary').innerHTML = h;

  drawMemChart();
  renderAllocators();
}

function drawMemChart() {
  var mem = D.memory, samples = mem.samples;
  var canvas = document.getElementById('mem-chart');
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var pad = { t: 30, r: 60, b: 40, l: 65 };
  var pW = W - pad.l - pad.r, pH = H - pad.t - pad.b;

  if (samples.length < 2) return;

  var times = samples.map(function(s) { return s[0]; });
  var vals = samples.map(function(s) { return s[1]; });
  var minT = times[0], maxT = times[times.length - 1];
  var minV = Math.min.apply(null, vals) * 0.95;
  var maxV = Math.max.apply(null, vals) * 1.05;
  var rT = maxT - minT || 1, rV = maxV - minV || 1;

  ctx.clearRect(0, 0, W, H);

  // Horizontal grid
  ctx.strokeStyle = '#e9ecef'; ctx.lineWidth = 1;
  for (var g = 0; g <= 5; g++) {
    var gy = pad.t + (g / 5) * pH;
    ctx.beginPath(); ctx.moveTo(pad.l, gy); ctx.lineTo(pad.l + pW, gy); ctx.stroke();
    ctx.fillStyle = '#868e96'; ctx.font = '11px system-ui'; ctx.textAlign = 'right';
    ctx.fillText(fmtMB(maxV - (g / 5) * rV), pad.l - 8, gy + 4);
  }

  // Area fill
  ctx.beginPath();
  ctx.moveTo(pad.l, pad.t + pH);
  for (var i = 0; i < samples.length; i++) {
    var x = pad.l + ((times[i] - minT) / rT) * pW;
    var y = pad.t + ((maxV - vals[i]) / rV) * pH;
    ctx.lineTo(x, y);
  }
  ctx.lineTo(pad.l + ((times[times.length - 1] - minT) / rT) * pW, pad.t + pH);
  ctx.closePath();
  ctx.fillStyle = 'rgba(66, 133, 244, 0.12)';
  ctx.fill();

  // Line
  ctx.beginPath();
  for (var i = 0; i < samples.length; i++) {
    var x = pad.l + ((times[i] - minT) / rT) * pW;
    var y = pad.t + ((maxV - vals[i]) / rV) * pH;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  }
  ctx.strokeStyle = '#4285f4'; ctx.lineWidth = 2; ctx.stroke();

  // Peak marker
  var peakVal = Math.max.apply(null, vals);
  var peakIdx = vals.indexOf(peakVal);
  var px = pad.l + ((times[peakIdx] - minT) / rT) * pW;
  var py = pad.t + ((maxV - vals[peakIdx]) / rV) * pH;
  ctx.fillStyle = '#c92a2a';
  ctx.beginPath(); ctx.arc(px, py, 4, 0, 2 * Math.PI); ctx.fill();
  ctx.font = '11px system-ui'; ctx.textAlign = 'center';
  ctx.fillText('peak ' + fmtMB(vals[peakIdx]), px, py - 10);

  // Axes
  ctx.strokeStyle = '#ced4da'; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(pad.l, pad.t); ctx.lineTo(pad.l, pad.t + pH);
  ctx.lineTo(pad.l + pW, pad.t + pH); ctx.stroke();

  // X-axis labels
  ctx.fillStyle = '#868e96'; ctx.font = '11px system-ui';
  var nXL = Math.min(6, samples.length - 1);
  for (var j = 0; j <= nXL; j++) {
    var t = minT + (j / nXL) * rT;
    var lx = pad.l + (j / nXL) * pW;
    ctx.textAlign = 'center';
    ctx.fillText(t >= 60 ? (t / 60).toFixed(1) + 'm' : t.toFixed(0) + 's', lx, H - pad.b + 20);
  }
  ctx.textAlign = 'center';
  ctx.fillText('elapsed time', pad.l + pW / 2, H - 5);

  // Y-axis label
  ctx.save();
  ctx.translate(12, pad.t + pH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.textAlign = 'center';
  ctx.fillText('RSS', 0, 0);
  ctx.restore();
}

var allocSort = { key: 'size', desc: true };

function allocArrow(key) {
  if (allocSort.key !== key) return '<span class="arrow"></span>';
  return '<span class="arrow">' + (allocSort.desc ? '\\u25bc' : '\\u25b2') + '</span>';
}

function allocSortBy(key) {
  if (allocSort.key === key) allocSort.desc = !allocSort.desc;
  else { allocSort.key = key; allocSort.desc = true; }
  renderAllocators();
}

function sparkline(sizes) {
  if (!sizes || sizes.length < 2) return '';
  var max = Math.max.apply(null, sizes);
  if (max === 0) return '';
  var w = 60, h = 16, n = sizes.length;
  var pts = [];
  for (var i = 0; i < n; i++) {
    pts.push((i / (n - 1) * w).toFixed(1) + ',' + (h - sizes[i] / max * h).toFixed(1));
  }
  return '<svg width="' + w + '" height="' + h + '" style="vertical-align:middle">' +
    '<polyline points="' + pts.join(' ') + '" fill="none" stroke="#4285f4" stroke-width="1.5"/></svg>';
}

function trendBadge(trend) {
  if (trend === 'growing')
    return '<span class="gp" style="font-weight:600"'
      + ' title="Growing across most snapshots">\\u25b2 growing</span>';
  if (trend === 'shrinking')
    return '<span class="gn"'
      + ' title="Shrinking">\\u25bc shrinking</span>';
  if (trend === 'stable')
    return '<span style="color:#868e96"'
      + ' title="Stable">\\u2500 stable</span>';
  return '<span style="color:#868e96">\\u2014</span>';
}

function renderAllocators() {
  var mem = D.memory;
  if (!mem.allocators || mem.allocators.length === 0) {
    document.getElementById('alloc-tbl').innerHTML =
      '<p style="color:#868e96;font-size:.82rem">No allocations tracked by tracemalloc.</p>';
    return;
  }

  var allocLimit = parseInt(document.getElementById('alloc-limit').value) || 0;
  var hasDiff = mem.allocators[0].size_diff !== undefined;
  var hasTrend = mem.allocators[0].trend !== undefined && mem.allocators[0].trend !== 'unknown';
  var allSorted = mem.allocators.slice().sort(function(a, b) {
    var va = a[allocSort.key], vb = b[allocSort.key];
    if (typeof va === 'string') return allocSort.desc ? vb.localeCompare(va) : va.localeCompare(vb);
    return allocSort.desc ? vb - va : va - vb;
  });
  var sorted = allocLimit > 0 ? allSorted.slice(0, allocLimit) : allSorted;

  var h = '<table><thead><tr>';
  h += '<th class="fn-col" onclick="allocSortBy(\\'location\\')">Location' + allocArrow('location') + '</th>';
  h += '<th class="r" onclick="allocSortBy(\\'size\\')">Current Size' + allocArrow('size') + '</th>';
  h += '<th class="r" onclick="allocSortBy(\\'count\\')">Alloc Count' + allocArrow('count') + '</th>';
  if (hasDiff) {
    h += '<th class="r" onclick="allocSortBy(\\'size_diff\\')">Growth' + allocArrow('size_diff') + '</th>';
    h += '<th class="r" onclick="allocSortBy(\\'count_diff\\')">Count \\u0394' + allocArrow('count_diff') + '</th>';
  }
  if (hasTrend) {
    h += '<th onclick="allocSortBy(\\'trend\\')">Trend' + allocArrow('trend') + '</th>';
    h += '<th>History</th>';
  }
  h += '</tr></thead><tbody>';

  sorted.forEach(function(a) {
    h += '<tr><td class="m" title="' + esc(a.location) + '">' + esc(a.location) + '</td>';
    h += '<td class="r m">' + a.size_str + '</td>';
    h += '<td class="r m">' + a.count.toLocaleString() + '</td>';
    if (hasDiff) {
      var cls = a.size_diff > 0 ? 'gp' : (a.size_diff < 0 ? 'gn' : '');
      h += '<td class="r m ' + cls + '">' + a.size_diff_str + '</td>';
      h += '<td class="r m">' + (a.count_diff >= 0 ? '+' : '') + a.count_diff.toLocaleString() + '</td>';
    }
    if (hasTrend) {
      h += '<td>' + trendBadge(a.trend) + '</td>';
      h += '<td>' + sparkline(a.sizes) + '</td>';
    }
    h += '</tr>';
  });

  h += '</tbody></table>';
  document.getElementById('alloc-tbl').innerHTML = h;
}

render();
if (D.memory) renderMemory();
</script>
</body>
</html>
"""
