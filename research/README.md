# Research: what GenVM can read, before PayMatch was built

Every source PayMatch might use was fetched **from inside GenVM on Studio Next**, not from a laptop, because a source can answer a validator (a US-region sandbox) differently from a person. One throwaway probe contract did the fetching ([`probe_studio_next.py`](probe_studio_next.py), deployed at [`0xb9469F3d10cFb7EcF03CEa80c4DA1345D3bb279b`](https://explorer-studio-dev.genlayer.com/address/0xb9469F3d10cFb7EcF03CEa80c4DA1345D3bb279b), deploy tx [`0x5e8241f3…`](https://explorer-studio-dev.genlayer.com/tx/0x5e8241f3b1861bdd6a522d673942e8a1d3832f212f12a17d62079c5597de9d2e)). `probe_many(urls, ua)` stores each URL's status, byte length, SHA-256, content type and the first and last bytes; `get_results()` reads them back. Transactions are linked below. The same real transaction and the same real proposal were used throughout (the ENS DAO's 470,000 USDC payment of 2026-02-18 and the funding request it paid), so a number that differs is a source that differs.

## Chain facts

| Source | From GenVM | Used |
|---|---|---|
| Blockscout (Ethereum): `/api/v2/transactions/<hash>` ([batch A](https://explorer-studio-dev.genlayer.com/tx/0x4ac9f15549868ec2e896fca66bb7eacd6b92529a5fced005e597d6f9941af873)) | 200, 22,300 bytes, JSON | **yes** |
| Blockscout: `/transactions/<hash>/token-transfers` | 200, 8,394 bytes | **yes** (50 transfers a page) |
| Blockscout: `/tokens/<address>` | 200, 472 bytes | **yes** (the pinned-token check) |
| Routescan, an independent indexer, `eth_getTransactionReceipt` | 200, 7,891 bytes | **yes**: the second source |
| Routescan `eth_getBlockByNumber` and `eth_blockNumber` ([batch C](https://explorer-studio-dev.genlayer.com/tx/0x1068debd58e575403069ad5ade876285faae85d6d5f2091a3808658510d30d09)) | 200 | **yes** (block time, finality) |
| Blockscout, a hash that does not exist | **404**, `{"message":"Not found"}` | read as "not found" |
| Routescan, a hash that does not exist | 200, `"result": null` | read as "not found" |
| `base.blockscout.com` | **403**, a Cloudflare "Just a moment" page | no: PayMatch is Ethereum-only |
| beaconcha.in (checked locally) | 401, needs an API key | no |

Both indexers returned the same transaction, so PayMatch requires them to agree. A **POST** probe ([tx `0x6864dfdd…`](https://explorer-studio-dev.genlayer.com/tx/0x6864dfdd0f5a96e452161bf820c79bdd9ef2a23d67d657c3551d8b0d5d57a6d6)) showed `gl.nondet.web.post` and `gl.nondet.web.request(method="POST")` both work, so a JSON-RPC node was a possible third source. It was not used: `ethereum-rpc.publicnode.com` answered `{"result": null}` for a February 2026 receipt that the other two sources return in full. **A single source can answer "unknown" for a transaction that exists**, which is why one source reporting "not found" is never read as "does not exist" and two sources that disagree are `UNDETERMINED`.

## The approval document and the vote

| Source | From GenVM | Used |
|---|---|---|
| Snapshot's IPFS gateway, `snapshot.4everland.link/ipfs/<cid>` | 200, 6,343 bytes; **its SHA-256 is the CID's own hash** | **yes** |
| `ipfs.io/ipfs/<cid>` | **429**, "this IPFS gateway is switching to a service worker gateway only" | no |
| `dweb.link`, `w3s.link` | **429**, the same notice | no |
| `gateway.pinata.cloud` | **404**, a timeout searching the network | no |
| `hub.snapshot.org/graphql?query=…` (GET) | 200 | **yes** (the vote record) |
| `raw.githubusercontent.com` | 200 | no |

The public IPFS gateways refuse validators; Snapshot's own gateway serves them. Because a raw-codec CID (`bafkrei…`) **is** the SHA-256 of the document, PayMatch hashes what the gateway returns and compares it with the address, so the gateway is not trusted at all. The hub's record names the document it voted on (`ipfs`), the space, the choices, the scores and when voting ended.

## What the data decided

- **Ethereum only, two indexers.** Base's Blockscout is behind a Cloudflare challenge for validators; a payment is only trusted when two independent indexers can be read.
- **The payer cannot come from the vote.** The ENS Snapshot space declares no treasury (`treasuries: []`; checked for the most-followed spaces too). So the payer is the registrant's claim, stored immutably, and a consumer pins the treasury it trusts (TrancheGate).
- **Real adversarial data is on the recipient's own history.** The ENS Ecosystem multisig receives a steady stream of **address-poisoning dust**: 0.001 USDC from look-alike senders, some as 50-transfer batches. They are real USDC at the real address, so a check that only asked "did the recipient receive the asset?" would be fooled. The payer binding and the transfer-page limit come from this.
- **Quotes are of Markdown.** The ENS proposals are Markdown (tables, links). A model quoting a table row is quoting genuine words, so quotes are compared as the words a reader sees (`_plain`), and the reader is asked once more if a quote cannot be grounded.
