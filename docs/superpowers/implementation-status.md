# Implementation status

Updated: 2026-10-05

## Starting state and intended target

The checked-out `main` branch contained design and review documentation only (`README.md` had one heading; there was no source tree, package metadata, or test configuration). The authoritative target is Plan 1 in `docs/superpowers/plans/2026-09-23-rerank-core-and-benchmark.md`: implement the `rerank` core and offline librime/model benchmark before any Squirrel code. Plan 2 (Squirrel/IMK integration) is explicitly outside this plan and has not been started.

## Implemented

The repository now has a Python package and pytest configuration (Python >=3.11), with lazy MLX imports and a deterministic 200-item corpus (40 seed contexts × 5 fuzzy-spelling ratios). The core includes Rime-compatible syllable normalization, fuzzy groups parsed from the shared schema, ambiguous DP segmentation with partial-tail retention, pypinyin heteronym readings, T0/T1 DP validation including erhua and strict non-Han rejection, an L1 mean-logprob scorer interface, local L2 prompt/decoder, an OpenAI-compatible BYOK L2 client, secure macOS Keychain lookup, and per-session 5-sample/3-timeout downgrade windows.

The local HTTP service includes a 0600 token, constant-time bearer validation, protocol-version check, candidate/request bounds, L1/L2 validation, executor-bounded hard timeout, and fast-path fallback. Deployment templates, installation script and HTTP smoke test are present. The librime C harness now uses the versioned `RimeApi` function table, explicit schema selection, the shared `essay.txt` vocabulary preset, and the same schema's fuzzy rules plus OpenCC simplified-Chinese conversion. Its offline runner writes a local (ignored) same-schema top-20 baseline.

## Validation on the shared computer

Environment: Python 3.12.3, Linux x86_64. I installed an isolated `.venv` with the declared runtime/test dependencies, installed the package editable, and installed CMake/librime system dependencies. The upstream librime 1.17.0 source compiled successfully with GCC 13.3; the C harness linked and ran against it. The build also used the installed OpenCC data and Rime's minimal `essay.txt` preset.

Latest full test run: **76 passed, 0 skipped** in 6.17 seconds. Both real librime integration tests ran and passed. Pytest reports one non-blocking Starlette deprecation warning: `starlette.testclient` currently warns that `httpx` support is deprecated in favor of `httpx2`.

The deterministic dataset generator produces 200 rows. The real librime runner generated candidates for all **158 unique key strings** in those rows. On the 200 expected-output examples, baseline top-20 recall was **105/200 (52.5%)** and baseline top-1 accuracy was **105/200 (52.5%)**; none of the key strings returned an empty candidate menu. These are baseline-only measurements, not L1 results. They show the current reference lexicon does not contain/recover many expected full phrases, so any L1 accuracy gain gate remains open and must be interpreted against the measured recall ceiling.

## Not measured / target-environment requirement

The available device list contains only this Linux x86_64 Sandbox; there is no authorized Apple Silicon Mac in this session. MLX, Apple Keychain, InputMethodKit, and launchd are macOS-only. Therefore a real MLX model load, L1/L2 quality and latency, KV-cache probe, launchd boot, and Squirrel keyboard/selection integration have not been measured here. The Python and Linux librime portions are runnable and verified; the macOS model/integration portions are not.

The plan's final gate (L1 improvement versus same-schema baseline, real p95 latency, KV cache, L2 false-accept review, and Rime/Squirrel behavior) remains **open**. Do not infer a Plan 2 go/no-go from unit tests, the librime baseline alone, or mocked scorers.

## External resource needed for the remaining gate

No additional information is needed to complete or verify the portable core. To complete the remaining target-specific gate, an authorized Apple Silicon macOS environment is required to install/run the selected MLX model and execute the macOS-only integration tests. The current session has no such device available; the local `benchmark/run_bench.py` default model is `mlx-community/Qwen2.5-1.5B-Instruct-4bit`.
