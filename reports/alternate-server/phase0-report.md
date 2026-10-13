# Phase 0 feasibility report

Outcome: **passed**

Reason: All 1/3/5-question calls returned valid native output

Target: alternate Linux AI server; CPU-only; not the Dell

Missing measurements are null. Synthetic mock answers are never benchmark data.

## Measured timings

| Questions | First call (ms) | Warm samples | Warm median (ms) | Warm max (ms) | p95 (ms) |
|---|---|---|---|---|---|
| 1 | 8525.591612997232 | 3 | 6744.842560001416 | 6745.87016300211 | null |
| 3 | 9472.98755600059 | 3 | 9436.532193998573 | 9485.230607999256 | null |
| 5 | 11379.508746002102 | 3 | 11307.491178005876 | 11393.591962994833 | null |

## Environment, provenance and resource measurements

```json
{
  "schema_version": 1,
  "created_at_utc": "2026-10-13T16:09:04.934652+00:00",
  "benchmark_target": "alternate Linux AI server; CPU-only; not the Dell",
  "outcome": "passed",
  "reason": "All 1/3/5-question calls returned valid native output",
  "environment": {
    "os": "Linux-7.0.0-38-generic-x86_64-with-glibc2.43",
    "windows_build": null,
    "python": "3.14.4",
    "architecture": "x86_64",
    "hardware": {
      "cpu": "12th Gen Intel(R) Core(TM) i7-12700KF",
      "manufacturer": null,
      "model": null,
      "video_controllers": null
    },
    "total_physical_bytes": 65854894080,
    "available_physical_bytes": 47998554112,
    "free_disk_bytes": 31682908160,
    "dependencies": {
      "Pillow": "12.0.0",
      "psutil": "7.1.0",
      "pytest": "8.4.2",
      "torch": "2.14.1+cpu",
      "torchvision": "0.29.1+cpu",
      "transformers": "5.19.0",
      "huggingface-hub": "2.2.0"
    },
    "accelerator_runtime_probe": "not_run; CPU benchmark; controllers are inventory only"
  },
  "model": {
    "id": "LiquidAI/d1-3B",
    "requested_revision": "051bcc464b01b9f92942b364d9586b0ef5912432",
    "resolved_revision": "051bcc464b01b9f92942b364d9586b0ef5912432",
    "cache_path": "<isolated-run>/model-cache/models--LiquidAI--d1-3B/snapshots/051bcc464b01b9f92942b364d9586b0ef5912432",
    "revision_validation": "system_one validated on recorded benchmark image; no accuracy claim",
    "dtype": "float32",
    "device": "cpu",
    "weight_blob_hashes": {
      "model.safetensors": "902525631a6779559a94422449196da2e6b811d346fe9a65c4088b7c22a38b67"
    }
  },
  "image": {
    "sha256": "d00897c187b79246860701e3b958ebbbb7d1452b83b215d3fc73fdc8df2a8cdd",
    "width": 384,
    "height": 256,
    "capture_time_semantics": "file import instant; original capture time unknown"
  },
  "model_load_ms": 1293.756057995779,
  "download_ms": 125336.23855699989,
  "peak_process_tree_rss_bytes": 19005329408,
  "minimum_available_physical_bytes": 28753559552,
  "sampling_interval_seconds": 0.1,
  "peak_process_tree_swap_bytes": 344375296,
  "swap_measurement": "Linux per-process swap when readable; unavailable on Windows",
  "memory_measurement": "sampled RSS/working set; can miss transient peaks; no pagefile guarantee",
  "operator_consent": true,
  "preflight_override": false,
  "recommendation": "CONDITIONAL GO: review measured latency and accuracy before selecting the Phase 1 engine",
  "preflight_issues": [],
  "timeout_seconds": 900.0,
  "worker_dependencies": {
    "Pillow": "12.0.0",
    "psutil": "7.1.0",
    "pytest": "8.4.2",
    "torch": "2.14.1+cpu",
    "torchvision": "0.29.1+cpu",
    "transformers": "5.19.0",
    "huggingface-hub": "2.2.0"
  },
  "redactions": [
    "Ephemeral absolute cache directory replaced with <isolated-run>; complete original retained locally"
  ],
  "runtime_verification": {
    "actual_dtype": "torch.float32",
    "actual_device": "cpu",
    "parameter_count": 3123483888,
    "floating_parameter_dtypes": [
      "torch.float32"
    ],
    "method": "Separate bounded load-only inspection after benchmark"
  },
  "phase0_review": {
    "recommendation": "GO",
    "basis": "Owner accepts this CPU feasibility result; suitable for sparse still images, not a real-time capacity claim",
    "limits": "Single synthetic image; GPU, Dell performance, production accuracy and remote transport untested"
  }
}
```

## Actual first-call native output: 1 questions

```json
{
  "answers": {
    "red_square": {
      "type": "noul",
      "noul": 0.9926723012956866
    }
  },
  "usage": {
    "input_tokens": 120,
    "output_tokens": 0
  }
}
```

## Actual first-call native output: 3 questions

```json
{
  "answers": {
    "red_square": {
      "type": "noul",
      "noul": 0.9926723151697343
    },
    "background": {
      "type": "choice",
      "choice": "white",
      "confidence": 0.9831774987029727,
      "probabilities": {
        "white": 0.9831774987029727,
        "black": 0.016822501297027323
      }
    },
    "brightness": {
      "type": "score",
      "score": 1.8361759520575593,
      "confidence": 0.8497793265509658,
      "probabilities": {
        "0": 0.013603374493406381,
        "1": 0.13661729895562782,
        "2": 0.8497793265509658
      },
      "legend": {
        "0": "Dark",
        "1": "Medium",
        "2": "Bright"
      }
    }
  },
  "usage": {
    "input_tokens": 179,
    "output_tokens": 0
  }
}
```

## Actual first-call native output: 5 questions

```json
{
  "answers": {
    "red_square": {
      "type": "noul",
      "noul": 0.9926723290437557
    },
    "background": {
      "type": "choice",
      "choice": "white",
      "confidence": 0.9831774829296644,
      "probabilities": {
        "white": 0.9831774829296644,
        "black": 0.016822517070335472
      }
    },
    "brightness": {
      "type": "score",
      "score": 1.8361754448175995,
      "confidence": 0.8497788506117108,
      "probabilities": {
        "0": 0.01360340579411133,
        "1": 0.13661774359417792,
        "2": 0.8497788506117108
      },
      "legend": {
        "0": "Dark",
        "1": "Medium",
        "2": "Bright"
      }
    },
    "blue_circle": {
      "type": "noul",
      "noul": 0.9936175240718795
    },
    "green_triangle": {
      "type": "noul",
      "noul": 0.014872595940176944
    }
  },
  "usage": {
    "input_tokens": 215,
    "output_tokens": 0
  }
}
```

The companion JSON retains every call's actual native and normalised output.
