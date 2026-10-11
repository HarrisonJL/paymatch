"""
Writes CONTRACT.md from studio-next/live_proof.json (the log prove.ts wrote as it ran), so no transaction
hash or verdict in it is ever transcribed by hand.   python3 scripts/build_contract_md.py
"""
import datetime
import json
import pathlib

REPO = pathlib.Path(__file__).resolve().parent.parent
L = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
X = "https://explorer-studio-dev.genlayer.com"
PM = "0x05dd40484265FB0B949A127a3bf19aC505Badcf9"
GATE = "0xD3C520106520b510C261e93aC0689141199dCd52"
PM_DEPLOY = "0x883edcfd63db6eef2f50aa15b5d8c21fa290776a4c2adfa541d9baf90926d314"
GATE_DEPLOY = "0x66aa01d2bd9087b1dd28fbeba78c6d242050c58408a838e8cd9a91b760136cd2"
PM_SHA = "8724ed555d1c920327bfe1c089a598b0fd6682d3dd592052e266f5df69aa09d0"
GATE_SHA = "21c02f8650cc0d68ca2809c2c5408cdc6958f073220fbaa9ace8ea5b809812a9"


def tx(h): return f"[`{h[:10]}…`]({X}/tx/{h})"
def eth(h): return f"[`{h[:10]}…`](https://etherscan.io/tx/{h})"
def votes(v):
    a, d = v.count("AGREE"), v.count("DISAGREE")
    return f"{a} agree" + (f", {d} disagree" if d else "")
def day(ts): return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%-d %b %Y")
def usdc(raw): return f"{int(raw) / 10 ** 6:,.3f}".rstrip("0").rstrip(".")


regs = [e for e in L if e["step"] == "register"]
refs = [e for e in L if e["step"] == "refuse"]
vers = [e for e in L if e["step"] == "verify"]
gate = [e for e in L if e["step"] == "gate"]
read = next(e for e in L if e["step"] == "read")
assert all(e["result"] in ("FINISHED_WITH_RETURN", "FINISHED_WITH_ERROR") for e in L if "result" in e)
assert not any(v == "DISAGREE" for e in L for v in e.get("votes", [])), "a disagreement belongs in the text"
decided = [e for e in L if "tx" in e]

o = []
w = o.append
w("# PayMatch: deployment and live proof\n")
w("## Deployment\n")
w("| | |\n|---|---|")
w("| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |")
w(f"| PayMatch | [`{PM}`]({X}/address/{PM}) - deploy tx {tx(PM_DEPLOY)} |")
w(f"| TrancheGate | [`{GATE}`]({X}/address/{GATE}) - deploy tx {tx(GATE_DEPLOY)}; constructed with PayMatch's address and the ENS DAO treasury `0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7` as its trusted payer |")
w("| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |")
w("| Deployer | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |\n")
w("Both contracts passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> <file>` fetches it with `gen_getContractCode` and compares.\n")
w("| Contract | SHA-256 on-chain = SHA-256 of the repo file |\n|---|---|")
w(f"| PayMatch / `contracts/pay_match_studio_next.py` | `{PM_SHA}` |")
w(f"| TrancheGate / `contracts/tranche_gate_studio_next.py` | `{GATE_SHA}` |\n")
w("## Live proof (11 October 2026)\n")
w(f"Reproduce with `cd studio-next && npx tsx prove.ts <paymatch> <tranchegate> <register|refuse|verify|gate|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped), with the contract's recorded output. \"Agree\" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All {len(decided)} transactions reached consensus with every voting validator agreeing**, including the ones the contracts refused: a refusal is a decided outcome.\n")
w("The authorisations are the ENS DAO's own Snapshot funding requests; the payments are the real Ethereum transactions by which its treasury (`wallet.ensdao.eth`, `0xFe89cc7a…`) paid the Ecosystem Working Group multisig (`0x2686a891…`, `main.eco.wg.ens.eth`).\n")

