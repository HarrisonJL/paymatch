"""
Mutation check: proves each safety property is actually pinned by a test.

tests/mutations.txt (PayMatch) and tests/mutations_tranche_gate.txt list
deliberate breakages of the contracts - each one removes or weakens exactly
one safety property (the document hash check, the vote binding, the pinned
token record, quote grounding, the payer, the cap, the two-indexer
agreement, fail-closed fetches, the validators' comparisons, ...). For every
mutation this script patches the contract, runs the full test suite, and
restores the original. A mutation the suite still passes is a safety property
no test protects; the script exits non-zero if any survive.

TrancheGate's mutations cover the checks that run before its cross-contract call
to PayMatch (owner, amount, tranche order, the trusted payer's format). Direct Mode
cannot simulate a cross-contract call, so the checks that read PayMatch (payer,
flagged payments, earlier tranches paid, cap, window, existence) are proven live
instead: see CONTRACT.md.

Format of each mutations file: blocks separated by a line "===", each
    <name>
    ---
    <exact original text>
    ---
    <replacement text>

The suite runs in its own process group with a timeout, and the contract is
restored however the script ends (including SIGTERM).

Usage (from the repo root):  python3 scripts/mutation_check.py [pay_match|tranche_gate]
"""

import os
import pathlib
import signal
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
PYTEST = REPO / ".venv" / "bin" / "pytest"
TARGETS = {
    "pay_match": (REPO / "contracts" / "pay_match.py", REPO / "tests" / "mutations.txt"),
    "tranche_gate": (REPO / "contracts" / "tranche_gate.py", REPO / "tests" / "mutations_tranche_gate.txt"),
}
TIMEOUT = 120


def run_suite() -> bool:
    """True if the suite fails (the mutation was killed)."""
    proc = subprocess.Popen([str(PYTEST), "tests", "-q", "-x", "-p", "no:cacheprovider"], cwd=REPO,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        return proc.wait(timeout=TIMEOUT) != 0
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        return True  # a mutation that hangs the suite is caught too


def check(contract: pathlib.Path, mutations_file: pathlib.Path) -> int:
    original = contract.read_text()

    def restore(*_):
        contract.write_text(original)
        sys.exit(1)

    signal.signal(signal.SIGTERM, restore)
    mutations = []
    for block in mutations_file.read_text().split("\n===\n"):
        name, old, new = block.split("\n---\n")
        assert old in original, f"mutation target not found in {contract.name}: {name.strip()}"
        mutations.append((name.strip(), old, new))

    survivors = []
    try:
        for name, old, new in mutations:
            contract.write_text(original.replace(old, new, 1))
            killed = run_suite()
            print(("KILLED    " if killed else "SURVIVED  ") + name, flush=True)
            if not killed:
                survivors.append(name)
    finally:
        contract.write_text(original)
    print(f"\n{contract.name}: {len(mutations) - len(survivors)}/{len(mutations)} mutations killed")
    return 1 if survivors else 0


def main() -> int:
    chosen = sys.argv[1:] or list(TARGETS)
    return max(check(*TARGETS[name]) for name in chosen)


if __name__ == "__main__":
    sys.exit(main())
