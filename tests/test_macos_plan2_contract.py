from pathlib import Path
import os


ROOT = Path(__file__).resolve().parents[1]
PATCH = (ROOT / "macos/patches/squirrel-integration.patch").read_text(encoding="utf-8")
BUILD = (ROOT / "macos/build-squirrel.sh").read_text(encoding="utf-8")
BRIDGE_TEST = ROOT / "macos/test-bridge-contract.sh"
BRIDGE_CONTRACT = (ROOT / "macos/tests/SuperInputClientContractTests.swift").read_text(encoding="utf-8")


def test_imk_history_is_bound_to_client_identity_and_empty_context_can_rerank():
    assert "+  private var superInputHistoryClientID: ObjectIdentifier?" in PATCH
    assert "+        resetSuperInputHistory(for: senderID)" in PATCH
    assert "+          superInputHistoryClientID == clientID else { return }" in PATCH
    assert "+      context: superInputHistory," in PATCH
    assert "!superInputHistory.isEmpty" not in PATCH
    assert 'context: ""' in BRIDGE_CONTRACT
    assert 'firstObject?["context"] as? String == ""' in BRIDGE_CONTRACT


def test_client_switch_cancels_and_invalidates_old_response():
    assert "+        invalidateSuperInput(clearApplied: true)" in PATCH
    assert "+    superInputTask?.cancel()" in PATCH
    assert "+    superInputPending = nil" in PATCH
    assert "+          superInputClientID == snapshot.clientID," in PATCH
    assert "+          ObjectIdentifier(activeClient as AnyObject) == snapshot.clientID," in PATCH


def test_pkg_build_removes_old_targets_before_invoking_make():
    clean = 'rm -f "$UPSTREAM_DIR/package/Squirrel.pkg" "$OUTPUT_DIR/SuperInput-Squirrel.pkg"'
    assert clean in BUILD
    assert BUILD.index(clean) < BUILD.index("make package")
    assert "test -s \"$UPSTREAM_DIR/package/Squirrel.pkg\"" in BUILD


def test_readme_bridge_test_is_directly_executable_and_explains_missing_swiftc():
    assert os.access(BRIDGE_TEST, os.X_OK)
    script = BRIDGE_TEST.read_text(encoding="utf-8")
    assert 'command -v swiftc' in script
    assert "Xcode Command Line Tools" in script
    assert '$(uname -s)' in script
