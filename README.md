# PayMatch

**Was this payment actually authorised?** A GenLayer Intelligent Contract that does, on-chain and with no oracle, the control accountants call a *three-way match*: an approval, a payment, and a verdict that a committee of validators reached independently. An authorisation is a DAO funding request that passed a Snapshot vote; a payment is an Ethereum transaction; the verdict is `MATCH` only if the authorised **payer** sent the authorised **asset** to the authorised **recipient**, after the vote closed, inside the window, with the running total within the cap. Anything else is a named mismatch (`OVER_CAP`, `BEFORE_APPROVAL`, `WRONG_PAYER`, `WRONG_RECIPIENT`, …), and anything unreadable is `UNDETERMINED`, never a match.

| | |
|---|---|
| Network | GenLayer Studio Next (chain 61997) |
| PayMatch | [`0x05dd40484265FB0B949A127a3bf19aC505Badcf9`](https://explorer-studio-dev.genlayer.com/address/0x05dd40484265FB0B949A127a3bf19aC505Badcf9) |
| TrancheGate (consumer) | [`0xD3C520106520b510C261e93aC0689141199dCd52`](https://explorer-studio-dev.genlayer.com/address/0xD3C520106520b510C261e93aC0689141199dCd52) |
| Live proof | [CONTRACT.md](CONTRACT.md): the ENS DAO's real funding requests and the real payments that settled them, every verdict path, every transaction linked |
| Tests | 157 Direct Mode tests (147 PayMatch, 10 TrancheGate) on real Snapshot documents and real Ethereum transactions; 119/119 safety mutations killed |

## Why this exists

A DAO or foundation treasury approves a payment in one place (a forum post, a Snapshot vote) and makes it in another (a multisig on Ethereum). The two are linked only by whoever executes. The control that closes the gap is old: match what was authorised to what was paid, and say so when they differ. Smart contracts can't do it, because the approval is text on the web and the payment is history on another chain; both are things a deterministic contract cannot read.

The real record shows why a naive check fails. The ENS DAO approved a **470,000 USDC** request for its Ecosystem Working Group by vote (closed 10 November 2025), and its treasury paid exactly that on 18 February 2026, in one transaction that also paid two other groups. The same recipient address also receives a steady stream of **address-poisoning dust**: 0.001 USDC from look-alike senders, some as 50-transfer batches, all real USDC at the real address. "Did the recipient receive USDC?" is true of all of them. PayMatch asks the right questions and shows its working.

## How it decides

### 1. An authorisation is a passed vote about a named document

`register_authorisation` takes the Snapshot proposal's id, its IPFS address, the recipient, the **payer** (the treasury that must send the funds), the asset and a cap. Validators check, in plain code:

- **The document is what its address says.** A raw-codec CID (`bafkrei…`) *is* the SHA-256 of the document, so the contract hashes the bytes the gateway returned and compares them with the address. The gateway is not trusted at all.
- **The vote is for that document.** The Snapshot hub's record of the proposal must name the same IPFS address, be in the same space, be `closed`, and have a strict majority For over Against. (Votes with other shapes, such as options A/B/C, are refused.)
- **The asset is canonical.** The registrant names a symbol; the contract supplies the address from a pinned list (USDC, USDT, DAI, EURC, WETH, ENS, UNI) and checks the explorer's token record agrees. A look-alike token with the same symbol can never be authorised.
- **The document says it.** The recipient's address, the cap (as written: `470,000`, `42k`, `1.5M`) and the asset's symbol must all appear in the document's text.

Only then does an LLM read the document, and it can only **refuse**. It must say the document really requests *this* payment (not a past period, not a line in a budget table, not another recipient), and it must quote the decisive words. Every fragment of the quote must be found in the document (compared as the words a reader sees, with Markdown links and table bars removed), and the quote itself must state the amount and name the asset, so it cannot cite unrelated text. An unreadable or ungrounded answer is asked for once more, then fails closed. A "no" is never asked again.

Registration is permissionless and immutable. One vote authorises one payer-recipient-asset once, so a cap cannot be counted twice under two ids.

### 2. A payment is judged by chain facts only

`verify_payment(auth_id, tx_hash)` reads the transaction from **two independent indexers**, Blockscout and Routescan. They must agree on whether it exists, its status, its block and time, that it is final (64 blocks on top), and every transfer of the authorised asset. No LLM is involved. The verdict is a pure function of those facts and the authorisation's own running total:

| Verdict | Meaning |
|---|---|
| `MATCH` | The authorised payer sent the authorised asset to the authorised recipient, after the vote closed, inside `valid_until`, and the running total stays within the cap. |
| `OVER_CAP` | A proper payment that would take the total past the cap. Recorded and flagged, not counted as paid. |
| `BEFORE_APPROVAL` | Paid before the vote closed. |
| `OUTSIDE_WINDOW` | Paid after the registrant's `valid_until`. |
| `WRONG_PAYER` | The recipient received the asset, but not from the authorised payer (this is what dust from a look-alike address is). |
| `WRONG_RECIPIENT` | The payer sent the asset, but not to the authorised recipient. |
| `WRONG_ASSET` | The payer paid the recipient in a different token. |
| `NO_TRANSFER` | The authorised payer sent none of the asset in this transaction. |
| `TX_FAILED` | The transaction reverted. |
| `UNDETERMINED` | Not found, not final yet, an indexer unreadable, the two indexers disagree, or more transfers than an indexer lists in a page (50). Never a match, and can be retried. |

Every decided verdict is recorded against the authorisation, so a mismatch is an on-chain alert feed. A transaction already decided for an authorisation cannot be verified again there.

### 3. Fail closed

An unreadable document, vote or token record; an authorisation whose document does not say what is claimed; a transaction that is too new, too large to list, or reported differently by the two indexers: each ends in a refusal or `UNDETERMINED`, never a positive. **The verdict is recomputed from the agreed facts, never taken from the leader.**

## Equivalence principle

A custom leader/validator pair (`gl.vm.run_nondet`) for each write:

- **Registration:** exact agreement on everything plain code derives: the document's hash, the vote record, the token record, and what the document is found to say. On the reading, agreement on the decision a consumer acts on (accepted or refused), plus: the leader's quote must be in each validator's own copy of the document, and a reading of a document the facts already refuse is rejected.
- **Verification:** exact agreement on the facts both indexers give. Because the verdict is a pure function of those facts and the authorisation's state, agreeing on the facts is agreeing on the verdict.

The consensus-boundary tests (`tests/test_pay_match.py`, section 5) show validators rejecting: tampered vote or document facts, a quote not in the validator's copy, a leader that hides or flips the reading, a reading of nothing, malformed readings, altered transfers, success flags, times and finality, and a leader that sent no facts.

## TrancheGate: the verdict drives an action

`TrancheGate` ([`contracts/tranche_gate.py`](contracts/tranche_gate.py)) is a minimal consumer, proven live. Its owner releases a grant's tranches in order, and a tranche is released only if, in PayMatch's own record of the authorisation:

- the authorisation names **the one treasury this gate trusts** as payer (PayMatch's payer is the registrant's claim, so the consumer pins it);
- nothing paid against it has been flagged;
- every tranche already released has really been paid and matched on-chain;
- the authorisation's window has not closed; and
- the tranche fits what is left of the authorised cap.

It reads PayMatch through a cross-contract view. It moves no funds: it shows the gate, not a payments system.

## What this proves, and what it doesn't

| It proves | It does not prove |
|---|---|
| A document that hashes to its own IPFS address was the subject of a closed Snapshot vote that carried by weighted majority | That the vote was **wise or legitimate**: Snapshot quorum rules and who could vote are not checked |
| The document names this recipient, this cap and this asset, and a committee of validators agreed it requests exactly this payment | That the document is **the only authority**: a DAO may need an on-chain execution too |
| Two independent indexers agree what a transaction transferred, in which asset, from whom and to whom, and when | That the indexers are right. They are two sources, not the chain itself |
| The running total of verified payments against the cap, and every payment that did not match | That **no other payment** was made: only transactions someone submitted are judged |
| | That the **payer is the right treasury**. The payer is the registrant's claim; a consumer must pin the address it trusts |

## Known limitations

- **Ethereum mainnet only.** Base's Blockscout answers Studio Next's validators with a Cloudflare challenge, and a payment is only trusted when two indexers can be read. Other chains need two readable indexers each.
- **Snapshot-approved authorisations only**, with a binary For/Against vote. A payment approved some other way (an on-chain governor, a multisig decision, a signed letter) has no adapter.
- **The payer is a claim.** The ENS Snapshot space declares no treasury, so nothing in the vote names the payer. Someone can register the same vote with a different payer; that is a separate authorisation, and a consumer that pins its payer ignores it (shown live: the look-alike dust sender "matches" its own dust under `eco470-alt-payer`, and TrancheGate refuses it).
- **A pinned list of assets** (seven ERC-20s). Another token needs a contract change.
- **Transactions with more than 50 token transfers are `UNDETERMINED`** (an indexer lists 50 a page). A real 50-transfer poisoning batch is in the live proof.
- **A transaction counts toward every authorisation it is verified against.** Two requests to the same recipient from the same payer share payments if both are registered; register one authorisation per request and verify against the right one.
- **Amounts in a document are read as written** (`470,000`, `42k`, `1.5M`); a figure written in words is not read.
- **The hub and the IPFS gateway are services.** A closed vote's record is final, and the document is checked against its own hash, but the hub being down means no new registrations.
- **The reader is an LLM.** It can only refuse, and its quote is checked word for word, but a model can still miss an authorisation that is there (a refusal is retryable by re-registering under a new id).
- **Ids are first-come and immutable.** Someone can register an `auth_id` before you; read the immutable record (`get_authorisation`) and pin what you expect. `TrancheGate` is owner-only and demonstrates a consumer.
- **Studio Next only.** The earlier deployments of this contract are superseded (CONTRACT.md).

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install genlayer-test==0.29.2 genvm-linter==0.11.0 pytest
.venv/bin/pytest tests -q                     # 157 tests
.venv/bin/genvm-lint check contracts/pay_match.py
python3 scripts/mutation_check.py             # every safety mutation must be killed
python3 scripts/capture_fixtures.py           # re-capture the real fixtures

cd studio-next && npm ci
npx tsx check_schema.ts pay_match_studio_next.py
npx tsx verify_code.ts <address> pay_match_studio_next.py    # on-chain code == this repo
```

## Repository layout

```
contracts/pay_match.py                  tested source (GenVM v0.2.11)
contracts/pay_match_studio_next.py      deployed port (Studio Next)
contracts/tranche_gate*.py              consumer contract + port
tests/                                  Direct Mode tests, real fixtures, mutations*.txt
scripts/                                fixture capture, port, mutation check
studio-next/                            deploy, schema check, live proof (prove.ts, live_proof.json), verify_code.ts
research/                               what GenVM can read from each source, and the probe contract
```