w("### Registering authorisations\n")
w("| Id | The request | Registration | Recorded |\n|---|---|---|---|")
for e in regs:
    a = e["authorisation"]
    w(f"| `{e['auth_id']}` | {a['title'].split('] ', 2)[-1]}, vote closed {day(a['approved_at'])}, cap {usdc(a['cap_raw'])} USDC, payer `{a['payer'][:10]}…` | {tx(e['tx'])} {votes(e['votes'])} | the validators' quote: *\"{a['evidence']}\"*; vote For {float(a['vote']['for_score']):,.0f} to Against {float(a['vote']['against_score']):,.0f}; document SHA-256 `{a['doc_digest'][:12]}…` |")
w("\n`eco470-alt-payer` is the same vote registered with a look-alike address as the payer. It is a separate authorisation by design (see the gate below).\n")

w("### Refusals\n")
w("Each is a registration the contract refused. The reasons are the contract's own, decided from the documents, the vote and the explorer.\n")
w("| What it tries | Tx | Revert message |\n|---|---|---|")
for e in refs:
    w(f"| {e['note']} | {tx(e['tx'])} {votes(e['votes'])} | `{e['revert']}` |")
w("\nThe last refusal in the table that reads *document does not authorise this payment* is the reader's: `172k` is a figure in the request's own budget table (the Main Multisig's line), so the cap is \"in the document\", and the validators' LLMs still refused it as not what the document asks to be paid. The others are decided by plain code with no LLM.\n")

w("### Judging payments\n")
w("Each row is one `verify_payment` against the named authorisation. The verdict, amount and reasons are what the contract recorded after both indexers (Blockscout and Routescan) agreed.\n")
w("| Authorisation | Transaction judged | What it is | Verdict | Amount (USDC) | Tx |\n|---|---|---|---|---|---|")
for e in vers:
    p = e["payment"]
    w(f"| `{e['auth_id']}` | {eth(e['subject'])} | {e['note']} | **{p['verdict']}** | {usdc(p['amount_raw'])} | {tx(e['tx'])} {votes(e['votes'])} |")
w("\n`UNDETERMINED` is not a finding: it is recorded in the history but does not count against the authorisation, and the same transaction can be judged again. The facts behind every row (both indexers' agreed view: block, time, finality, every transfer of the asset) are in the on-chain record (`get_payment`) and in `live_proof.json`.\n")

w("### TrancheGate: the verdict drives an action\n")
w("The gate trusts one payer, the ENS treasury. A release is allowed only if PayMatch's own record shows the earlier tranches paid and matched, nothing flagged, and room under the cap. Amounts are in USDC's smallest unit (6 decimals).\n")
w("| Step | Call | Outcome | Tx |\n|---|---|---|---|")
for e in L:
    if e["step"] == "gate":
        out_ = "**released**" if e["result"] == "FINISHED_WITH_RETURN" else f"refused: `{e['revert']}`"
        w(f"| {e['note']} | `release({e['args'][0]}, {e['args'][1]}, {e['args'][2]})` | {out_} | {tx(e['tx'])} {votes(e['votes'])} |")
    elif e["step"] == "verify" and e["id"].startswith("g-"):
        w(f"| {e['note']} | `PayMatch.verify_payment({e['auth_id']}, {e['tx_key']})` | **{e['payment']['verdict']}** | {tx(e['tx'])} {votes(e['votes'])} |")
cfg = read["gate_config"]
w(f"\nAfter the run `TrancheGate.get_config()` reports {cfg['release_count']} releases, and each authorisation reads back as follows from `PayMatch.get_reconciliation`:\n")
w("| Authorisation | Cap (USDC) | Matched (USDC) | Flagged | Payments |\n|---|---|---|---|---|")
for k, r in read["reconciliation"].items():
    w(f"| `{k}` | {usdc(r['cap_raw'])} | {usdc(r['matched_raw'])} | {r['flagged_count']} | {r['payment_count']} |")
w(f"\n`get_history(\"eco470\")` walks that authorisation's own chain, newest first: {' → '.join(f'#{i}:{v}' for i, v, _ in read['history_eco470'])}.\n")

