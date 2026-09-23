# rerank-core 与离线基准 实施计划（Plan 1/2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 rerank-service 的核心库（音节/模糊音等价类/校验/L1 打分/L2 解码）并跑通离线基准——在写任何 Squirrel 代码之前验证 LLM 路线值不值（spec §6.1），产出延迟-模型尺寸曲线与 4 项存疑的实测答案。

**Architecture:** 纯 Python 包 `rerank`：音节表 → 解析 librime 同源 schema 得模糊等价类 → 击键 DP 切分 → L2 校验（DP 对齐+儿化+有界编辑）→ MLX logprob 打分（L1，惰性导入）→ 生成式 L2。基准侧：librime 源码编译 + C 工具以同一 schema 吐 top-20 基线。服务侧：FastAPI + token 鉴权 + 超时降级 + launchd。**Squirrel fork 集成 = Plan 2**，以本计划 Task 10 的 gate 报告为输入。

**Tech Stack:** Python 3.11+ / pytest / pypinyin / PyYAML / mlx-lm（mlx-community Qwen2.5-*-Instruct-4bit）/ FastAPI + uvicorn / librime（源码编译，C API）

## Global Constraints（每个任务隐含遵守）

- 包名 `rerank`，源码 `src/rerank/`；`mlx-lm` 惰性导入（在函数/`__init__` 内 import），单元测试不得加载模型
- **模糊音等价类单一事实源** = `assets/superpinyin.schema.yaml`；校验与服务只准解析该文件，禁止硬编码副本（spec §3）
- 校验规则（spec §4.4）：音节层比对（模糊等价类内相等）、不校声调、多音字任一读音即过；T1 额外允许 ≤2 字无音节插入/删除
- IPC：HTTP 127.0.0.1:47625、头 `X-SuperInput-Protocol: 1`、Bearer token 于 `~/Library/Application Support/super-input/token`（0600）
- 触发门槛 ≥2 完整音节；L1 只走本地 logprob（云无 logprob，云仅 L2）
- 延迟：L1 P95 <800ms / 硬限 1500ms；L2 P95 <2s；目标硬件 16GB+ M 系列
- 基线必须与打分跑同一 schema（否则 +15pt 不可归因，spec §6.1）
- 每 Task 一次 commit；conventional commits
- 本计划零 Squirrel/IME 代码（Plan 2 范围）

## 文件结构（分解决策锁定）

```
super-input/
├── pyproject.toml
├── assets/superpinyin.schema.yaml      # 模糊音规则单一事实源（基线与服务共用）
├── src/rerank/
│   ├── syllables.py    # 有效音节表 + v→ü 归一化
│   ├── fuzzy.py        # schema 解析 → 等价类（并查集）
│   ├── segment.py      # 击键串 → 音节切分（DP、完整音节前缀、枚举上限）
│   ├── readings.py     # 汉字→读音（pypinyin heteronym，多音字）
│   ├── validator.py    # L2 校验层（DP 对齐 / 儿化 / T0 / T1）
│   ├── testgen.py      # 测试集生成（种子句 + 模糊音强度变体）
│   ├── scorer.py       # L1：MLX logprob 打分（rank_from_scores 纯函数 + MLXScorer）
│   ├── decode_l2.py    # L2：本地生成式解码（prompt 构建纯函数 + LocalDecoder）
│   ├── cloud.py        # L2：云 BYOK（OpenAI 兼容，重试 1 次）
│   ├── policy.py       # 超时滑动窗口降级（5 次窗口 3 次超时 → 本会话 L2 走云）
│   ├── config.py       # 默认配置 + ~/.superinput/rerank.yaml 合并
│   └── service.py      # FastAPI（/rerank /health，token 中间件，scorer 可注入）
├── tests/              # 与 src 镜像；基线测试标 integration（工具缺失则 skip）
├── baseline/
│   ├── dump_candidates.c
│   ├── build.sh        # clone librime --recursive + cmake + clang 工具
│   └── data/           # default.yaml + schema（从 assets 拷贝）+ luna_pinyin.dict.yaml（curl）
├── benchmark/
│   ├── run_baseline.py  # 数据集 → librime top-20 → baseline.json
│   ├── run_bench.py     # L1/L2 指标 + report.md（gate 输入）
│   ├── latency_curve.py # 模型尺寸 × 前文长度 → 延迟曲线
│   └── datasets/        # dataset.json / baseline.json（生成物）
└── deploy/com.superinput.rerank.plist
```

---

### Task 1: 脚手架 + 音节表

**Files:**
- Create: `pyproject.toml`、`src/rerank/__init__.py`、`src/rerank/syllables.py`、`tests/test_syllables.py`

**Interfaces:**
- Produces: `SYLLABLES: frozenset[str]`（书写形式，含 ü 形如 `lü`）、`norm(s: str) -> str`（`v→ü`，小写化；后续所有模块以 norm 后形态比较）

- [ ] **Step 1: 建 venv 与骨架**

```bash
cd /Users/lijianhua04/Documents/IdeaProject/super-input
# Python 版本预检（reviewer：str | None 注解在 ≤3.10 上 import 即 TypeError）
PY3=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(printf '%s\n3.11' "$PY3" | sort -V | head -1)" != "3.11" ]; then
  echo "需要 Python ≥3.11，当前 $PY3。brew install python@3.11 后用 python3.11 重试"
  exit 1
fi
python3 -m venv .venv
mkdir -p src/rerank tests benchmark/datasets baseline/data deploy assets scripts
touch src/rerank/__init__.py
# 仓库卫生（reviewer：防 4MB 词典/venv/编译产物进 git）
cat > .gitignore <<'GIEOF'
.venv/
third_party/
__pycache__/
*.egg-info/
benchmark/datasets/baseline.json
GIEOF
```

`pyproject.toml`：

```toml
[project]
name = "super-input-rerank"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pypinyin>=0.51", "PyYAML>=6", "fastapi>=0.110", "uvicorn>=0.29", "requests>=2.31"]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]
ml = ["mlx-lm>=0.19"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
pythonpath = ["src"]
markers = ["integration: needs librime tool or MLX model"]
```

- [ ] **Step 2: 写失败测试 `tests/test_syllables.py`**

```python
from rerank.syllables import SYLLABLES, norm

def test_valid_syllables():
    for s in ["feng", "fen", "zhuang", "chuang", "lü", "nü", "er", "sheng", "jin", "xuan", "seng", "rua"]:
        assert s in SYLLABLES, s

def test_invalid_syllables():
    for s in ["fengg", "ng", "vv", "zhx", "ian"]:
        assert s not in SYLLABLES, s

def test_norm_maps_v_to_umlaut():
    assert norm("lv") == "lü"
    assert norm("nv3") == "nü3"
    assert norm("FENG") == "feng"
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/test_syllables.py -v`
Expected: FAIL（`ModuleNotFoundError: rerank.syllables`）

- [ ] **Step 4: 实现 `src/rerank/syllables.py`**

```python
"""有效普通话音节表（书写形式）与归一化。用户键入 v 表示 ü。"""
import re

_RAW = """
a ai an ang ao
ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng
chi chong chou chu chua chuai chuan chuang chun chuo ci cong cou cu cuan cui cun cuo
da dai dan dang dao de dei dia die diao diu dian ding dou du duo dui duan dong
er
fa fei fen feng fo fou fu
ga gai gan gang gao ge gei gen geng gong gou gu gua guo guai guan guang gun
ha hai han hang hao he hei hen heng hong hou hu hua huo huai huan huang hun
ji jia jie jiao jiu jian jin jiang jing ju jue juan jun
ka kai kan kang kao ke ken keng kong kou ku kua kuo kuai kuan kuang kun
la lai lan lang lao le lei lou leng li lie liao liu lian lin liang ling lu luo luan lun lü lüe
ma mai man mang mao me mei men mi mie miao miu mian min ming mo mou mu
na nai nan nang nao ne nei nen ni nie niao niu nian nin niang ning nu nuo nuan nun nü nüe
o ou
pa pai pan pang pao pei pen peng pi pie piao pian pin ping po pou pu
qi qia qie qiao qiu qian qin qiang qing qu que quan qun
ran rang rao re ren reng ri rong rou ru rua rui ruan run ruo
sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng
shi shou shu shua shuo shuai shuan shun song sou su suo sui suan sun
ta tai tan tang tao te teng ti tie tiao tian ting tu tuo tui tuan tun tong
wa wai wan wang wei wen weng wo wu
xi xia xie xiao xiu xian xin xiang xing xu xue xuan xun
ya yan yang yao ye yi yin you ying yong you yu yue yuan yun yo
chui zhui shui dun gui kui hui xiong jiong
za ze zi zai zei zao zou zan zen zang zeng zu zuo zui zuan zun
zha zhe zhi zhai zhao zhou zhan zhen zhang zheng zhong zhu zhua zhuo zhuai zhuan zhun
nuan nun teng ruo lüe nüe yong
"""
# 注：上面末三行是把首轮遗漏的音节补齐（yang/tou/hui/gui/shui/dun/xiong/jiong/
# lüe/nüe/ruo/teng/chui/zhui/kui——reviewer 实测发现「好像 haoxiang」都会切分失败）。
# 实施时建议对照标准 410 音节全表逐项校验一次（Task 1 Step 5 之外加人工比对）。
SYLLABLES = frozenset(_RAW.split())

def norm(s: str) -> str:
    return s.strip().lower().replace("v", "ü")
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_syllables.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src tests
git commit -m "feat(rerank): scaffold + pinyin syllable table"
```

