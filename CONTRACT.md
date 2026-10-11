# PayMatch: deployment and live proof

## Deployment

| | |
|---|---|
| Network | GenLayer Studio Next, chain 61997 (`chains.studioDevnet`, genlayer-js 2.0.0-rc.1) |
| PayMatch | [`0x05dd40484265FB0B949A127a3bf19aC505Badcf9`](https://explorer-studio-dev.genlayer.com/address/0x05dd40484265FB0B949A127a3bf19aC505Badcf9) - deploy tx [`0x883edcfd…`](https://explorer-studio-dev.genlayer.com/tx/0x883edcfd63db6eef2f50aa15b5d8c21fa290776a4c2adfa541d9baf90926d314) |
| TrancheGate | [`0xD3C520106520b510C261e93aC0689141199dCd52`](https://explorer-studio-dev.genlayer.com/address/0xD3C520106520b510C261e93aC0689141199dCd52) - deploy tx [`0x66aa01d2…`](https://explorer-studio-dev.genlayer.com/tx/0x66aa01d2bd9087b1dd28fbeba78c6d242050c58408a838e8cd9a91b760136cd2); constructed with PayMatch's address and the ENS DAO treasury `0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7` as its trusted payer |
| Runner | `py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng` (v0.3.0) |
| Deployer | `0x5cdb5699bc1038e115A973bb91A646f7E98C075b` |

Both contracts passed the live runner's `getContractSchemaForCode` check before deploying, and **the code on-chain is byte-identical to this repo**: `cd studio-next && npx tsx verify_code.ts <address> <file>` fetches it with `gen_getContractCode` and compares.

| Contract | SHA-256 on-chain = SHA-256 of the repo file |
|---|---|
| PayMatch / `contracts/pay_match_studio_next.py` | `8724ed555d1c920327bfe1c089a598b0fd6682d3dd592052e266f5df69aa09d0` |
| TrancheGate / `contracts/tranche_gate_studio_next.py` | `21c02f8650cc0d68ca2809c2c5408cdc6958f073220fbaa9ace8ea5b809812a9` |

## Live proof (11 October 2026)

Reproduce with `cd studio-next && npx tsx prove.ts <paymatch> <tranchegate> <register|refuse|verify|gate|read>`. Every row is from [`studio-next/live_proof.json`](studio-next/live_proof.json), written as it ran (it resumes where it stopped), with the contract's recorded output. "Agree" counts the validators that actively voted (Studio Next leaves the rest of the 5-seat committee idle). **All 32 transactions reached consensus with every voting validator agreeing**, including the ones the contracts refused: a refusal is a decided outcome.

The authorisations are the ENS DAO's own Snapshot funding requests; the payments are the real Ethereum transactions by which its treasury (`wallet.ensdao.eth`, `0xFe89cc7a…`) paid the Ecosystem Working Group multisig (`0x2686a891…`, `main.eco.wg.ens.eth`).

### Registering authorisations

| Id | The request | Registration | Recorded |
|---|---|---|---|
| `eco470` | Funding Request: ENS Ecosystem Working Group (Oct. Window), vote closed 10 Nov 2025, cap 470,000 USDC, payer `0xfe89cc7a…` | [`0x7dbbd4db…`](https://explorer-studio-dev.genlayer.com/tx/0x7dbbd4db016ac0d7f59006e6ad8cc402c1621726413f75b73c0d92cb75e7595a) 3 agree | the validators' quote: *"The ENS Ecosystem Working Group is requesting **470k in USDC** and zero ETH."*; vote For 1,375,141 to Against 0; document SHA-256 `2fe96c52d88b…` |
| `eco836` | Funding Request: ENS Ecosystem Working Group, vote closed 14 Oct 2024, cap 836,000 USDC, payer `0xfe89cc7a…` | [`0xc8851149…`](https://explorer-studio-dev.genlayer.com/tx/0xc885114978d4df572fa05583a4a3be022fe0660277e4871edece21b976465899) 3 agree | the validators' quote: *"Ecosystem WG is requesting 836,000 in USDC and zero ETH."*; vote For 1,430,724 to Against 0; document SHA-256 `87b823528e27…` |
| `eco409` | Funding Request: ENS Ecosystem Working Group, vote closed 25 Oct 2023, cap 409,000 USDC, payer `0xfe89cc7a…` | [`0xb43d8866…`](https://explorer-studio-dev.genlayer.com/tx/0xb43d8866764ec8161711589aa4dd9b4a1e5dd701154181d5d2ac628ea8ab8103) 3 agree | the validators' quote: *"As result, Ecosystem WG is requesting 409,000 in USDC and zero ETH."*; vote For 1,561,995 to Against 3; document SHA-256 `1a01c8587eac…` |
| `eco470-alt-payer` | Funding Request: ENS Ecosystem Working Group (Oct. Window), vote closed 10 Nov 2025, cap 470,000 USDC, payer `0x703abdbb…` | [`0xc2b463f6…`](https://explorer-studio-dev.genlayer.com/tx/0xc2b463f60ce7beaebab9112dae443fc7c696b430bb45df15f470917ec9d57d92) 3 agree | the validators' quote: *"The ENS Ecosystem Working Group is requesting 470k in USDC and zero ETH."*; vote For 1,375,141 to Against 0; document SHA-256 `2fe96c52d88b…` |

`eco470-alt-payer` is the same vote registered with a look-alike address as the payer. It is a separate authorisation by design (see the gate below).

### Refusals

Each is a registration the contract refused. The reasons are the contract's own, decided from the documents, the vote and the explorer.

| What it tries | Tx | Revert message |
|---|---|---|
| cap not in the document | [`0x7d0c8854…`](https://explorer-studio-dev.genlayer.com/tx/0x7d0c8854e806d31c85f39a6cd3b24d7c41132d4167d5dc3358d53dc0bfcf57e6) 3 agree | `authorisation refused: cap_not_in_document` |
| recipient not in the document | [`0x6818fa50…`](https://explorer-studio-dev.genlayer.com/tx/0x6818fa50f7c4d6ca24a8982ac5d7586123f888d474451c31831390a846230cd9) 3 agree | `authorisation refused: recipient_not_in_document` |
| a vote that did not pass | [`0xbe39654e…`](https://explorer-studio-dev.genlayer.com/tx/0xbe39654eb0f9274b4cf3b4aa95e7ebcf3599cc1c581124bce730b803549972b4) 3 agree | `authorisation refused: recipient_not_in_document, cap_not_in_document, vote_did_not_pass` |
| asset not named in the document | [`0x02607830…`](https://explorer-studio-dev.genlayer.com/tx/0x0260783099bd183fbbf0037e2faaa4b8fce14293fa3940ce068e4c195df89f4e) 3 agree | `authorisation refused: symbol_not_in_document` |
| a vote counted twice | [`0x8524d00e…`](https://explorer-studio-dev.genlayer.com/tx/0x8524d00e791d9f6aa89534fa554fda53a2d91fca08c9102e555941d22eda68c3) 3 agree | `that vote already authorises this payer, recipient and asset as 'eco470'` |
| a figure in the document that is not the request (reader) | [`0x5982dbc7…`](https://explorer-studio-dev.genlayer.com/tx/0x5982dbc79c2cbb20fef17f5b8487bb12c46000bd33ce87034bf7f9bb718e3811) 3 agree | `authorisation refused: document_does_not_authorise_this_payment` |

The last refusal in the table that reads *document does not authorise this payment* is the reader's: `172k` is a figure in the request's own budget table (the Main Multisig's line), so the cap is "in the document", and the validators' LLMs still refused it as not what the document asks to be paid. The others are decided by plain code with no LLM.

### Judging payments

Each row is one `verify_payment` against the named authorisation. The verdict, amount and reasons are what the contract recorded after both indexers (Blockscout and Routescan) agreed.

| Authorisation | Transaction judged | What it is | Verdict | Amount (USDC) | Tx |
|---|---|---|---|---|---|
| `eco470` | [`0x85462789…`](https://etherscan.io/tx/0x85462789b2919f32fa7da4ea7ece7665a87a881ada5ad48ecd17aff47e613036) | the treasury paid exactly the approved 470,000 (one of three payments in the transaction) | **MATCH** | 470,000 | [`0x35d5aa4a…`](https://explorer-studio-dev.genlayer.com/tx/0x35d5aa4a0aec4d14777da0abee913ee402c16bce0128462ef67d869f0c080550) 3 agree |
| `eco836` | [`0x80b10aa6…`](https://etherscan.io/tx/0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c) | 836,000 paid in 2024 | **MATCH** | 836,000 | [`0xdca9a68d…`](https://explorer-studio-dev.genlayer.com/tx/0xdca9a68d36f1ef9babef218c7475ca84a20fdf473eb653f71931c6b0856ed040) 3 agree |
| `eco470` | [`0x80b10aa6…`](https://etherscan.io/tx/0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c) | the 2024 payment, against a request voted a year later | **BEFORE_APPROVAL** | 836,000 | [`0x45f84c53…`](https://explorer-studio-dev.genlayer.com/tx/0x45f84c5396c5623c9aa7894669fe1f794ba261008d69a3c4765d16ae82368f6f) 3 agree |
| `eco470` | [`0x6464aca3…`](https://etherscan.io/tx/0x6464aca3757d68a42ca8448af53207036b67c20ec8693f1d5ba4cc79d3881d72) | the treasury paying a different group | **WRONG_RECIPIENT** | 0 | [`0x031faf4d…`](https://explorer-studio-dev.genlayer.com/tx/0x031faf4d50aa446e05bb7e0e63bf19a24cee1e76593224a555b3cbd18bc8766d) 3 agree |
| `eco470` | [`0x09fc99e8…`](https://etherscan.io/tx/0x09fc99e8734ae9a5ff57b7ad57c1cd5ed6ceb61ca8eee71ca27c3ab616037d06) | 0.001 USDC from a look-alike address | **WRONG_PAYER** | 0 | [`0x676e0a11…`](https://explorer-studio-dev.genlayer.com/tx/0x676e0a11fed965912fa7c1af8470d440655a39ef19d375cee34290de739c56bd) 3 agree |
| `eco470` | [`0xa72389d2…`](https://etherscan.io/tx/0xa72389d239eee71dfe9ea7a59a1a1b11e15028aa6f211dbc38bc3822164b83ed) | a reverted transaction | **TX_FAILED** | 0 | [`0xdb980725…`](https://explorer-studio-dev.genlayer.com/tx/0xdb9807257b6544ae413a9738924579c2b8c96550cc685c81d6e5804906593dd2) 3 agree |
| `eco470` | [`0x5f8c3a0b…`](https://etherscan.io/tx/0x5f8c3a0b74fde822c4ea32d9f9ee5fb672a65dd9290f8448fde38dad1b4bdecf) | a plain ETH transfer | **NO_TRANSFER** | 0 | [`0x32e400be…`](https://explorer-studio-dev.genlayer.com/tx/0x32e400be0c2a74305eb1cb325592603525626d7203aa4c628899100561173059) 3 agree |
| `eco470` | [`0x641907b0…`](https://etherscan.io/tx/0x641907b05caa5a18aecc9d8379f1322a52b81340731074caef7ec54ed02af3de) | a 50+ transfer poisoning batch | **UNDETERMINED** | 0 | [`0xc8faa610…`](https://explorer-studio-dev.genlayer.com/tx/0xc8faa6108c7e0a6936f622b314b01db8dfe678dc8ed319c96ccfcd5e61d04337) 3 agree |
| `eco470` | [`0x00000000…`](https://etherscan.io/tx/0x0000000000000000000000000000000000000000000000000000000000000001) | a transaction that does not exist | **UNDETERMINED** | 0 | [`0x55115e97…`](https://explorer-studio-dev.genlayer.com/tx/0x55115e97ab8c9a1e2dbd057e4af888ff387e45673aa7a668bc70a8aafc052989) 3 agree |
| `eco836` | [`0x85462789…`](https://etherscan.io/tx/0x85462789b2919f32fa7da4ea7ece7665a87a881ada5ad48ecd17aff47e613036) | 470,000 more would take the total past the 836,000 cap | **OVER_CAP** | 470,000 | [`0xf251f70d…`](https://explorer-studio-dev.genlayer.com/tx/0xf251f70dec4e0d84d2494a7a17b901e0cb9805fe3c0ab76eac7637bc72989dbf) 3 agree |
| `eco470-alt-payer` | [`0x09fc99e8…`](https://etherscan.io/tx/0x09fc99e8734ae9a5ff57b7ad57c1cd5ed6ceb61ca8eee71ca27c3ab616037d06) | anyone can be registered as payer: the dust sender 'matches' its own dust | **MATCH** | 0.001 | [`0x2b54d7b4…`](https://explorer-studio-dev.genlayer.com/tx/0x2b54d7b481e81466477321b01debf1323701851e0273babe68112349ad7b6edf) 3 agree |
| `eco409` | [`0x7eadcd84…`](https://etherscan.io/tx/0x7eadcd845362e160fa4a6f1918132c1b2c918fdb25e81cc3358ca11ef8daa1fe) | the real 409,000 payment is verified | **MATCH** | 409,000 | [`0xddbf473c…`](https://explorer-studio-dev.genlayer.com/tx/0xddbf473cb72b5b8e4d14d8fc385609528af149caf08c7319472bb3a53ad11e5d) 3 agree |
| `eco409` | [`0x80b10aa6…`](https://etherscan.io/tx/0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c) | the 836,000 payment against the 409,000 request: OVER_CAP, flagged | **OVER_CAP** | 836,000 | [`0x67fb424a…`](https://explorer-studio-dev.genlayer.com/tx/0x67fb424a77608e27c7dd41fa97f279571bad309afd99a012d19ed08d72eeef76) 3 agree |

`UNDETERMINED` is not a finding: it is recorded in the history but does not count against the authorisation, and the same transaction can be judged again. The facts behind every row (both indexers' agreed view: block, time, finality, every transfer of the asset) are in the on-chain record (`get_payment`) and in `live_proof.json`.

### TrancheGate: the verdict drives an action

The gate trusts one payer, the ENS treasury. A release is allowed only if PayMatch's own record shows the earlier tranches paid and matched, nothing flagged, and room under the cap. Amounts are in USDC's smallest unit (6 decimals).

| Step | Call | Outcome | Tx |
|---|---|---|---|
| tranche 1 of 200,000 USDC before anything is paid: allowed (nothing earlier is owed) | `release(eco409, 1, 200000000000)` | **released** | [`0x48ecd247…`](https://explorer-studio-dev.genlayer.com/tx/0x48ecd247cb3f11249a4505594e83235cab77b2c3e158795640124049b11d2ee4) 3 agree |
| tranche 2 while tranche 1 is unpaid: refused | `release(eco409, 2, 100000000000)` | refused: `'eco409' refused: tranches worth 200000000000 were released but only 0 has been paid and matched` | [`0xd6784a7a…`](https://explorer-studio-dev.genlayer.com/tx/0xd6784a7a2219abdc468c6d1f45a9ccd7e015f51fd96c6aab392e0ebb3c28174f) 3 agree |
| the real 409,000 payment is verified | `PayMatch.verify_payment(eco409, t409)` | **MATCH** | [`0xddbf473c…`](https://explorer-studio-dev.genlayer.com/tx/0xddbf473cb72b5b8e4d14d8fc385609528af149caf08c7319472bb3a53ad11e5d) 3 agree |
| tranche 2 once the payment is on record: allowed | `release(eco409, 2, 100000000000)` | **released** | [`0xc4a10e81…`](https://explorer-studio-dev.genlayer.com/tx/0xc4a10e8157fe0184d9ec8aa7cb1a8103cc2d903b034690f7915f710e0b5062fc) 3 agree |
| tranche 3 would take releases past the cap: refused | `release(eco409, 3, 200000000000)` | refused: `'eco409' refused: this tranche would take releases past the authorised cap 409000000000` | [`0x676b3e9b…`](https://explorer-studio-dev.genlayer.com/tx/0x676b3e9be611d0481c7139d12abe81c2b4d85e87d9db6959bc776ec018777899) 3 agree |
| an authorisation PayMatch has never heard of: refused | `release(nope, 1, 1000000)` | refused: `'nope' refused: PayMatch has no such authorisation` | [`0xe34e7e40…`](https://explorer-studio-dev.genlayer.com/tx/0xe34e7e40ea10d52b327f497464763e791704a9e9252a1ec28e090e3eb5934136) 3 agree |
| a tranche out of order: refused | `release(eco409, 9, 1000000)` | refused: `tranches are released in order: the next is 3` | [`0x00342177…`](https://explorer-studio-dev.genlayer.com/tx/0x003421779f24f2efb260df4a9358dc5de16af37eba4ef1d2772821ca53ba3889) 3 agree |
| eco470 has flagged payments against it: refused | `release(eco470, 1, 1000000)` | refused: `'eco470' refused: a payment against it was flagged (5)` | [`0x858ce357…`](https://explorer-studio-dev.genlayer.com/tx/0x858ce3571fe1f5f947910ae340c19f61c56d1759be343f1a7efaf34bb1a3eb25) 3 agree |
| an authorisation naming a payer the gate does not trust: refused | `release(eco470-alt-payer, 1, 1000000)` | refused: `'eco470-alt-payer' refused: its payer 0x703abdbb99c60068f78737bb3bf94869b9cc789b is not the treasury this gate trusts` | [`0x94655953…`](https://explorer-studio-dev.genlayer.com/tx/0x946559534c3cf5f086282546f6b09a6eb1c71edcc5e39880c784b15e64906353) 3 agree |
| the 836,000 payment against the 409,000 request: OVER_CAP, flagged | `PayMatch.verify_payment(eco409, t836)` | **OVER_CAP** | [`0x67fb424a…`](https://explorer-studio-dev.genlayer.com/tx/0x67fb424a77608e27c7dd41fa97f279571bad309afd99a012d19ed08d72eeef76) 3 agree |
| eco409 is now flagged too: refused | `release(eco409, 3, 1000000)` | refused: `'eco409' refused: a payment against it was flagged (1)` | [`0x4b9f1478…`](https://explorer-studio-dev.genlayer.com/tx/0x4b9f1478f8a4dfbdbf69a6da8a85018226a671dce5adbfd99444e2c6f338773e) 3 agree |

After the run `TrancheGate.get_config()` reports 2 releases, and each authorisation reads back as follows from `PayMatch.get_reconciliation`:

| Authorisation | Cap (USDC) | Matched (USDC) | Flagged | Payments |
|---|---|---|---|---|
| `eco470` | 470,000 | 470,000 | 5 | 8 |
| `eco836` | 836,000 | 836,000 | 1 | 2 |
| `eco409` | 409,000 | 409,000 | 1 | 2 |
| `eco470-alt-payer` | 470,000 | 0.001 | 0 | 1 |

`get_history("eco470")` walks that authorisation's own chain, newest first: #8:UNDETERMINED → #7:UNDETERMINED → #6:NO_TRANSFER → #5:TX_FAILED → #4:WRONG_PAYER → #3:WRONG_RECIPIENT → #2:BEFORE_APPROVAL → #0:MATCH.

## What the live run found

Running the contract on the real network found three things Direct Mode could not, each fixed and covered by a test or a mutation:

- **A view returned a float and the runtime could not encode it.** The stored vote record carried Snapshot's scores (`1375141.4178885242`). `get_authorisation` failed with a bare `exit_code 1` although every Direct Mode test passed. GenVM calldata has no float type, so the scores are carried as text, and a test asserts that no view returns a float.
- **A model's quote of a Markdown table row failed grounding.** Asked about the 836,000 request, the validators' models sometimes quoted `ENS Ecosystem Main Multisig | 836,000 | -- | --`: genuine words, but not verbatim next to the document's link syntax, and naming no asset. The registration was refused depending on which validator led. Quotes and documents are now compared as the words a reader sees (Markdown links, table bars and emphasis removed), the reader is told to prefer a sentence of prose, and an affirmative quote that cannot be grounded is asked for once more. A refusal is never retried, so the retry can only turn an unreadable answer into a readable one, never a "no" into a "yes".
- **One model returned text that was not JSON.** On a scratch copy of the contract, one validator (`gpt-oss`) answered with prose ([tx `0xb1e53497…`](https://explorer-studio-dev.genlayer.com/tx/0xb1e5349775778ef196a5a6fa6dfac4d7db8c3cbb1194c1eda5494973bbee9ccf)); the exception escaped and cost a vote (the round still carried). A reader that does not return JSON is now treated as unreadable and asked once more, then fails closed.

## Superseded deployments

The three earlier PayMatch deployments ran the same design while these were found. None is current; nothing here points at them.

| PayMatch | Deploy tx | Why it is superseded |
|---|---|---|
| `0x8c244D9747421Cfff1E1B8E4702B76eBCFac7697` | [`0x4bf569c5…`](https://explorer-studio-dev.genlayer.com/tx/0x4bf569c5f28ad7c7add2c1951f5a28da34634a31bf2cef5ea1359a8b6774e686) | `get_authorisation` returned a float (above). |
| `0xC24c75D227e85A539A10027d92a6d9164951F003` | [`0x0d206156…`](https://explorer-studio-dev.genlayer.com/tx/0x0d206156403c06726926a2037d89af94d08270f3b9d28b94306316b910400219) | The reader refused real quotes it should have grounded (above). Its partial log is `studio-next/live_proof_superseded_v2.json`. |
| `0xc03F375E046917a1201f5d5FAd4b4f9F94c62D99` | [`0x01edd7dc…`](https://explorer-studio-dev.genlayer.com/tx/0x01edd7dcccfea9d9b298beeff46748431a934e0fd73931bbb82b81cadd3fb868) | The same code as the current deployment. Its gate run failed because the script passed `release`'s `u256` amount as a string, and the failed run left `eco409` in an unintended state, so the proof was rerun from a clean deployment. Its log is `studio-next/live_proof_superseded_v3.json`. |

## Proven in tests, not live

Direct Mode proves these on real captures (or a real response with one marked field changed); none has a live transaction:

- `WRONG_ASSET` (the payer paid the recipient in another token and sent none of the asset): no real transaction was found, so it is proven on crafted facts.
- `OUTSIDE_WINDOW` and the inclusive edge of `valid_until`, and `BEFORE_APPROVAL` to the second the vote closed.
- Disagreeing indexers, one indexer unreachable or malformed, a payment not yet 64 blocks deep, a reorged log, an ERC-721 event with the same signature, a 50-item page with no next page: all fail closed, on real responses with one field changed.
- A document whose bytes do not match its address; a vote record for another document, an open vote, a tie, another space, results of the wrong type.
- Every TrancheGate check that runs before its cross-contract call (owner, amount, order, the trusted payer's format). Its checks that read PayMatch are proven by the live table above, because Direct Mode cannot simulate a cross-contract call. The window-closed check has no live refusal.
- The replay: `test_the_fixtures_reproduce_what_the_validators_agreed_on_live` runs every live verification again on the committed fixtures and requires the same facts, verdict, reasons, amount and block.