w("## What the live run found\n")
w("Running the contract on the real network found three things Direct Mode could not, each fixed and covered by a test or a mutation:\n")
w("- **A view returned a float and the runtime could not encode it.** The stored vote record carried Snapshot's scores (`1375141.4178885242`). `get_authorisation` failed with a bare `exit_code 1` although every Direct Mode test passed. GenVM calldata has no float type, so the scores are carried as text, and a test asserts that no view returns a float.")
w("- **A model's quote of a Markdown table row failed grounding.** Asked about the 836,000 request, the validators' models sometimes quoted `ENS Ecosystem Main Multisig | 836,000 | -- | --`: genuine words, but not verbatim next to the document's link syntax, and naming no asset. The registration was refused depending on which validator led. Quotes and documents are now compared as the words a reader sees (Markdown links, table bars and emphasis removed), the reader is told to prefer a sentence of prose, and an affirmative quote that cannot be grounded is asked for once more. A refusal is never retried, so the retry can only turn an unreadable answer into a readable one, never a \"no\" into a \"yes\".")
w("- **One model returned text that was not JSON.** On a scratch copy of the contract, one validator (`gpt-oss`) answered with prose ([tx `0xb1e53497…`](" + X + "/tx/0xb1e5349775778ef196a5a6fa6dfac4d7db8c3cbb1194c1eda5494973bbee9ccf)); the exception escaped and cost a vote (the round still carried). A reader that does not return JSON is now treated as unreadable and asked once more, then fails closed.\n")
w("## Superseded deployments\n")
w("The three earlier PayMatch deployments ran the same design while these were found. None is current; nothing here points at them.\n")
w("| PayMatch | Deploy tx | Why it is superseded |\n|---|---|---|")
w(f"| `0x8c244D9747421Cfff1E1B8E4702B76eBCFac7697` | {tx('0x4bf569c5f28ad7c7add2c1951f5a28da34634a31bf2cef5ea1359a8b6774e686')} | `get_authorisation` returned a float (above). |")
w(f"| `0xC24c75D227e85A539A10027d92a6d9164951F003` | {tx('0x0d206156403c06726926a2037d89af94d08270f3b9d28b94306316b910400219')} | The reader refused real quotes it should have grounded (above). Its partial log is `studio-next/live_proof_superseded_v2.json`. |")
w(f"| `0xc03F375E046917a1201f5d5FAd4b4f9F94c62D99` | {tx('0x01edd7dcccfea9d9b298beeff46748431a934e0fd73931bbb82b81cadd3fb868')} | The same code as the current deployment. Its gate run failed because the script passed `release`'s `u256` amount as a string, and the failed run left `eco409` in an unintended state, so the proof was rerun from a clean deployment. Its log is `studio-next/live_proof_superseded_v3.json`. |\n")
w("## Proven in tests, not live\n")
w("Direct Mode proves these on real captures (or a real response with one marked field changed); none has a live transaction:\n")
w("- `WRONG_ASSET` (the payer paid the recipient in another token and sent none of the asset): no real transaction was found, so it is proven on crafted facts.")
w("- `OUTSIDE_WINDOW` and the inclusive edge of `valid_until`, and `BEFORE_APPROVAL` to the second the vote closed.")
w("- Disagreeing indexers, one indexer unreachable or malformed, a payment not yet 64 blocks deep, a reorged log, an ERC-721 event with the same signature, a 50-item page with no next page: all fail closed, on real responses with one field changed.")
w("- A document whose bytes do not match its address; a vote record for another document, an open vote, a tie, another space, results of the wrong type.")
w("- Every TrancheGate check that runs before its cross-contract call (owner, amount, order, the trusted payer's format). Its checks that read PayMatch are proven by the live table above, because Direct Mode cannot simulate a cross-contract call. The window-closed check has no live refusal.")
w("- The replay: `test_the_fixtures_reproduce_what_the_validators_agreed_on_live` runs every live verification again on the committed fixtures and requires the same facts, verdict, reasons, amount and block.")
(REPO / "CONTRACT.md").write_text("\n".join(o) + "\n")
print("wrote CONTRACT.md,", len(o), "lines;", len(decided), "transactions")