---

### Task 2: 模糊音等价类（schema 单一事实源）

**Files:**
- Create: `assets/superpinyin.schema.yaml`、`src/rerank/fuzzy.py`、`tests/test_fuzzy.py`

**Interfaces:**
- Consumes: `SYLLABLES`
- Produces: `load_fuzzy_classes(schema_path: str) -> FuzzyClasses`；`FuzzyClasses.cls(s: str) -> int`（未知音节自成一类）；`FuzzyClasses.pair_count -> int`

- [ ] **Step 1: 写 schema `assets/superpinyin.schema.yaml`**（基线与服务共用——单一事实源）

```yaml
# superpinyin：super-input 基准/服务共用的拼音 schema。
# 模糊音规则 = 等价类的唯一来源；rerank.fuzzy 解析本文件，librime 基线部署本文件。
schema:
  schema_id: superpinyin
  name: SuperInput基准拼音
  version: 1

engine:
  processors: [ speller, express_editor ]
  segmentors: [ abc_segmentor, fallback_segmentor ]
  translators: [ script_translator ]

speller:
  alphabet: zyxwvutsrqponmlkjihgfedcba
  algebra:
    - derive/^([zcs])h/$1/          # zh ch sh → z c s（平翘舌）
    - derive/^([zcs])/$1h/          # z c s → zh ch sh
    - derive/([ei])n$/$1ng/         # in→ing, en→eng（前后鼻音）
    - derive/([ei])ng$/$1n/         # ing→in, eng→en
    - derive/([aou])n$/$1ng/        # an→ang, on→ong, un→ung(无效自动丢弃)
    - derive/([aou])ng$/$1n/        # ang→an, ong→on(无效自动丢弃)

menu:
  page_size: 20                      # L1 打分取材上限（spec §3 配置三层第 1 条）

translator:
  dictionary: luna_pinyin
```

- [ ] **Step 2: 写失败测试 `tests/test_fuzzy.py`**

```python
from rerank.fuzzy import load_fuzzy_classes

FC = load_fuzzy_classes("assets/superpinyin.schema.yaml")

def test_front_back_nasal_same_class():
    assert FC.cls("fen") == FC.cls("feng")
    assert FC.cls("jin") == FC.cls("jing")
    assert FC.cls("chen") == FC.cls("cheng")

def test_retroflex_same_class():
    assert FC.cls("za") == FC.cls("zha")
    assert FC.cls("si") == FC.cls("shi")

def test_unrelated_differ():
    assert FC.cls("hao") != FC.cls("fen")

def test_unknown_syllable_self_class():
    assert FC.cls("hao") == FC.cls("hao")  # same unknown -> same id
```

- [ ] **Step 3: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_fuzzy.py -v`
Expected: FAIL（`No module named 'rerank.fuzzy'`）

- [ ] **Step 4: 实现 `src/rerank/fuzzy.py`**

```python
"""从 rime schema 的 speller/algebra derive 规则推导音节等价类（并查集）。

只支持 derive/<regex>/<repl>/ 形式；derive 结果不在 SYLLABLES 内的自动丢弃。
等价类语义（reviewer 发现的闭包歧义，此处钉死）：**规则对内等价**而非
传递闭包——an↔ang 是一类、en↔eng 是一类，但 zhan(=zha+an) 不会因此
与 zang(=za+ang) 连通。实现：每条 derive 规则生成 (原音节, 派生音节) 对，
**按规则号分组**做并查集（不同规则不合并根）——class id = 规则组内根。"""
import re
import yaml

from .syllables import SYLLABLES


