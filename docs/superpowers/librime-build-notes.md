# librime build notes

External source checked on 2026-10-05 while enabling a real same-schema baseline build:

- Official repository/README: https://github.com/rime/librime
  - Current default branch README lists C++17, CMake >=3.12, Boost >=1.74, LevelDB, Marisa, OpenCC >=1.0.2 and yaml-cpp >=0.5; google-glog and GTest are optional in its top-level dependency list.
  - Linux README build entry is `make` then `sudo make install`; our build script instead uses the repo's CMake project and installs to the workspace-local `third_party/install` prefix (no system install).
- Official build-system source checked from a shallow recursive clone of the same repository: https://github.com/rime/librime/blob/master/CMakeLists.txt and https://github.com/rime/librime/blob/master/Makefile
  - CMake declares `BUILD_TEST` default ON and uses `find_package(GTest REQUIRED)` if enabled; the workspace build explicitly turns tests OFF.
  - CMake project uses `find_package(Boost 1.74.0 REQUIRED COMPONENTS regex)` on Linux and requires the local `FindGlog`, `FindYamlCpp`, `FindLevelDb`, `FindMarisa`, and `FindOpencc` modules.
  - The official Makefile installs to `/usr` by default on Linux; we do not run it.
- Additional cross-check: https://context7.com/rime/librime
  - Repeats Linux dependency/build guidance and confirms upstream recursive clone usage.

Workspace dependency install (Ubuntu 24.04 packages): `cmake`, Boost headers/regex, glog, LevelDB, Marisa, OpenCC, yaml-cpp, plus existing build-essential/pkg-config. Compiled artifacts and third-party source are ignored/untracked workspace-local outputs, not part of the deliverable commit.

The matching official Luna Pinyin sources were also checked:

- Repository and README: https://github.com/rime/rime-luna-pinyin — the README explicitly documents `v` as the keyboard spelling for `ü`; repository currently contains the core dictionary and schema family.
- Core dictionary: https://github.com/rime/rime-luna-pinyin/blob/master/luna_pinyin.dict.yaml — dictionary metadata sets `use_preset_vocabulary: true`, so the shared `essay.txt` preset is required for normal preset-frequency vocabulary.
- Main schema and simplified variant: https://raw.githubusercontent.com/rime/rime-luna-pinyin/master/luna_pinyin.schema.yaml and https://github.com/rime/rime-luna-pinyin/blob/master/luna_pinyin_simp.schema.yaml — the official schema uses an OpenCC simplifier filter; its simplified variant resets the simplified option by default. The local benchmark schema mirrors this simplified-output behavior while retaining its own shared fuzzy spelling algebra.
