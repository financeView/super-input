# Implementation status

Updated: 2026-10-07

## Starting state and intended target

The checked-out `main` branch originally contained design and review documentation only. Plan 1 remains the core rerank and offline benchmark target. Plan 2 (Squirrel/IMK integration) was previously deferred; at the user's request, its source integration is now implemented, but the target-Mac build and behavior gate is still open.

## Implemented

The repository now has a Python package and pytest configuration (Python >=3.11), with lazy MLX imports and a deterministic 200-item corpus (40 seed contexts × 5 fuzzy-spelling ratios). The core includes Rime-compatible syllable normalization, fuzzy groups parsed from the shared schema, ambiguous DP segmentation with partial-tail retention, pypinyin heteronym readings, T0/T1 DP validation including erhua and strict non-Han rejection, an L1 mean-logprob scorer interface, local L2 prompt/decoder, an OpenAI-compatible BYOK L2 client, secure macOS Keychain lookup, and per-session 5-sample/3-timeout downgrade windows.

The local HTTP service includes a 0600 token, constant-time bearer validation, protocol-version check, candidate/request bounds, L1/L2 validation, executor-bounded hard timeout, and fast-path fallback. Deployment templates, installation script and HTTP smoke test are present. The librime C harness now uses the versioned `RimeApi` function table, explicit schema selection, the shared `essay.txt` vocabulary preset, and the same schema's fuzzy rules plus OpenCC simplified-Chinese conversion. Its offline runner writes a local (ignored) same-schema top-20 baseline.

## Validation on the shared computer

Environment: Python 3.12.3, Linux x86_64. I installed an isolated `.venv` with the declared runtime/test dependencies, installed the package editable, and installed CMake/librime system dependencies. The upstream librime 1.17.0 source compiled successfully with GCC 13.3; the C harness linked and ran against it. The build also used the installed OpenCC data and Rime's minimal `essay.txt` preset.

Latest full test run after the Plan 2 source integration: **79 passed, 0 skipped** in 7.07 seconds. Both real librime integration tests ran and passed. Pytest reports one non-blocking Starlette deprecation warning: `starlette.testclient` currently warns that `httpx` support is deprecated in favor of `httpx2`.

The deterministic dataset generator produces 200 rows. The real librime runner generated candidates for all **158 unique key strings** in those rows. On the 200 expected-output examples, baseline top-20 recall was **105/200 (52.5%)** and baseline top-1 accuracy was **105/200 (52.5%)**; none of the key strings returned an empty candidate menu. These are baseline-only measurements, not L1 results. They show the current reference lexicon does not contain/recover many expected full phrases, so any L1 accuracy gain gate remains open and must be interpreted against the measured recall ceiling.

## Plan 2 source implementation (2026-10-07)

The repository now contains a pinned Squirrel patch and macOS build entry point under `macos/`. The IMK controller debounces the current composition, submits only to the authenticated loopback service, rejects stale replies by session/request/focus/composition/cursor/page/candidate snapshots, remaps keyboard selection for L1 without visually reordering Rime candidates, and displays validated L2 text as a virtual first candidate. The bundle build includes the project schema and luna-pinyin dictionary, and adds `superpinyin` to the schema list. The build script produces an app or an unsigned internal-use `.pkg`; it does not install or replace an input method automatically.

The patch is pinned to Squirrel commit `0cd71a6130a5866b0ae6ba0494929ebdc8211194`. `macos/verify-squirrel-patch.sh` passes against a fresh clone, and the patch also applies in both directions in a clean worktree. Shell scripts pass `bash -n`. This Linux environment has no Swift compiler or Xcode, so the Swift Codable contract test and app build were not run here.

## Not measured / target-environment requirement

The available device list contains only this Linux x86_64 Sandbox; there is no authorized Apple Silicon Mac in this session. MLX, Apple Keychain, InputMethodKit, and launchd are macOS-only. Therefore a real MLX model load, L1/L2 quality and latency, KV-cache probe, launchd boot, Xcode build, and Squirrel keyboard/selection integration have not been measured here. No installable app or package was produced in this session. The Python and Linux librime portions are runnable and verified; the macOS model/integration portions are not.

The plan's final gate (L1 improvement versus same-schema baseline, real p95 latency, KV cache, L2 false-accept review, and Rime/Squirrel behavior) remains **open**. Do not infer a Plan 2 go/no-go from unit tests, the librime baseline alone, or mocked scorers.

## External resource needed for the remaining gate

No additional information is needed to complete or verify the portable core. To complete the remaining target-specific gate, an authorized Apple Silicon macOS environment is required to install/run the selected MLX model and execute the macOS-only integration tests. The current session has no such device available; the local `benchmark/run_bench.py` default model is `mlx-community/Qwen2.5-1.5B-Instruct-4bit`.
