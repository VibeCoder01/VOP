# ADR-0003 — Phase 0 foundation verified; real-engine selection requires evidence

Date: 13 October 2026. Status: proposed for Phase 0 review.

The offline byte-oriented inference foundation and synthetic CLI work on Windows 11 Pro
build 26300 / Python 3.11.9 on the Dell Latitude 5510, i5-10310U, approximately 16 GiB installed
RAM. The same 78 tests pass on an independently provisioned Linux x86_64 host with Python
3.14.4 / i7-12700KF / approximately 61 GiB RAM. Two mock instances use identical contracts,
with no shared paths or device-specific caller code. This verifies software, not visual accuracy.

The official d1-3B API/source was inspected at SHA
`051bcc464b01b9f92942b364d9586b0ef5912432`. The optional adapter loads only that snapshot
using the documented FP32 CPU API; no model format or provider substitution occurs.
The Dell report is `not_run`: approximately 5.4 GiB available RAM and 14.5 GiB disk triggered
conservative preflight warnings, and laptop inference was not explicitly authorised.
Dell model load success, peak inference memory, latency and throughput remain unknown.

The product owner subsequently authorised an alternate server benchmark. This is the same
standalone CLI on a separate machine, not a remote worker service or new network protocol.
Its outcome and measurements are recorded separately in the alternate-server report.
GPU presence is not a claimed Vulkan/CUDA benchmark: this phase's model adapter uses CPU.

The alternate CPU benchmark passed all 12 first/warm calls for 1/3/5 questions. Warm median
latencies were 6.745/9.437/11.307 seconds; sampled peak process-tree RSS was 17.700 GiB.
All floating parameters were separately confirmed as FP32 on CPU. The owner explicitly
accepted this alternate CPU test and made Dell feasibility nonblocking.

Recommendation: **GO** for Phase 1 foundation review using the validated d1-3B CPU runtime
for sparse still images on sufficiently provisioned hardware. Real workload capacity and
accuracy require later validation; this is not a real-time or GPU claim. A server run does
not establish Dell feasibility. Fallback selection must be explicit, with image/API
equivalence and independent licence review; no quantised alternative is claimed equivalent.
Capture, inference, storage and UI placement remain independent under ADR-0002.

Before live capture: review/authorise Phase 1, choose the validated real engine/runtime, decide
the application/model licence position, and validate workload-specific accuracy and capacity.
No dashboard, camera integration, distributed inference worker or deployment service was built.