class FuzzyClasses:
    def __init__(self, rule_groups: list[list[tuple[str, str]]]):
        # 每组独立并查集（组间不闭包）
        self._groups: list[dict[str, str]] = [dict() for _ in rule_groups]
        for gi, pairs in enumerate(rule_groups):
            parent = self._groups[gi]
            for a, b in pairs:
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                self._union_in(parent, a, b)
        self.pair_count = sum(len({p for p in g}) for g in rule_groups)

    def _union_in(self, parent: dict[str, str], a: str, b: str) -> None:
        ra, rb = self._find_in(parent, a), self._find_in(parent, b)
        if ra != rb:
            parent[ra] = rb

    def _find_in(self, parent: dict[str, str], s: str) -> str:
        parent.setdefault(s, s)
        root = s
        while parent[root] != root:
            root = parent[root]
        while parent[s] != root:
            parent[s], s = root, parent[s]
        return root

    def cls(self, s: str) -> int:
        # 类标识 = (组号, 组内根) 的哈希；不在任何组 → (−1, 自身)
        for gi, parent in enumerate(self._groups):
            if s in parent:
                return hash((gi, self._find_in(parent, s)))
        return hash((-1, s))

    def _ensure(self, s: str) -> None:
        self._parent.setdefault(s, s)

    def _find(self, s: str) -> str:
        self._ensure(s)
        root = s
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[s] != root:  # 路径压缩
            self._parent[s], s = root, self._parent[s]
        return root

    def _union(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[ra] = rb

    def cls(self, s: str) -> int:
        return hash(self._find(s))


def load_fuzzy_classes(schema_path: str) -> FuzzyClasses:
    with open(schema_path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    rules = doc["speller"]["algebra"]
    rule_groups: list[list[tuple[str, str]]] = []
    for rule in rules:
        rule = rule.strip()
        if not rule.startswith("derive/"):
            continue
        spec = rule[len("derive/"):].rstrip("/")
        if spec.count("/") < 1:
            continue
        pattern, repl = spec.split("/", 1)
        rx = re.compile(pattern)
        pairs: set[tuple[str, str]] = set()
        for s in SYLLABLES:
            t = rx.sub(repl, s)
            if t != s and t in SYLLABLES:
                pairs.add((s, t))
        if pairs:
            rule_groups.append(sorted(pairs))
    return FuzzyClasses(rule_groups)
```

- [ ] **Step 5: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_fuzzy.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add assets/superpinyin.schema.yaml src/rerank/fuzzy.py tests/test_fuzzy.py
git commit -m "feat(rerank): fuzzy equivalence classes from shared rime schema"
```

---

### Task 3: 击键切分 DP

**Files:**
- Create: `src/rerank/segment.py`、`tests/test_segment.py`

**Interfaces:**
- Consumes: `SYLLABLES`、`norm`
- Produces: `all_segmentations(keys: str, limit: int = 32) -> tuple[list[list[str]], str]`（全部有效切分 + 不可切分的尾部残串）；`segment_keys(keys: str) -> tuple[list[str] | None, str]`（单一切分便捷函数）

- [ ] **Step 1: 写失败测试 `tests/test_segment.py`**

```python
from rerank.segment import all_segmentations, segment_keys

def test_plain_two_syllables():
    segs, frag = all_segmentations("jintian")
    assert [ "jin", "tian" ] in segs and frag == ""

def test_ambiguous_xian():
    segs, frag = all_segmentations("xian")
    assert ["xian"] in segs and ["xi", "an"] in segs and frag == ""

def test_trailing_fragment_is_kept_for_next_round():
    segs, frag = all_segmentations("jinf")   # f 单字母不是音节
    assert segs == [["jin"]] and frag == "f"

def test_long_input_all_covered():
    segs, frag = all_segmentations("jintiantianqihenhao")
    assert frag == "" and all(seg for seg in segs)

def test_v_normalizes_to_umlaut():
    segs, frag = all_segmentations("lvdi")
    assert ["lü", "di"] in segs and frag == ""

def test_segment_keys_single():
    segs, frag = segment_keys("jintian")
    assert segs is not None and frag == ""
```

- [ ] **Step 2: 跑测试确认失败**

Run: `.venv/bin/pytest tests/test_segment.py -v` → FAIL（模块不存在）

- [ ] **Step 3: 实现 `src/rerank/segment.py`**

```python
"""击键串 → 音节切分。dp 求最长可切前缀（完整音节前缀，spec §4.4），
回溯枚举该前缀的全部切分（音节切分歧义如 xian=xi'an|xian 由校验器全试），
尾部不可切残串返回给调用方留待下一轮停顿。"""
from .syllables import SYLLABLES, norm

_MAX_SYLL = 6  # chuang/zhuang

def _reachable(keys: str) -> list[bool]:
    n = len(keys)
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(1, n + 1):
        for j in range(max(0, i - _MAX_SYLL), i):
            if dp[j] and keys[j:i] in SYLLABLES:
                dp[i] = True
                break
    return dp

def all_segmentations(keys: str, limit: int = 32):
    keys = "".join(c for c in norm(keys) if "a" <= c <= "z" or c == "ü")
    dp = _reachable(keys)
    n = len(keys)
    cover = max(i for i in range(n + 1) if dp[i])
    results: list[list[str]] = []

    def bt(pos: int, acc: list[str]) -> None:
        if len(results) >= limit:
            return
        if pos == cover:
            results.append(list(acc))
            return
        for end in range(pos + 1, min(pos + _MAX_SYLL, cover) + 1):
            s = keys[pos:end]
            if s in SYLLABLES:
                acc.append(s)
                bt(end, acc)
                acc.pop()

    bt(0, [])
    return results, keys[cover:]

def segment_keys(keys: str):
    segs, frag = all_segmentations(keys, limit=1)
    return (segs[0] if segs else None), frag
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_segment.py -v` → 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/segment.py tests/test_segment.py
git commit -m "feat(rerank): key-string syllable segmentation DP"
```

---

### Task 4: 汉字读音与等价匹配

**Files:**
- Create: `src/rerank/readings.py`、`tests/test_readings.py`

**Interfaces:**
- Consumes: `FuzzyClasses`、`norm`
- Produces: `char_readings(ch: str) -> list[str]`（去声调、norm 后的多读音列表；非汉字返回空表）；`syllable_match(reading: str, typed: str, fuzzy: FuzzyClasses) -> bool`

- [ ] **Step 1: 写失败测试 `tests/test_readings.py`**

```python
from rerank.fuzzy import load_fuzzy_classes
from rerank.readings import char_readings, syllable_match

FC = load_fuzzy_classes("assets/superpinyin.schema.yaml")

def test_polyphonic_char_has_all_readings():
    r = char_readings("行")
    assert "hang" in r and "xing" in r

def test_readings_toneless():
    assert "feng" in char_readings("风")

def test_non_han_empty():
    assert char_readings("a") == [] and char_readings("，") == []

def test_fuzzy_match_front_back_nasal():
    assert syllable_match("feng", "fen", FC) is True
    assert syllable_match("fen", "feng", FC) is True

def test_exact_match_no_fuzzy_rules_needed():
    assert syllable_match("hao", "hao", FC) is True

def test_mismatch():
    assert syllable_match("fen", "hao", FC) is False
```

- [ ] **Step 2: 跑测试确认失败** → FAIL（模块不存在）

- [ ] **Step 3: 实现 `src/rerank/readings.py`**

```python
"""汉字 → 无声调读音（pypinyin heteronym 全读音），及音节等价匹配。"""
from functools import lru_cache

from pypinyin import pinyin, Style

from .syllables import norm
from .fuzzy import FuzzyClasses


class _Identity(FuzzyClasses):
    def __init__(self):  # type: ignore[no-untyped-def]
        self._parent = {}
        self.pair_count = 0


@lru_cache(maxsize=65536)
def char_readings(ch: str) -> list[str]:
    if not ("一" <= ch <= "鿿"):
        return []
    out = pinyin(ch, style=Style.NORMAL, heteronym=True, errors=lambda x: [])[0]
    return [norm(x) for x in out] or []


def syllable_match(reading: str, typed: str, fuzzy: FuzzyClasses) -> bool:
    return fuzzy.cls(reading) == fuzzy.cls(typed)
```

- [ ] **Step 4: 跑测试确认通过** → 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/readings.py tests/test_readings.py
git commit -m "feat(rerank): char readings via pypinyin + fuzzy syllable match"
```

---

### Task 5: L2 校验器（DP 对齐 / 儿化 / T0 / T1）

**Files:**
- Create: `src/rerank/validator.py`、`tests/test_validator.py`

**Interfaces:**
- Consumes: `all_segmentations`、`char_readings`、`syllable_match`、`FuzzyClasses`
- Produces: `validate(text: str, keys: str, trust: str = "T0", fuzzy: FuzzyClasses | None = None) -> Verdict`；`Verdict(ok: bool, edits: int | None, reason: str)`；`min_edit_align(chars: list[str], sylls: list[str], fuzzy) -> int`；`normalize_text(s: str) -> str`（去空白与标点）；`normalize_compare(a: str, b: str) -> bool`；`PUNCT: frozenset[str]`

- [ ] **Step 1: 写失败测试 `tests/test_validator.py`**

```python
from rerank.fuzzy import load_fuzzy_classes
from rerank.validator import validate, min_edit_align, normalize_compare

FC = load_fuzzy_classes("assets/superpinyin.schema.yaml")

def test_t0_exact_pass():
    v = validate("今天天气很好", "jintiantianqihenhao", "T0", FC)
    assert v.ok and v.edits == 0

def test_t0_fuzzy_pass_front_back_nasal():
    v = validate("风景很美", "fenjinghenmei", "T0", FC)   # fen→风 在等价类内
    assert v.ok and v.edits == 0

def test_punctuation_stripped():
    v = validate("今天，天气很好！", "jintiantianqihenhao", "T0", FC)
    assert v.ok

def test_erhua_alignment():
    assert min_edit_align(["哪", "儿"], ["nar"], FC) == 0
    assert min_edit_align(["花", "儿"], ["huar"], FC) == 0

def test_t1_insertion_of_function_word():
    v = validate("完成了任务", "wanchengrenwu", "T0", FC)   # 的 插入
    assert not v.ok
    v1 = validate("完成了任务", "wanchengrenwu", "T1", FC)
    assert v1.ok and v1.edits == 1

def test_t1_deletion():
    # keys 含 5 个音节（wan-cheng-le-ren-wu），输出只有 4 字（了 无对应）→ 1 编辑
    v = validate("完成了务", "wanchenglerenwu", "T1", FC)
    assert v.ok and v.edits == 1

def test_t1_over_limit_rejected():
    text = "完成了的了任务"                                     # 3 个无音节字
    v = validate(text, "wanchengrenwu", "T1", FC)
    assert not v.ok

def test_digit_counts_as_insertion():
    v = validate("今天3点", "jintian", "T0", FC)
    assert not v.ok

def test_unsegmentable_keys():
    v = validate("任意", "fff", "T0", FC)
    # f 非法节 → cover=0 → [[]]（长度0切分）→ 空音节表，任意文本 edits>limit → 拦截
    assert not v.ok and v.reason == "limit"

def test_normalize_text_and_compare():
    from rerank.validator import normalize_text
    assert normalize_text("今天，天气好！") == normalize_text("今天 天气 好")
    assert normalize_compare("今天，天气好！", "今天天气好") is True
```

- [ ] **Step 2: 跑测试确认失败** → FAIL（模块不存在）

- [ ] **Step 3: 实现 `src/rerank/validator.py`**

```python
"""L2 输出校验层（spec §4.4）：
预处理（标点剥离/白名单）→ DP 最小编辑对齐（儿化 1 音节↔多字、T1 有界编辑）
→ 信任级判定。T0 = 0 编辑；T1 = ≤2 插入/删除。"""
import dataclasses

from .fuzzy import FuzzyClasses, load_fuzzy_classes
from .readings import char_readings, syllable_match
from .segment import all_segmentations

PUNCT = frozenset("，。！？、；：“”‘’…—·,.!?;:'\"()（）-—《》【】 ")
_DEFAULT_FC: FuzzyClasses | None = None


@dataclasses.dataclass
class Verdict:
    ok: bool
    edits: int | None
    reason: str


def _fc(fuzzy: FuzzyClasses | None) -> FuzzyClasses:
    global _DEFAULT_FC
    if fuzzy is not None:
        return fuzzy
    if _DEFAULT_FC is None:
        _DEFAULT_FC = load_fuzzy_classes("assets/superpinyin.schema.yaml")
    return _DEFAULT_FC


def normalize_text(s: str) -> str:
    return "".join(c for c in s if not c.isspace() and c not in PUNCT)


def normalize_compare(a: str, b: str) -> bool:
    return normalize_text(a) == normalize_text(b)


def min_edit_align(chars: list[str], sylls: list[str], fuzzy: FuzzyClasses) -> int:
    m, n = len(chars), len(sylls)
    reads = [char_readings(c) for c in chars]
    INF = 10 ** 9
    dp = [[INF] * (n + 1) for _ in range(m + 1)]
    dp[0][0] = 0
    for i in range(m + 1):
        for j in range(n + 1):
            cur = dp[i][j]
            if cur == INF:
                continue
            if i < m:                                   # 插入：输出多字（无音节对应）
                dp[i + 1][j] = min(dp[i + 1][j], cur + 1)
            if j < n:                                   # 删除：丢一个已打音节
                dp[i][j + 1] = min(dp[i][j + 1], cur + 1)
            if i < m and j < n:                         # 常规匹配（多音字任一读音）
                for r in reads[i]:
                    if syllable_match(r, sylls[j], fuzzy):
                        dp[i + 1][j + 1] = min(dp[i + 1][j + 1], cur)
                        break
                if i + 1 < m and chars[i + 1] == "儿":  # 儿化：前字+儿 两字共耗一个音节
                    for r in reads[i]:
                        if sylls[j] == r + "r":
                            dp[i + 2][j + 1] = min(dp[i + 2][j + 1], cur)
                            break
    return dp[m][n]


def validate(text: str, keys: str, trust: str = "T0", fuzzy: FuzzyClasses | None = None):
    fc = _fc(fuzzy)
    segs_list, _frag = all_segmentations(keys)
    if not segs_list:
        return Verdict(False, None, "unsegmentable")
    chars = [c for c in text if not c.isspace() and c not in PUNCT]
    best: int | None = None
    for sylls in segs_list:
        e = min_edit_align(chars, sylls, fc)
        if best is None or e < best:
            best = e
    assert best is not None
    limit = 0 if trust == "T0" else 2
    return Verdict(best <= limit, best, "limit" if best > limit else "ok")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `.venv/bin/pytest tests/test_validator.py -v` → 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/validator.py tests/test_validator.py
git commit -m "feat(rerank): L2 validation layer (DP align, erhua, T0/T1 bounded edit)"
```

---

### Task 6: 测试集生成器

**Files:**
- Create: `src/rerank/testgen.py`、`tests/test_testgen.py`；生成物 `benchmark/datasets/dataset.json`

**Interfaces:**
- Consumes: `char_readings`、`FuzzyClasses`
- Produces: `SEEDS: list[tuple[str, str]]`（context, sentence）；`make_keys(sentence: str, swap_ratio: float, fuzzy) -> str`；`build_dataset(schema_path: str = ...) -> dict`（`{"items": [{"context","keys","expected","swap_ratio"}]}`）；`write_dataset(out_path: str)`

- [ ] **Step 1: 写失败测试 `tests/test_testgen.py`**

```python
from rerank.testgen import SEEDS, make_keys, build_dataset
from rerank.fuzzy import load_fuzzy_classes

FC = load_fuzzy_classes("assets/superpinyin.schema.yaml")

def test_seeds_have_context_and_sentence():
    assert len(SEEDS) >= 40
    for ctx, s in SEEDS:
        assert len(ctx) >= 4 and len(s) >= 4

def test_make_keys_swaps_fuzzy_syllable():
    k = make_keys("风景很美", 1.0, FC)   # 风 feng→fen、景 jing→jin、很 hen→heng
    assert k == "fenjinhengmei"

def test_make_keys_zero_ratio_keeps_correct():
    assert make_keys("风景很美", 0.0, FC) == "fengjinghenmei"

def test_dataset_200_plus_and_wellformed():
    ds = build_dataset()
    items = ds["items"]
    assert len(items) >= 200
    for it in items:
        assert it["keys"].isalpha() and len(it["keys"]) >= 4
        assert it["expected"] and it["context"]
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/testgen.py`**

```python
"""测试集：40 条种子句（context, sentence），每句 × 5 档模糊音替换强度
（0/25/50/75/100% 可换字被换成等价类混淆音）→ ≥200 条。
keys = 「前后鼻音混淆用户」的击键模拟：正确读音按比例替换为同类另一形态。"""
import json
import pathlib

from .fuzzy import FuzzyClasses, load_fuzzy_classes
from .readings import char_readings

SEEDS: list[tuple[str, str]] = [
    ("周末的清晨很安静", "空气里有一点凉意"),
    ("朋友约我去逛超市", "我们分头买东西"),
    ("登高望远的心情", "风景美得让人屏住呼吸"),
    ("他是个很真诚的人", "说话从来不含糊"),
    ("公司楼下的银行", "每天早上都有人排队"),
    ("这座城市的生活节奏", "让人又爱又恨"),
    ("春天的森林里", "鸟叫声此起彼伏"),
    ("老人的心情很好", "每天坚持晨跑锻炼"),
    ("声音太大听不清", "请你重新说一遍"),
    ("真正的朋友", "不会在你落魄时沉默"),
    ("完成了今天的任务", "晚上可以安心休息"),
    ("深圳的春天很短", "一转眼就入夏了"),
    ("银杏叶黄了", "满地都是金色的"),
    ("生产力工具", "用好了能省一半时间"),
    ("找到证据了吗", "没有证据就不能下结论"),
    ("支持正版软件", "尊重开发者的劳动"),
    ("挑战自己的极限", "人生才有意思"),
    ("上传文件失败", "请检查网络连接"),
    ("车站出口在哪边", "我记得是在东边"),
    ("自然生长的果树", "果子味道更好"),
    ("智慧城市治理", "需要长期投入"),
    ("人民银行总部", "就在这条街上"),
    ("心情不好想吃火锅", "约上朋友一起"),
    ("拼命工作不是办法", "身体才是本钱"),
    ("亲自体验过的人", "才有发言权"),
    ("沉默是金", "但该说话时要说"),
    ("晨雾散去之后", "山下的城市清晰可见"),
    ("成功没有秘诀", "只有日复一日地坚持"),
    ("孩子的成长过程", "需要父母足够的耐心"),
    ("门前的花儿开了", "蝴蝶飞来飞去"),
    ("站在城市的高处", "看万家灯火"),
    ("商务谈判进行得很顺利", "双方都做了让步"),
    ("生产线出了故障", "工程师连夜抢修"),
    ("森林防火人人有责", "一点火星都不行"),
    ("证据链条完整", "案子可以移送了"),
    ("人生地不熟", "问问路边的老人"),
    ("城市治理的智慧", "藏在细节里"),
    ("声音识别技术", "这几年进步飞快"),
    ("认真的样子最帅", "你工作的时候真好看"),
    ("挣钱的速度", "赶不上房价的速度"),
]


def _swap(reading: str, fc: FuzzyClasses) -> str | None:
    """返回等价类中另一个合法音节（模拟用户打混淆音），无则 None。"""
    import itertools

    from .syllables import SYLLABLES

    for s in SYLLABLES:
        if s != reading and fc.cls(s) == fc.cls(reading):
            return s
    return None


def make_keys(sentence: str, swap_ratio: float, fuzzy: FuzzyClasses) -> str:
    out = []
    swappable = []  # (idx, swapped)
    for i, ch in enumerate(sentence):
        r = char_readings(ch)
        if r:
            sw = _swap(r[0], fuzzy)
            if sw:
                swappable.append((i, sw, r[0]))
    take = {i for k, (i, sw, r) in enumerate(swappable) if (k + 1) / max(len(swappable), 1) <= swap_ratio}
    for i, ch in enumerate(sentence):
        r = char_readings(ch)
        if r and i in take:
            out.append(next(sw for j, sw, _ in swappable if j == i))
        elif r:
            out.append(r[0])
    return "".join(out)


def build_dataset(schema_path: str = "assets/superpinyin.schema.yaml") -> dict:
    fc = load_fuzzy_classes(schema_path)
    items = []
    for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
        for ctx, s in SEEDS:
            items.append({
                "context": ctx,
                "keys": make_keys(s, ratio, fc),
                "expected": s,
                "swap_ratio": ratio,
            })
    return {"items": items}


def write_dataset(out_path: str = "benchmark/datasets/dataset.json") -> None:
    p = pathlib.Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(build_dataset(), ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    write_dataset()
    print("dataset written")
```

- [ ] **Step 4: 跑测试确认通过 + 生成数据集**

Run: `.venv/bin/pytest tests/test_testgen.py -v && .venv/bin/python -m rerank.testgen`
Expected: 4 passed；`benchmark/datasets/dataset.json`（200 条）

- [ ] **Step 5: Commit**

```bash
git add src/rerank/testgen.py tests/test_testgen.py benchmark/datasets/dataset.json
git commit -m "feat(rerank): benchmark dataset generator (40 seeds x 5 fuzzy-swap ratios)"
```

---

### Task 7: librime 基线工具（C）

**Files:**
- Create: `baseline/dump_candidates.c`、`baseline/build.sh`、`baseline/data/default.yaml`；`baseline/data/superpinyin.schema.yaml`（build.sh 从 assets 拷贝）、`tests/test_baseline.py`（integration）

**Interfaces:**
- Produces: CLI `baseline/dump_candidates <data_dir>`——stdin 每行击键串，stdout 每行 `keys<TAB>index<TAB>候选文本`（index 为菜单 0 基序号，同一 keys 最多 page_size=20 行）

- [ ] **Step 1: 写 `baseline/data/default.yaml`**

```yaml
schema_list:
  - schema: superpinyin
```

- [ ] **Step 2: 写 `baseline/dump_candidates.c`**

```c
/* dump_candidates: 逐行读击键串，经 librime 处理后输出 top-20 候选。
   usage: dump_candidates <data_dir>   (stdin: keys per line) */
#include <rime_api.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "usage: dump_candidates <data_dir>\n");
        return 2;
    }
    RIME_STRUCT(RimeTraits, traits);
    traits.app_name = "super-input-baseline";
    traits.user_data_dir = argv[1];
    traits.shared_data_dir = argv[1];
    traits.modules = NULL;          /* 防 RIME_STRUCT 未清零字段读到栈垃圾 */
    RimeSetup(&traits);
    RimeInitialize(&traits);
    RimeStartMaintenance(1);
    RimeJoinMaintenance();

    RimeSessionId sid = RimeCreateSession();
    char line[512];
    while (fgets(line, sizeof(line), stdin)) {
        size_t len = strlen(line);
        while (len && (line[len - 1] == '\n' || line[len - 1] == '\r')) line[--len] = 0;
        if (!len) continue;
        RimeClearComposition(sid);
        for (size_t i = 0; i < len; i++) {
            if (line[i] >= 'a' && line[i] <= 'z')
                RimeProcessKey(sid, (int)line[i], 0);
        }
        RIME_STRUCT(RimeContext, ctx);
        if (RimeGetContext(sid, &ctx)) {
            for (int i = 0; i < ctx.menu.num_candidates; i++)
                printf("%s\t%d\t%s\n", line, i, ctx.menu.candidates[i].text);
            RimeFreeContext(&ctx);
        } else {
            printf("%s\t-\t\n", line);
        }
        fflush(stdout);
    }
    RimeDestroySession(sid);
    RimeFinalize();
    return 0;
}
```

- [ ] **Step 3: 写 `baseline/build.sh` 并执行**

```bash
#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIBRIME="$ROOT/third_party/librime"
INSTALL="$ROOT/third_party/install"
[ -f "$ROOT/baseline/data/luna_pinyin.dict.yaml" ] || \
  curl -fsSL -o "$ROOT/baseline/data/luna_pinyin.dict.yaml" \
    https://raw.githubusercontent.com/rime/rime-luna-pinyin/master/luna_pinyin.dict.yaml
cp "$ROOT/assets/superpinyin.schema.yaml" "$ROOT/baseline/data/"
if [ ! -d "$LIBRIME" ]; then
  git clone --recursive https://github.com/rime/librime.git "$LIBRIME"
fi
mkdir -p "$LIBRIME/build"
cd "$LIBRIME/build"
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$INSTALL"
make -j"$(sysctl -n hw.ncpu)" install
clang -I"$INSTALL/include" -L"$INSTALL/lib" \
  "$ROOT/baseline/dump_candidates.c" -lrime \
  -o "$ROOT/baseline/dump_candidates"
echo BUILD_OK
```

Run: `chmod +x baseline/build.sh && ./baseline/build.sh`
Expected: 末行 `BUILD_OK`（首次约 5-10 分钟；需 Xcode CLT）

- [ ] **Step 4: 手动冒烟**

```bash
echo "jintiantianqihenhao" | DYLD_LIBRARY_PATH=third_party/install/lib \
  ./baseline/dump_candidates baseline/data | head -5
```
Expected: 至少一行 `jintiantianqihenhao<TAB>0<TAB>今天天气很好`（或近似整句；首行部署会编译词典，稍慢）

- [ ] **Step 5: 写 integration 测试 `tests/test_baseline.py`**

```python
import os
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TOOL = ROOT / "baseline" / "dump_candidates"

pytestmark = pytest.mark.integration if not TOOL.exists() else pytest.mark.integration


def _run(keys: str) -> list[str]:
    env = dict(os.environ, DYLD_LIBRARY_PATH=str(ROOT / "third_party/install/lib"))
    p = subprocess.run([str(TOOL), str(ROOT / "baseline/data")],
                       input=keys + "\n", capture_output=True, text=True, env=env, timeout=120)
    return [ln.split("\t")[2] for ln in p.stdout.splitlines() if ln.count("\t") == 2]


@pytest.mark.skipif(not TOOL.exists(), reason="baseline tool not built")
def test_top_candidate_reasonable():
    cands = _run("jintiantianqihenhao")
    assert cands and any("今天" in c for c in cands)


@pytest.mark.skipif(not TOOL.exists(), reason="baseline tool not built")
def test_fuzzy_schema_active():
    cands = _run("fenjinghenmei")   # 前鼻音键 → 应召出「风景」（模糊音生效）
    assert any("风" in c for c in cands)
```

- [ ] **Step 6: 跑测试 + Commit**

Run: `.venv/bin/pytest tests/test_baseline.py -v` → 2 passed（工具未建则 skip）

```bash
git add baseline tests/test_baseline.py
git commit -m "feat(baseline): librime dump_candidates tool with shared fuzzy schema"
```

---

### Task 8: MLX 打分器（L1）

**Files:**
- Create: `src/rerank/scorer.py`、`tests/test_scorer.py`

**Interfaces:**
- Consumes: 无（纯新增）
- Produces: `rank_from_scores(scores: list[float]) -> tuple[list[int], int, float]`（（重排索引序、最佳索引、置信度=best-second logprob 差））；`MLXScorer(model_id: str)`（`.score(prefix: str, candidate: str) -> float`、`.rank(prefix, candidates)`）；`probe_prefix_cache(model_id) -> bool | None`（KV 前缀缓存可用性实测，gate 输入之一）

- [ ] **Step 1: 写失败测试 `tests/test_scorer.py`**

```python
import sys

from rerank.scorer import rank_from_scores


def test_rank_from_scores_order_and_conf():
    order, best, conf = rank_from_scores([-1.0, -3.0, -2.5])
    assert order == [0, 2, 1] and best == 0 and abs(conf - 1.5) < 1e-9

def test_rank_single_candidate_conf_zero():
    order, best, conf = rank_from_scores([-1.0])
    assert order == [0] and best == 0 and conf == 0.0

def test_import_does_not_load_mlx():
    import rerank.scorer  # noqa: F401
    assert "mlx" not in sys.modules   # 惰性导入纪律
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/scorer.py`**

```python
"""L1 似然打分（spec §2/D1）：log P(候选|前文)，argmax 重排。
纯 prefill 无解码；置信度 = best 与 second 的 logprob 差。
注意：encode(prefix+candidate) 与 encode(prefix) 的 BPE 边界可能差一两个
token（跨边界合并），对同为汉字候选的相对排序影响可忽略，基准阶段量化。"""


def rank_from_scores(scores: list[float]) -> tuple[list[int], int, float]:
    order = sorted(range(len(scores)), key=lambda i: -scores[i])
    best = order[0]
    conf = (scores[best] - scores[order[1]]) if len(order) > 1 else 0.0
    return order, best, conf


class MLXScorer:
    def __init__(self, model_id: str):
        import mlx.core as mx
        from mlx_lm.utils import load

        self._mx = mx
        self.model, self.tokenizer = load(model_id)

    def score(self, prefix: str, candidate: str) -> float:
        mx = self._mx
        pre_ids = self.tokenizer.encode(prefix)
        full_ids = self.tokenizer.encode(prefix + candidate)
        if len(full_ids) <= len(pre_ids):
            return float("-inf")
        x = mx.array(full_ids)
        logits = self.model(x)
        logprobs = mx.log_softmax(logits.astype(mx.float32), axis=-1)
        s = 0.0
        for i in range(len(pre_ids), len(full_ids)):
            s += float(logprobs[i - 1, full_ids[i]])
        return s

    def rank(self, prefix: str, candidates: list[str]):
        scores = [self.score(prefix, c) for c in candidates]
        order, best, conf = rank_from_scores(scores)
        return order, best, conf, scores


def probe_prefix_cache(model_id: str) -> bool | None:
    """实测 mlx-lm 跨请求前缀 KV 缓存（spec §9 存疑 1）。
    True=复用明显加速；False=API 存在但无加速/异常；None=当前版本无 make_prompt_cache。"""
    try:
        import time

        import mlx.core as mx
        from mlx_lm.utils import load, make_prompt_cache
    except ImportError:
        return None
    try:
        model, tok = load(model_id)
        ids = mx.array(tok.encode("今天天气很好。" * 40))
        t0 = time.perf_counter(); model(ids); t1 = time.perf_counter()      # 冷前向
        cache = make_prompt_cache(model)
        model(ids, cache=cache); t2 = time.perf_counter()                   # 填充缓存
        model(ids, cache=cache); t3 = time.perf_counter()                   # 复用
        return (t1 - t0) > (t3 - t2) * 1.5                                  # 复用快得多 → 可用
    except Exception:
        return False
```

- [ ] **Step 4: 跑测试确认通过** → 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/scorer.py tests/test_scorer.py
git commit -m "feat(rerank): L1 likelihood scorer (pure-prefill ranking, lazy mlx)"
```

---

### Task 9: L2 本地解码器

**Files:**
- Create: `src/rerank/decode_l2.py`、`tests/test_decode_l2.py`

**Interfaces:**
- Consumes: 无
- Produces: `build_prompt(context: str, sylls: list[str]) -> str`；`LocalDecoder(model_id: str)`（`.decode(context, sylls) -> str`，取首行）

- [ ] **Step 1: 写失败测试 `tests/test_decode_l2.py`**

```python
from rerank.decode_l2 import build_prompt

def test_prompt_contains_context_sylls_and_instruction():
    p = build_prompt("今天天气很好", ["fen", "jing", "hen", "mei"])
    assert "今天天气很好" in p and "fen jing hen mei" in p
    assert "只输出" in p and "不要解释" in p
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/decode_l2.py`**

```python
"""L2 整句解码（本地生成式）。输出必须经 validator 才可用（服务侧负责）。"""


def build_prompt(context: str, sylls: list[str]) -> str:
    return (
        "你是拼音转汉字引擎。把拼音转成中文。"
        "只输出与拼音逐字对应的文字，不要解释，不要加标点以外的内容。\n"
        f"前文：{context}\n"
        f"拼音：{' '.join(sylls)}\n"
        "输出："
    )


class LocalDecoder:
    def __init__(self, model_id: str):
        from mlx_lm.utils import load

        self.model, self.tokenizer = load(model_id)

    def decode(self, context: str, sylls: list[str]) -> str:
        from mlx_lm.utils import generate

        text = generate(self.model, self.tokenizer,
                        prompt=build_prompt(context, sylls),
                        max_tokens=256, verbose=False)
        return text.strip().splitlines()[0] if text.strip() else ""
```

- [ ] **Step 4: 跑测试确认通过** → 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/decode_l2.py tests/test_decode_l2.py
git commit -m "feat(rerank): L2 local generative decoder with prompt builder"
```

---

### Task 10: 基准运行器与 Gate 报告

**Files:**
- Create: `benchmark/run_baseline.py`、`benchmark/run_bench.py`、`benchmark/latency_curve.py`

**Interfaces:**
- Consumes: `dataset.json`（Task 6）、`dump_candidates`（Task 7）、`MLXScorer/rank_from_scores`（Task 8）、`LocalDecoder`（Task 9）、`validate/normalize_compare`（Task 5）
- Produces: `benchmark/datasets/baseline.json`（`{keys: [候选]}`）；`benchmark/report.md`（gate 决策输入）；`benchmark/latency.csv`

- [ ] **Step 1: 写 `benchmark/run_baseline.py` 并跑**

```python
"""数据集 → librime top-20 基线。产物 baseline.json：{keys: [候选文本]}"""
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def main() -> None:
    dataset = json.loads((ROOT / "benchmark/datasets/dataset.json").read_text())
    keys_lines = "".join(i["keys"] + "\n" for i in dataset["items"])
    env = dict(os.environ, DYLD_LIBRARY_PATH=str(ROOT / "third_party/install/lib"))
    p = subprocess.run([str(ROOT / "baseline/dump_candidates"), str(ROOT / "baseline/data")],
                       input=keys_lines, capture_output=True, text=True, env=env, timeout=1800)
    out: dict[str, list[str]] = {}
    for ln in p.stdout.splitlines():
        if ln.count("\t") != 2:
            continue
        keys, _idx, text = ln.split("\t")
        out.setdefault(keys, []).append(text)
    (ROOT / "benchmark/datasets/baseline.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(f"baseline: {len(out)} keys")


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/python benchmark/run_baseline.py`
Expected: `baseline: ≥200 keys`（首跑含词典部署，分钟级）

- [ ] **Step 2: 写 `benchmark/run_bench.py` 并跑（1.5B）**

```python
"""离线基准（spec §6.1）：召回上限 / 基线首选 / L1 / L2 指标 + report.md。
用法: run_bench.py [model_id]   默认 mlx-community/Qwen2.5-1.5B-Instruct-4bit"""
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rerank.fuzzy import load_fuzzy_classes           # noqa: E402
from rerank.scorer import MLXScorer, rank_from_scores  # noqa: E402
from rerank.segment import segment_keys               # noqa: E402
from rerank.decode_l2 import LocalDecoder            # noqa: E402
from rerank.validator import validate, normalize_text  # noqa: E402
from rerank.scorer import probe_prefix_cache  # noqa: E402

CONF_THRESHOLD = 2.0


def pctl(xs: list[float], q: float) -> float:
    xs = sorted(xs)
    return xs[min(int(q * len(xs)), len(xs) - 1)] if xs else 0.0


def main() -> None:
    model_id = sys.argv[1] if len(sys.argv) > 1 else "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
    fc = load_fuzzy_classes(str(ROOT / "assets/superpinyin.schema.yaml"))
    items = json.loads((ROOT / "benchmark/datasets/dataset.json").read_text())["items"]
    base = json.loads((ROOT / "benchmark/datasets/baseline.json").read_text())

    scorer = MLXScorer(model_id)
    decoder = LocalDecoder(model_id)

    n = len(items)
    recall20 = base_first = l1_first = l2_tried = l2_ok = l2_correct = l2_blocked = 0
    validated_wrong = 0
    t1_extra_ok = 0
    lat: list[float] = []
    l2_lat: list[float] = []
    details = []
    for it in items:
        cands = base.get(it["keys"], [])
        exp = normalize_text(it["expected"])
        norm = normalize_text  # noqa: E731
        if any(norm(c) == exp for c in cands):
            recall20 += 1
        if cands and norm(cands[0]) == exp:
            base_first += 1
        if not cands:
            details.append({**it, "note": "no-candidates"})
            continue
        t0 = time.perf_counter()
        scores = [scorer.score(it["context"], c) for c in cands[:20]]
        order, best, conf = rank_from_scores(scores)
        lat.append((time.perf_counter() - t0) * 1000)
        if norm(cands[best]) == exp:
            l1_first += 1
        # 升级判定（spec §4.3）：best≠快速通道首选 且 置信度低 → L2
        if best != 0 and conf < CONF_THRESHOLD:
            l2_tried += 1
            segs, _frag = segment_keys(it["keys"])
            t2 = time.perf_counter()
            try:
                text = decoder.decode(it["context"], segs or [])
                l2_lat.append((time.perf_counter() - t2) * 1000)
                v = validate(text, it["keys"], "T0", fc)
                if not v.ok:
                    # T1 对照量（spec §7 验收第 2 条：T1 有界编辑可控性）：
                    # T0 拦下的输出里有多少是 T1 应放行的（虚词/儿化类插入）
                    v1 = validate(text, it["keys"], "T1", fc)
                    if v1.ok:
                        t1_extra_ok += 1
                    details.append({**it, "l2_text": text, "l2_ok": False})
                    continue
                if v.ok:
                    l2_ok += 1
                    if normalize_text(text) == exp:
                        l2_correct += 1
                    else:
                        validated_wrong += 1
                else:
                    l2_blocked += 1
            except Exception as e:  # noqa: BLE001
                l2_blocked += 1
                details.append({**it, "note": f"l2-error:{e}"})
                continue
            details.append({**it, "l2_text": text, "l2_ok": True})
        else:
            details.append({**it, "l1_best": cands[best]})

    kv = probe_prefix_cache(model_id)
    pct = lambda x: f"{x / n:.1%}"  # noqa: E731
    report = f"""# 离线基准报告（gate 输入）

- 模型: {model_id}
- 测试集: {n} 条（40 种子 × 5 模糊音强度）
- **召回上限（正确答案在 top-20 内）**: {pct(recall20)}（L1 结构性天花板，spec §6.1）
- **librime 基线首选正确率**: {pct(base_first)}
- **L1 打分后首选正确率**: {pct(l1_first)}
- L2 升级触发: {l2_tried} 条；过校验 {l2_ok}；被校验拦截 {l2_blocked}（其中 T1 可放行 {t1_extra_ok}——T1 开关的增量收益，spec §7）；过校验但错（幻觉代理指标）{validated_wrong}；L2 后正确 {l2_correct}
- L1 延迟: p50={pctl(lat, .5):.0f}ms p95={pctl(lat, .95):.0f}ms（目标 p95<800ms，硬限 1500ms）
- L2 延迟: p50={pctl(l2_lat, .5):.0f}ms p95={pctl(l2_lat, .95):.0f}ms（目标 p95<2s）— {len(l2_lat)} 条
- KV 前缀缓存实测: {kv}

## Gate 决策（逐项填写实测值）
1. L1 相对基线提升 ≥ +15pt（对照召回上限解读，spec §7）：____
2. L1 p95 < 800ms：____（不达标 → 沿延迟-尺寸曲线降档模型）
3. KV 前缀缓存可用性（spec §9 存疑）：____
4. L2 校验拦截率与幻觉率是否可接受：____
5. 结论：进入 Plan 2（Squirrel 集成）是 / 否 / 调整 ____
"""
    (ROOT / "benchmark/report.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/pip install ".[ml]" && .venv/bin/python benchmark/run_bench.py`
Expected: 生成 `benchmark/report.md`，指标全部为实际数值（人检 gate 五项并手填）

- [ ] **Step 3: 写 `benchmark/latency_curve.py` 并跑**

```python
"""延迟-模型尺寸曲线（spec §6.1）：3 模型 × 3 前文长度 × score 单次。
产物 benchmark/latency.csv：model,prefix_chars,ms"""
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from rerank.scorer import MLXScorer  # noqa: E402

MODELS = [
    "mlx-community/Qwen2.5-0.5B-Instruct-4bit",
    "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "mlx-community/Qwen2.5-3B-Instruct-4bit",
]
CAND = "今天天气很好"


def main() -> None:
    rows = []
    for mid in MODELS:
        sc = MLXScorer(mid)
        for n in (50, 100, 200):
            prefix = "这是用于基准测试的前文。" * (n // 12)
            ts = []
            for _ in range(5):
                t0 = time.perf_counter()
                sc.score(prefix, CAND)
                ts.append((time.perf_counter() - t0) * 1000)
            rows.append((mid, n, statistics.median(ts)))
            print(*rows[-1], sep=",")
    with open(ROOT / "benchmark/latency.csv", "w") as f:
        f.write("model,prefix_chars,ms\n")
        for r in rows:
            f.write(f"{r[0]},{r[1]},{r[2]:.1f}\n")


if __name__ == "__main__":
    main()
```

Run: `.venv/bin/python benchmark/latency_curve.py`（首次拉模型，GB 级下载）
Expected: `benchmark/latency.csv` 9 行数据

- [ ] **Step 4: Commit**

```bash
git add benchmark
git commit -m "feat(benchmark): baseline/bench/latency-curve runners + gate report"
```

---

### Task 11: 服务化（HTTP + token + 配置）

**Files:**
- Create: `src/rerank/config.py`、`src/rerank/service.py`、`tests/test_service.py`

**Interfaces:**
- Consumes: `MLXScorer`、`segment_keys`、`validate`、`rank_from_scores`
- Produces: `load_config(path: str | None) -> dict`（默认值 + yaml 合并）；`ensure_token(path: str) -> str`（0600）；`create_app(cfg: dict) -> FastAPI`（`app.state.scorer`/`app.state.decoder` 可注入，测试用）；`POST /rerank`（body：`session_id:str, request_id:int, keys:str, preedit:str, candidates:list[str], context:str="", trust:str="T0"`；响应：`{mode:"L1"|"L2"|"fastpath", best:int|None, confidence:float, order:list[int], l2_text:str|None}`）；`GET /health`

- [ ] **Step 1: 写失败测试 `tests/test_service.py`**

```python
import pytest
from fastapi.testclient import TestClient

from rerank.service import create_app, ensure_token


@pytest.fixture()
def client(tmp_path):
    # create_app 已与 DEFAULTS 合并（无需全量键）；token_file 覆盖到 tmp 避免写真实家目录
    cfg = {"token_file": str(tmp_path / "token"), "min_syllables": 2,
           "l1_conf_threshold": 2.0, "timeout_ms": 1500,
           "model": "unused", "port": 47625,
           "schema": "assets/superpinyin.schema.yaml"}
    app = create_app(cfg)
    app.state.scorer = _FakeScorer()
    app.state.decoder = _FakeDecoder()
    app.state.ready = True        # 阻断 warmup 线程与注入的竞争
    return TestClient(app), ensure_token(cfg["token_file"])


class _FakeScorer:
    def rank(self, prefix, candidates):
        # 模拟：把「风景很美」排第一（librime 首选是别的）
        scores = [10.0 if "风景" in c else 0.0 for c in candidates]
        from rerank.scorer import rank_from_scores
        order, best, conf = rank_from_scores(scores)
        return order, best, conf, scores


class _FakeDecoder:
    def decode(self, context, sylls):
        return "风景很美"


def _hdr(tok):
    return {"X-SuperInput-Protocol": "1", "Authorization": f"Bearer {tok}"}


def test_auth_required(client):
    c, tok = client
    assert c.post("/rerank", json=_body()).status_code == 401
    assert c.get("/health").status_code == 401


def test_protocol_header_checked(client):
    c, tok = client
    r = c.post("/rerank", json=_body(), headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400


def test_min_syllables_fastpath(client):
    c, tok = client
    r = c.post("/rerank", json=_body("jin"), headers=_hdr(tok))
    assert r.status_code == 200 and r.json()["mode"] == "fastpath"


def test_l1_ranking(client):
    c, tok = client
    r = c.post("/rerank", json=_body("fenjinghenmei"), headers=_hdr(tok))
    j = r.json()
    assert j["mode"] == "L1" and "风景" in _cands()[j["best"]]


def _body(keys="fenjinghenmei"):
    return {"session_id": "s1", "request_id": 1, "keys": keys, "preedit": "",
            "candidates": _cands(), "context": "登高望远", "trust": "T0"}


def _cands():
    return ["分静很没", "风景很美", "风景很每"]
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/config.py`**

```python
"""默认配置 + ~/.superinput/rerank.yaml 合并。"""
import copy
import pathlib

import yaml

DEFAULTS = {
    "port": 47625,
    "token_file": str(pathlib.Path.home() / "Library/Application Support/super-input/token"),
    "model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "trust": "T0",
    "min_syllables": 2,
    "l1_conf_threshold": 2.0,
    "timeout_ms": 1500,
    "context_window": 200,
    "debounce_ms": 500,
    "cloud": {"enabled": False, "base_url": "", "model": ""},
    "schema": "assets/superpinyin.schema.yaml",
}


def load_config(path: str | None = None) -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    p = pathlib.Path(path or (pathlib.Path.home() / ".superinput/rerank.yaml"))
    if p.exists():
        user = yaml.safe_load(p.read_text()) or {}
        for k, v in user.items():
            if k == "cloud":
                cfg["cloud"].update(v)
            else:
                cfg[k] = v
    cfg["schema"] = str((pathlib.Path.cwd() / cfg["schema"]).resolve()) \
        if not pathlib.Path(cfg["schema"]).is_absolute() else cfg["schema"]
    return cfg
```

- [ ] **Step 4: 实现 `src/rerank/service.py`**

```python
"""rerank-service：POST /rerank（L1 打分→升级判定→L2+校验）。
守卫元组（过期/焦点/翻页判定）在 Squirrel 侧（Plan 2），本服务无状态。"""
import os
import pathlib
import secrets
import threading

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from .config import load_config


def ensure_token(path: str) -> str:
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if not p.exists():
        p.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        os.chmod(p, 0o600)
    return p.read_text(encoding="utf-8").strip()


class RerankRequest(BaseModel):
    session_id: str
    request_id: int
    keys: str
    preedit: str = ""
    candidates: list[str]
    context: str = ""
    trust: str = "T0"


def create_app(cfg: dict | None = None) -> FastAPI:
    # 部分配置必须与 DEFAULTS 合并（reviewer B3）：测试传 partial cfg 时
    # cfg["schema"]/["context_window"] 等 KeyError
    base = load_config()
    if cfg:
        base.update(cfg)
    cfg = base
    app = FastAPI()
    app.state.cfg = cfg
    app.state.ready = False
    app.state.scorer = None      # 启动后 warmup 填充；测试可注入
    app.state.decoder = None
    app.state.token = ensure_token(cfg["token_file"])
    from .fuzzy import load_fuzzy_classes
    app.state.fuzzy = load_fuzzy_classes(cfg["schema"])   # 单一事实源，CWD 无关

    def _auth(authorization: str, protocol: str) -> None:
        if authorization != f"Bearer {app.state.token}":
            raise HTTPException(401, "bad token")
        if protocol != "1":
            raise HTTPException(400, "protocol version mismatch")

    @app.get("/health")
    def health(authorization: str = Header(""),
               protocol: str = Header("", alias="X-SuperInput-Protocol")):
        _auth(authorization, protocol)
        return {"ready": app.state.ready}

    @app.post("/rerank")
    def rerank(req: RerankRequest, authorization: str = Header(""),
               protocol: str = Header("", alias="X-SuperInput-Protocol")) -> dict:
        _auth(authorization, protocol)
        from .segment import segment_keys
        segs, _frag = segment_keys(req.keys)
        if not segs or len(segs) < cfg["min_syllables"] or not req.candidates:
            return {"mode": "fastpath", "best": None, "confidence": 0.0,
                    "order": list(range(len(req.candidates))), "l2_text": None}
        if app.state.scorer is None:
            return {"mode": "fastpath", "best": None, "confidence": 0.0,
                    "order": list(range(len(req.candidates))), "l2_text": None}
        context = req.context[-cfg["context_window"]:]
        order, best, conf, _scores = app.state.scorer.rank(context, req.candidates[:20])
        mode, l2_text = "L1", None
        if best != 0 and conf < cfg["l1_conf_threshold"] and app.state.decoder is not None:
            try:
                text = app.state.decoder.decode(context, segs)
                from .validator import validate
                if validate(text, req.keys, req.trust, app.state.fuzzy).ok:
                    mode, l2_text = "L2", text
            except Exception:  # noqa: BLE001
                pass  # L2 失败回退 L1（spec §4.3 单一出口）
        return {"mode": mode, "best": best, "confidence": conf,
                "order": order, "l2_text": l2_text}

    def _warmup() -> None:
        from .decode_l2 import LocalDecoder
        from .scorer import MLXScorer

        app.state.scorer = MLXScorer(cfg["model"])
        app.state.decoder = LocalDecoder(cfg["model"])
        app.state.scorer.score("预热前文。", "测试")
        app.state.ready = True

    threading.Thread(target=_warmup, daemon=True).start()
    return app


def _create_prod_app() -> FastAPI:
    """uvicorn 入口（launchd 用）：--factory rerank.service:_create_prod_app。
    测试路径直接调 create_app(cfg)，不走本函数——模块级无副作用
    （reviewer：import 即写 token + 起 warmup 会污染测试与开发机）。"""
    return create_app(load_config())
```

- [ ] **Step 5: 跑测试确认通过** → 4 passed

- [ ] **Step 6: Commit**

```bash
git add src/rerank/config.py src/rerank/service.py tests/test_service.py
git commit -m "feat(rerank): HTTP service with token auth, injectable scorer, L2 fallback"
```

---

### Task 12: 云 BYOK（L2）

**Files:**
- Create: `src/rerank/cloud.py`、`tests/test_cloud.py`

**Interfaces:**
- Consumes: `build_prompt`
- Produces: `CloudError(Exception)`；`CloudDecoder(base_url: str, api_key: str, model: str)`（`.decode(context, sylls) -> str`；429/5xx 指数退避重试 1 次后抛 `CloudError`）；`read_keychain_key() -> str`（`security find-generic-password -s superinput-rerank -w`，找不到抛 `CloudError`）

- [ ] **Step 1: 写失败测试 `tests/test_cloud.py`**

```python
from unittest.mock import patch, MagicMock

import pytest

from rerank.cloud import CloudDecoder, CloudError, read_keychain_key


def test_decode_builds_openai_request():
    dec = CloudDecoder("https://api.example.com/v1", "sk-x", "m1")
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"choices": [{"message": {"content": "风景很美"}}]}
    with patch("rerank.cloud.requests.post", return_value=resp) as p:
        out = dec.decode("前文", ["fen", "jing"])
    assert out == "风景很美"
    body = p.call_args.kwargs["json"]
    assert body["model"] == "m1" and body["messages"][0]["role"] == "system"


def test_retry_once_on_429_then_raise():
    dec = CloudDecoder("https://api.example.com/v1", "sk-x", "m1")
    r = MagicMock(status_code=429)
    with patch("rerank.cloud.requests.post", return_value=r), \
         patch("rerank.cloud.time.sleep"):
        with pytest.raises(CloudError):
            dec.decode("前文", ["fen"])


def test_keychain_missing_raises(monkeypatch):
    class R:
        returncode, stdout, stderr = 44, "", "not found"
    monkeypatch.setattr("rerank.cloud.subprocess.run", lambda *a, **k: R())
    with pytest.raises(CloudError):
        read_keychain_key()
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/cloud.py`**

```python
"""云 BYOK（OpenAI 兼容 /chat/completions，仅 L2——云无 logprob，不用于 L1）。
Key 存钥匙串（spec §3 配置三层第 3 条）。429/5xx 退避重试 1 次（spec §5）。"""
import subprocess
import time

import requests

from .decode_l2 import build_prompt


class CloudError(Exception):
    pass


def read_keychain_key() -> str:
    p = subprocess.run(["security", "find-generic-password",
                        "-s", "superinput-rerank", "-w"],
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        raise CloudError("keychain key not found: security add-generic-password "
                         "-s superinput-rerank -a $USER -w <KEY>")
    return p.stdout.strip()


class CloudDecoder:
    def __init__(self, base_url: str, api_key: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

    def decode(self, context: str, sylls: list[str]) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system",
                 "content": "你是拼音转汉字引擎，只输出对应文字，不要解释。"},
                {"role": "user", "content": build_prompt(context, sylls)},
            ],
            "max_tokens": 256,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in (0, 1):
            try:
                r = requests.post(f"{self.base_url}/chat/completions",
                                  json=payload, headers=headers, timeout=10)
            except requests.RequestException:
                if attempt:
                    raise CloudError("network error") from None
                time.sleep(0.5)
                continue
            if r.status_code == 200:
                try:
                    return r.json()["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError) as e:
                    raise CloudError(f"bad response shape: {e}") from e
            if r.status_code == 429 or r.status_code >= 500:
                if attempt:
                    raise CloudError(f"upstream {r.status_code}") from None
                time.sleep(1.0)
                continue
            raise CloudError(f"upstream {r.status_code}: {r.text[:200]}")
        raise CloudError("unreachable")
```

- [ ] **Step 4: 跑测试确认通过** → 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/rerank/cloud.py tests/test_cloud.py
git commit -m "feat(rerank): cloud BYOK decoder (OpenAI-compatible, L2 only, retry-once)"
```

---

### Task 13: 超时降级策略 + 服务接线

**Files:**
- Create: `src/rerank/policy.py`、`tests/test_policy.py`；Modify: `src/rerank/service.py`（在 L2 分支接入 policy）

**Interfaces:**
- Consumes: 无
- Produces: `TimeoutWindow(span: int = 5, threshold: int = 3, ttl_s: int = 600)`（`.record(session_id, timed_out: bool)`、`.should_downgrade(session_id) -> bool`、内部 TTL：同一 session 超过 ttl 未活动则重置窗口）

- [ ] **Step 1: 写失败测试 `tests/test_policy.py`**

```python
from rerank.policy import TimeoutWindow


def test_three_of_five_triggers_downgrade():
    w = TimeoutWindow()
    for _ in range(3):
        w.record("s1", True)
    assert w.should_downgrade("s1") is True


def test_two_does_not():
    w = TimeoutWindow()
    w.record("s1", True)
    w.record("s1", True)
    assert w.should_downgrade("s1") is False


def test_ttl_resets_window(monkeypatch):
    w = TimeoutWindow(ttl_s=600)
    w.record("s1", True)
    monkeypatch.setattr("rerank.policy.time.time", lambda: w._now("s1") + 601)
    assert w.should_downgrade("s1") is False
```

- [ ] **Step 2: 跑测试确认失败** → FAIL

- [ ] **Step 3: 实现 `src/rerank/policy.py`**

```python
"""超时滑动窗口降级（spec §5）：5 次窗口内 3 次超硬限 → 该会话 L2 走云。
触发器是可测的超时率，不是小模型自报置信度。"""
import time
from collections import deque


class TimeoutWindow:
    def __init__(self, span: int = 5, threshold: int = 3, ttl_s: int = 600):
        self.span = span
        self.threshold = threshold
        self.ttl_s = ttl_s
        self._win: dict[str, deque] = {}
        self._ts: dict[str, float] = {}

    def _now(self, session_id: str) -> float:
        return self._ts.get(session_id, 0.0)

    def record(self, session_id: str, timed_out: bool) -> None:
        now = time.time()
        if now - self._ts.get(session_id, now) > self.ttl_s:
            self._win.pop(session_id, None)
        self._ts[session_id] = now
        w = self._win.setdefault(session_id, deque(maxlen=self.span))
        w.append(timed_out)

    def should_downgrade(self, session_id: str) -> bool:
        w = self._win.get(session_id)
        return bool(w) and sum(w) >= self.threshold
```

- [ ] **Step 4: 跑测试确认通过** → 3 passed

- [ ] **Step 5: 服务接线（Modify `src/rerank/service.py`）**

在 `create_app` 内 `app.state.cfg = cfg` 之后加：

```python
    from .policy import TimeoutWindow
    app.state.policy = TimeoutWindow()
```

在 `rerank` 端点 L2 分支（`if best != 0 and conf < ...`）把解码选择整体替换为：

```python
        if best != 0 and conf < cfg["l1_conf_threshold"] and app.state.decoder is not None:
            import concurrent.futures as cf
            timed_out = False
            text = ""
            try:
                if (cfg["cloud"].get("enabled")
                        and app.state.policy.should_downgrade(req.session_id)):
                    from .cloud import CloudDecoder, CloudError, read_keychain_key
                    try:
                        text = CloudDecoder(cfg["cloud"]["base_url"], read_keychain_key(),
                                            cfg["cloud"]["model"]).decode(context, segs)
                    except CloudError:
                        text = ""          # 云失败回退本地（spec §5）
                if not text:
                    with cf.ThreadPoolExecutor(max_workers=1) as ex:
                        fut = ex.submit(app.state.decoder.decode, context, segs)
                        try:
                            text = fut.result(timeout=cfg["timeout_ms"] / 1000)
                        except cf.TimeoutError:
                            timed_out = True
                            text = ""
            except Exception:  # noqa: BLE001
                text = ""                  # 单一出口：任何失败回退 L1（spec §4.3）
            # 只记录真超时（spec §5 触发器=超时率）：云失败回退本地/本地解码失败
            # 不计超时——否则云故障期会误积累记录、触发「降级到云」死循环。
            # 注意：降级到云后无回升回路（spec §5「本会话降云」是有意设计）。
            app.state.policy.record(req.session_id, timed_out)
            if text:
                from .validator import validate
                if validate(text, req.keys, req.trust, app.state.fuzzy).ok:
                    mode, l2_text = "L2", text
```

（MLX 推理无法安全强杀，超时=放弃本次结果、线程自行结束——本地可接受）

- [ ] **Step 6: 跑全部测试确认无回归**

Run: `.venv/bin/pytest -v` → 全部 passed

- [ ] **Step 7: Commit**

```bash
git add src/rerank/policy.py src/rerank/service.py tests/test_policy.py
git commit -m "feat(rerank): timeout sliding-window downgrade policy wired into service"
```

---

### Task 14: launchd 部署与端到端冒烟

**Files:**
- Create: `deploy/com.superinput.rerank.plist`、`scripts/smoke.sh`

**Interfaces:**
- Consumes: `rerank.service:app`（uvicorn 入口）
- Produces: 常驻服务（launchd RunAtLoad + KeepAlive）；冒烟脚本（token→/health→/rerank 断言）

- [ ] **Step 1: 写 `deploy/com.superinput.rerank.plist`**（`<ROOT>` 为仓库绝对路径占位，安装时替换）

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.superinput.rerank</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/lijianhua04/Documents/IdeaProject/super-input/.venv/bin/uvicorn</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>47625</string>
    <string>--factory</string><string>rerank.service:_create_prod_app</string>
  </array>
  <key>WorkingDirectory</key>
    <string>/Users/lijianhua04/Documents/IdeaProject/super-input</string>
  <key>EnvironmentVariables</key>
  <dict><key>PYTHONPATH</key><string>/Users/lijianhua04/Documents/IdeaProject/super-input/src</string></dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/superinput-rerank.log</string>
  <key>StandardErrorPath</key><string>/tmp/superinput-rerank.err</string>
</dict>
</plist>
```

- [ ] **Step 2: 安装并启动**

```bash
mkdir -p ~/Library/LaunchAgents
cp deploy/com.superinput.rerank.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.superinput.rerank.plist
```

Expected: 无输出（成功）；`/tmp/superinput-rerank.log` 出现 uvicorn 启动行

- [ ] **Step 3: 写 `scripts/smoke.sh` 并执行**

```bash
#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN=$(cat "$HOME/Library/Application Support/super-input/token")
H=(-H "X-SuperInput-Protocol: 1" -H "Authorization: Bearer $TOKEN")

for i in $(seq 1 60); do
  READY=$(curl -s "${H[@]}" http://127.0.0.1:47625/health | grep -o '"ready":[a-z]*' || true)
  [ "$READY" = '"ready":true' ] && break
  sleep 5
done
[ "$READY" = '"ready":true' ] || { echo "service never became ready"; exit 1; }

BODY='{"session_id":"smoke","request_id":1,"keys":"fenjinghenmei","preedit":"",
       "candidates":["分静很没","风景很美","风景很每"],"context":"登高望远","trust":"T0"}'
curl -s "${H[@]}" -H 'Content-Type: application/json' \
  -d "$BODY" http://127.0.0.1:47625/rerank | tee /tmp/smoke.json
grep -q '"mode"' /tmp/smoke.json && echo && echo SMOKE_OK
```

Run: `chmod +x scripts/smoke.sh && ./scripts/smoke.sh`
Expected: 末行 `SMOKE_OK`（ready 等待期 = 模型 warmup，首次数十秒）

- [ ] **Step 4: Commit**

```bash
git add deploy scripts
git commit -m "feat(deploy): launchd plist + end-to-end smoke test"
```

---

## Gate：本计划的终点 = Plan 2 的输入

`benchmark/report.md`（Task 10 产出）必须回答五项，才进入 Plan 2（Squirrel fork 集成：选择键拦截/守卫元组/防抖/IPC 客户端/前文 commit 缓冲，对应 spec §4.3 全部 Squirrel 侧条款）：

1. L1 相对基线提升是否 ≥ +15pt（对照召回上限解读）
2. L1 p95 是否 <800ms；不达标时沿 `latency.csv` 曲线选档
3. KV 前缀缓存可用性（`probe_prefix_cache` 实测——不可用则 L1 保持全量 prefill，延迟预算按实测重估）
4. L2 校验拦截率/幻觉率是否可接受
5. RimeMenu 分页常量与 Squirrel commit 回调文本读取（Task 7 中顺带记录 `page_size` 实际生效值；Squirrel 源码阅读在 Plan 2 Task 1 完成）

任一项不达标 → 回到 spec §2 调整（降模型档/调阈值/放弃 L2），不进 Plan 2。
