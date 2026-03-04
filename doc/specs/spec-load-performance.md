# Spec: Load Performance Optimizations

## Title

`load-performance` — Reduce `load_recording` latency by 3-4x by addressing the mcap Python iterator bottleneck and eliminating per-message Python overhead.

## Status

**Draft** — Design phase. Not yet implemented. Analysis updated 2026-03-04 with empirical profiling.

## Date

2026-03-04

---

## 1. Problem Statement

### Current Performance

Loading 4 topics (800K rows) from a 75 MB MCAP file takes **~11 seconds** on an M-series Mac, **regardless of encoding** (JSON and FlatBuffer produce identical load times).

### Profiled Breakdown (empirical, not estimated)

Tested on both `json.mcap` (75 MB, JSON-encoded) and `flatbuffers.mcap` (69 MB, FlatBuffer-encoded) — same recording, same 800K messages across 4 topics.

| Phase | JSON | FlatBuffer | Notes |
|-------|------|------------|-------|
| `mcap iter_messages()` — just iterating, empty body | **6.3s** | **6.3s** | Python MCAP framing + 800K object allocations |
| `log_time_order` sort overhead | ~0.5s | ~0.4s | Saved by passing `log_time_order=False` |
| `decoder.decode()` → Python dict | 1.7s | 1.6s | `json.loads` vs `struct.unpack` — essentially equal |
| Python `list.append()` accumulation | 0.8s | 0.9s | 800K × ~10 fields = 8M appends |
| `pd.DataFrame()` construction | 0.8s | 1.1s | Type inference on Python lists |
| **Total** | **~11s** | **~11s** | |

### The Real Bottleneck

**57% of the load time is the `mcap` Python library's `iter_messages()`** — before any decoder runs. The library:

1. Reads and decompresses zstd chunks (fast, C extension)
2. **Parses MCAP binary framing in Python** (slow — per-chunk, per-message parsing)
3. **Creates 800K Python `Message`/`Channel`/`Schema` namedtuple objects** (slow — GC pressure, allocation overhead)
4. Sorts by log_time when `log_time_order=True` (adds ~0.5s)

This cost is **encoding-agnostic**: the mcap library hands raw `bytes` to the caller. Whether those bytes are JSON or FlatBuffer doesn't matter — the 6.3s is paid before any decoding.

### Why the Original Analysis Was Wrong

The original spec attributed 4-5s to `json.loads()` and assumed binary encodings would be faster. Empirical profiling showed:
- `json.loads()` on 800K messages takes **1.7s**, not 4-5s
- FlatBuffer `struct.unpack` decode takes **1.6s** — essentially identical
- The missing 4-5s was hidden inside `mcap iter_messages()`, mis-attributed to "chunk decompression"

### Target

Reduce `load_recording` wall time to **3-4s** for 800K rows, achieving the spec target of <5s for 200 MB files.

---

## 2. Optimization Strategies

### Strategy Overview

Given that **57% of load time is the mcap Python iterator**, the optimizations are ranked by actual impact:

| # | Strategy | Target phase | Savings | Complexity |
|---|----------|-------------|---------|------------|
| 1 | **Bypass mcap Python iterator** | iter_messages (6.3s) | ~4-5s | High |
| 2 | **Direct chunk-level reading** | iter_messages (6.3s) | ~3-4s | Medium |
| 3 | **Quick wins** (sort skip, orjson, flatten skip) | decode + sort (2.2s) | ~1-1.5s | Low |
| 4 | **Columnar accumulation** (numpy/Arrow) | accumulate + DataFrame (1.6s) | ~1s | Medium |

---

## 3. Optimization 1: Bypass the mcap Python Iterator (highest impact)

### What

Replace `mcap.reader.make_reader().iter_messages()` with a lower-level approach that avoids creating 800K Python `Message`/`Schema`/`Channel` objects.

### Why

The `mcap` Python library's `iter_messages()` is implemented in pure Python. For every message it:
1. Parses the MCAP binary framing (opcodes, lengths, channel IDs)
2. Creates a `Message` namedtuple (`log_time`, `publish_time`, `sequence`, `channel_id`, `data`)
3. Looks up `Schema` and `Channel` objects
4. Yields three Python objects per message

At 800K messages, this means **2.4M Python object creations** just for iteration. The actual decompression (zstd) is fast (C extension), but the Python object allocation and framing parse dominate.

### Options

#### Option A: Use `mcap` Rust reader (`mcap-rs`) via Python bindings

