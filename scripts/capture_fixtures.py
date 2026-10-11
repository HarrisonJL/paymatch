"""
Captures the real responses the tests run on and writes tests/fixtures/ plus
tests/fixtures/manifest.json (URL, HTTP status, SHA-256 and size of every
file). Everything is committed byte for byte as served - nothing is
reduced - so the IPFS documents still hash to their own addresses and the
tests exercise exactly what the validators parse.

Run from the repo root:   python3 scripts/capture_fixtures.py
Captured 2026-10-11 from: snapshot.4everland.link (IPFS), hub.snapshot.org,
eth.blockscout.com and api.routescan.io. The transactions are immutable chain
history; the Snapshot votes are closed.
"""

import hashlib
import json
import pathlib
import sys
import urllib.request

OUT = pathlib.Path(__file__).resolve().parent.parent / "tests" / "fixtures"
BLOCKSCOUT = "https://eth.blockscout.com/api/v2/"
ROUTESCAN = "https://api.routescan.io/v2/network/mainnet/evm/1/etherscan/api?module=proxy&action="
SNAPSHOT_IPFS = "https://snapshot.4everland.link/ipfs/"
SNAPSHOT_HUB = "https://hub.snapshot.org/graphql?query="

# The ENS DAO's funding requests (Snapshot, approved) and the on-chain payments
# of those requests from the DAO treasury, plus the real look-alikes that the
# verdicts must tell apart. Every id and hash below is public.
PROPOSALS = {
    "eco470": ("0x9b3f5463e52aadc35155e686f8416297b24e6c7e30cb527747e61cf17b42a5f6",
               "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2pm"),   # 6.24.2: 470,000 USDC, Nov 2025
    "eco836": ("0xfe303865510b5ef7fabee2bcbd5081afa01f276195f57e1561ff27c477459984",
               "bafkreiehxarvfdrhw4tbodt3breveu6s2puyhiosvxhjrlyioiz2eazws4"),   # 5.17.2: 836,000 USDC, Oct 2024
    "eco409": ("0x12a2abca291496c7e990d099240b4c995099dc0fb85767e04f22b9496e953799",
               "bafkreia2ahefq7vmmgs5utov7a3db5mskx6rytrahms5c2fdcxkps6o3vq"),   # 4.4.1: 409,000 USDC, 2023
    "rejected": ("0xbc44d9714ee818da49c25998cabdbe745f939fef74923255c3571a00e8977e5d",
                 "bafkreifhxyn66hrmragdms52pk3svo7mh3edb3k7jxpozcbexlpmj5r6kq"),  # 6.25: voted down
}
TXS = {
    "t470": "0x85462789b2919f32fa7da4ea7ece7665a87a881ada5ad48ecd17aff47e613036",   # 2026-02-18, treasury -> 3 WGs (470,000 to Ecosystem)
    "t836": "0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c",   # 2024-11-29, 836,000 to Ecosystem
    "t409": "0x7eadcd845362e160fa4a6f1918132c1b2c918fdb25e81cc3358ca11ef8daa1fe",   # 2023-11-20, 409,000 to Ecosystem (+ ENS tokens elsewhere)
    "poison": "0x09fc99e8734ae9a5ff57b7ad57c1cd5ed6ceb61ca8eee71ca27c3ab616037d06",  # 2026-05-01, 0.001 USDC to the Ecosystem multisig from a look-alike sender (address poisoning)
    "spam": "0x641907b05caa5a18aecc9d8379f1322a52b81340731074caef7ec54ed02af3de",    # 2026-06-13, the same trick as a 50+ transfer batch
    "other": "0x6464aca3757d68a42ca8448af53207036b67c20ec8693f1d5ba4cc79d3881d72",  # 2026-02-07, treasury pays 125,000 USDC to Meta-Governance
    "failed": "0xa72389d239eee71dfe9ea7a59a1a1b11e15028aa6f211dbc38bc3822164b83ed",  # a reverted transaction
    "eth": "0x5f8c3a0b74fde822c4ea32d9f9ee5fb672a65dd9290f8448fde38dad1b4bdecf",    # a plain ETH transfer, no token moved
    "none": "0x0000000000000000000000000000000000000000000000000000000000000001",   # does not exist
}
ASSETS = {
    "USDC": ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    "USDT": ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    "DAI": ("0x6b175474e89094c44da98b954eedeac495271d0f", 18),
    "EURC": ("0x1abaea1f7c830bd89acc67ec4af516284b1bc33c", 6),
    "WETH": ("0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", 18),
    "ENS": ("0xc18360217d8f7ab5e7c516566761ea12ce7f9d72", 18),
    "UNI": ("0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", 18),
}


def hub_url(proposal_id: str) -> str:
    return (SNAPSHOT_HUB + "query%7Bproposal%28id%3A%22" + proposal_id
            + "%22%29%7Bid%20ipfs%20state%20scores%20choices%20end%20start%20space%7Bid%7D%7D%7D")


def fetch(url: str):
    req = urllib.request.Request(url, headers={"user-agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}

    def save(name: str, url: str) -> bytes:
        status, body = fetch(url)
        (OUT / name).write_bytes(body)
        manifest[name] = {"url": url, "status": status, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
        print(f"{status} {len(body):>7}  {name}")
        return body

    for key, (pid, cid) in PROPOSALS.items():
        save(f"ipfs_{key}.json", SNAPSHOT_IPFS + cid)
        save(f"hub_{key}.json", hub_url(pid))
    for symbol, (address, decimals) in ASSETS.items():
        body = save(f"token_{symbol}.json", BLOCKSCOUT + "tokens/" + address)
        doc = json.loads(body)
        assert doc["address_hash"].lower() == address and doc["symbol"] == symbol \
            and str(doc["decimals"]) == str(decimals) and doc["type"] == "ERC-20", f"registry mismatch for {symbol}"
    for key, tx in TXS.items():
        save(f"bs_tx_{key}.json", BLOCKSCOUT + "transactions/" + tx)
        status, _ = fetch(BLOCKSCOUT + "transactions/" + tx)
        if status == 200:
            save(f"bs_transfers_{key}.json", BLOCKSCOUT + "transactions/" + tx + "/token-transfers")
        body = save(f"rs_receipt_{key}.json", ROUTESCAN + "eth_getTransactionReceipt&txhash=" + tx)
        receipt = json.loads(body).get("result")
        if receipt:
            save(f"rs_block_{key}.json", ROUTESCAN + "eth_getBlockByNumber&tag=" + receipt["blockNumber"] + "&boolean=false")
    save("rs_latest.json", ROUTESCAN + "eth_blockNumber")
    (OUT / "manifest.json").write_text(json.dumps({"captured": "2026-10-11", "fixtures": manifest}, indent=1, sort_keys=True))
    print(f"wrote {len(manifest)} fixtures")
    return 0


if __name__ == "__main__":
    sys.exit(main())