The [mcap crate](https://github.com/foxglove/mcap/tree/main/rust) is the canonical high-performance MCAP reader. If Python bindings exist (or can be built via PyO3/maturin), the iterator would run at native speed.

**Status**: No official Python bindings exist as of 2026-03. Would require building a custom PyO3 wrapper.

#### Option B: Direct chunk-level reading (see Optimization 2)

Read MCAP chunks at the binary level, decompress them, and extract message payloads in batch without creating per-message Python objects.

#### Option C: Use `mcap` library's `iter_decoded_messages()` with pre-built decoder factories

The `mcap` library supports `DecoderFactory` objects that receive raw bytes and return decoded messages. For Protobuf and ROS this can skip one layer of indirection. However this still creates per-message Python objects in the iterator, so the gain is marginal (~10-15%).

### Expected Gain

**Option A**: ~5s savings (iterator drops from 6.3s to ~1s). Requires Rust build step.
**Option B**: ~3-4s savings. Pure Python, no native dependencies.

---

## 4. Optimization 2: Direct Chunk-Level Reading

### What

Read MCAP file structure at the chunk level: parse the summary/index, seek to relevant chunks, decompress them in bulk, and extract message payloads using `struct.unpack_from` on the raw decompressed buffer — without yielding per-message Python objects.

### Why

An MCAP file stores messages inside compressed chunks. The summary section at the end of the file provides a chunk index with byte offsets, topic filters, and time ranges. By reading this index first, we can:

1. Identify which chunks contain our requested topics/time range
2. Seek directly to those chunks (skip irrelevant data)
3. Decompress each chunk once (zstd, C extension, fast)
4. Walk the decompressed buffer with `struct.unpack_from`, extracting only `(channel_id, log_time, data_offset, data_length)` tuples — no Python object creation per message

### Implementation Sketch

```python
import struct, zstandard

def iter_messages_fast(file_path, channel_ids, start_ns=None, end_ns=None):
    """Yield (channel_id, log_time_ns, data_bytes) without mcap Message objects."""
    with open(file_path, 'rb') as f:
        summary = _read_summary_section(f)  # parse footer + summary

        for chunk_info in summary.chunk_indices:
            if not _chunk_overlaps(chunk_info, channel_ids, start_ns, end_ns):
                continue

            f.seek(chunk_info.offset)
            compressed = f.read(chunk_info.compressed_size)
            buf = zstandard.ZstdDecompressor().decompress(compressed)

            pos = 0
            while pos < len(buf):
                opcode = buf[pos]
                length = struct.unpack_from('<Q', buf, pos + 1)[0]
                pos += 9

                if opcode == 0x05:  # Message opcode
                    ch_id = struct.unpack_from('<H', buf, pos)[0]
                    if ch_id in channel_ids:
                        log_time = struct.unpack_from('<Q', buf, pos + 10)[0]
                        data_start = pos + 22
                        data = buf[data_start:data_start + (length - 22)]
                        yield ch_id, log_time, data

                pos += length
```

This avoids the `mcap` library's per-message object creation entirely. The critical path becomes: seek → decompress (C) → `struct.unpack_from` (fast).

### Trade-offs

| Pro | Con |
|-----|-----|
| Pure Python, no new dependencies | Must maintain MCAP binary format knowledge |
| ~3-4s savings on the dominant bottleneck | Couples to MCAP spec version (currently stable at v1) |
| Can be extended to extract fields directly from buffer | More code to maintain vs using the library |

### Expected Gain

**~3-4s** — iterator phase drops from 6.3s to ~2-3s (dominated by zstd decompression).

---

## 5. Optimization 3: Quick Wins (low complexity)

### 3a. Skip log_time_order sorting

Pass `log_time_order=False` to `iter_messages()`. Messages within a chunk are already time-ordered; cross-chunk ordering is rarely needed for per-topic loading since each topic typically lives in contiguous chunks.

**Savings: ~0.5s**

### 3b. orjson for JSON parsing

Replace `json.loads()` with `orjson.loads()` in `JsonDecoder.decode()`. [orjson](https://github.com/ijl/orjson) is 3-6x faster than stdlib for deserialization.

```python
try:
    import orjson
    _json_loads = orjson.loads
except ImportError:
    import json
    _json_loads = json.loads
```

Actual decode time for 800K JSON messages is 1.7s with stdlib. orjson should bring this to ~0.5s.

**Savings: ~1.2s** (JSON files only; no effect on FlatBuffer/Protobuf/ROS)

### 3c. Skip redundant flatten for flat schemas

After decoding the first message per topic, detect if the dict is already flat. If so, skip `flatten_dict()` for all subsequent messages.

```python
if topic not in topic_structure:
    decoded = decoder.decode(schema_data, message.data, ...)
    is_flat = all(not isinstance(v, dict) for v in decoded.values())
    topic_structure[topic] = is_flat
else:
    if topic_structure[topic]:  # flat schema
        decoded = _json_loads(message.data)  # skip flatten
    else:
        decoded = decoder.decode(schema_data, message.data, ...)
```

**Savings: ~0.3-0.5s** (depends on nesting depth; most robotics schemas are flat)

### Combined Quick Wins

**Total savings: ~1.5-2s** — brings load from ~11s to ~9s. Useful but doesn't address the 6.3s elephant.

---

## 6. Optimization 4: Columnar Accumulation (numpy + Arrow)

### What

Replace Python `list.append()` per field per message with pre-allocated numpy arrays, then register as Arrow table with DuckDB (zero-copy).

### Why

Currently: 800K messages × ~10 fields = 8M `list.append()` calls, then `pd.DataFrame()` does type inference. With numpy:
- Pre-allocate typed arrays (message count is known from MCAP summary)
- Direct indexed assignment (`arr[idx] = value`) — no reallocation, no type inference
- `pyarrow.table(numpy_arrays)` → DuckDB registration is zero-copy

### Implementation

```python
import numpy as np
import pyarrow as pa

estimated_count = channel_summary.message_count
arrays = {name: np.empty(estimated_count, dtype=np.float64) for name in field_names}
arrays["timestamp_us"] = np.empty(estimated_count, dtype=np.int64)
idx = 0

for ch_id, log_time, data in iter_messages_fast(...):
    decoded = decoder.decode(data)
    arrays["timestamp_us"][idx] = log_time // 1000
    for name in field_names:
        arrays[name][idx] = decoded.get(name, np.nan)
    idx += 1

# Trim and register (zero-copy path)
table = pa.table({k: v[:idx] for k, v in arrays.items()})
duckdb_conn.register(table_name, table)
```

### DuckDB Type Mapping

| FieldInfo type | numpy dtype | Arrow type |
|---------------|-------------|------------|
| BIGINT | `np.int64` | `pa.int64()` |
| INTEGER | `np.int32` | `pa.int32()` |
| DOUBLE | `np.float64` | `pa.float64()` |
| FLOAT | `np.float32` | `pa.float32()` |
| BOOLEAN | `np.bool_` | `pa.bool_()` |
| VARCHAR | `object` (str) | `pa.string()` |

### Expected Gain

**~1s** — accumulation + DataFrame phase drops from ~1.6s to ~0.5s.

---

## 7. Combined Impact Estimate

| Optimization | Phase targeted | Before | After | Savings |
|-------------|---------------|--------|-------|---------|
| Direct chunk reading (Opt 2) | mcap iterator | 6.3s | ~2-3s | **~3-4s** |
| Sort skip (Opt 3a) | mcap sort | 0.5s | 0s | ~0.5s |
| orjson (Opt 3b, JSON only) | decode | 1.7s | ~0.5s | ~1.2s |
| Flatten skip (Opt 3c) | decode | ~0.3s | 0s | ~0.3s |
| numpy/Arrow (Opt 4) | accumulate + DataFrame | 1.6s | ~0.5s | ~1s |
| **Total** | | **~11s** | **~3-4s** | **~7-8s** |

For FlatBuffer/Protobuf files, orjson doesn't apply — estimated total drops to ~4-5s.

---

## 8. Implementation Plan

### Phase A: Quick wins (low risk, ~2s savings)

- [ ] Pass `log_time_order=False` in `load_recording`
- [ ] Add `orjson` as optional dependency with stdlib `json` fallback
- [ ] Update `JsonDecoder` to use `orjson.loads`
- [ ] Add flat-schema detection to skip `flatten_dict()`
- [ ] Benchmark before/after on both `json.mcap` and `flatbuffers.mcap`

### Phase B: Columnar accumulation (medium risk, ~1s savings)

- [ ] Add DuckDB-type-to-numpy-dtype mapping utility
- [ ] Replace Python list accumulation with pre-allocated numpy arrays
- [ ] Register via `pyarrow.table()` → DuckDB zero-copy
- [ ] Benchmark before/after

### Phase C: Direct chunk reading (higher risk, ~3-4s savings)

- [ ] Implement MCAP summary/footer parser
- [ ] Implement chunk-level decompression and message extraction
- [ ] Validate against `mcap` library output for correctness
- [ ] Replace `iter_messages()` in `load_recording` hot path
- [ ] Benchmark before/after
- [ ] Maintain compatibility with all encodings (JSON, Protobuf, ROS1, ROS2, FlatBuffer)

### Phase D: Rust reader (optional, highest impact but most effort)

- [ ] Evaluate building PyO3 bindings for `mcap-rs`
- [ ] Provide `iter_messages()` compatible API returning `(channel_id, log_time, bytes)`
- [ ] Benchmark against pure-Python approaches

### Benchmarking

All benchmarks should be run on the same hardware with:
- `json.mcap` (75 MB, JSON-encoded, 800K messages)
- `flatbuffers.mcap` (69 MB, FlatBuffer-encoded, 800K messages)
- Measure wall time for `load_recording` with all topics
- Measure peak memory usage
- Compare against the spec target of <5s for 200 MB files

---

## 9. Risks and Trade-offs

| Concern | Mitigation |
|---------|-----------|
| Direct chunk reading couples to MCAP binary spec | MCAP v1 is stable; foxglove/mcap submodule provides reference |
| `orjson` adds a Rust-compiled dependency | Wheels for all major platforms; fallback to stdlib json |
| numpy pre-allocation overestimates memory | Use `message_count` from MCAP summary (exact); trim unused tail |
| Bypassing `mcap` library loses future bug fixes | Keep library as fallback; validate chunk reader against it |
| Arrow registration API may differ across DuckDB versions | Test against DuckDB >= 1.0; pandas path remains as fallback |

---

## 10. Non-Goals

- Building full Rust bindings for mcap-rs (future consideration, not Phase 1)
- Parallelising across topics (GIL limits benefit; revisit with free-threading Python 3.13+)
- Caching decoded data to disk (conflicts with read-only principle)
- Supporting streaming/incremental loading (future consideration)
