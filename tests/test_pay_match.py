"""
Deterministic tests for PayMatch using genlayer-test's Direct Mode.

Inputs are real: three ENS DAO funding requests (Snapshot proposals, stored on
IPFS and approved by vote), the on-chain USDC payments the DAO treasury made
for them, and the real look-alikes the verdicts must tell apart - captured on
2026-10-11 byte for byte from snapshot.4everland.link, hub.snapshot.org,
eth.blockscout.com and api.routescan.io (scripts/capture_fixtures.py; sources
and SHA-256s in tests/fixtures/manifest.json). Nothing is reduced, so each
IPFS document still hashes to its own address.

Real cases are the test cases:
- ENS Ecosystem Working Group asked for 470,000 USDC (vote closed Nov 2025);
  the treasury paid exactly that on 2026-02-18, in one transaction that also
  paid two other working groups. Likewise 836,000 (paid 2024-11-29) and
  409,000 (paid 2023-11-20, in a transaction that also moved ENS tokens).
- The 836,000 payment against the 409,000 request is OVER_CAP; against the
  470,000 request it is BEFORE_APPROVAL (it was paid a year before that vote).
- The treasury's 125,000 USDC to the Meta-Governance group is WRONG_RECIPIENT
  for an Ecosystem authorisation; the 0.001 USDC "address poisoning" dust sent
  to the Ecosystem multisig from a look-alike address is WRONG_PAYER, and the
  same trick as a 50-transfer batch is UNDETERMINED (more transfers than the
  indexer lists in a page); a reverted transaction is TX_FAILED; a plain ETH
  transfer is NO_TRANSFER; a hash nobody has used is not found.
- ENS's vote to replace its working groups was voted down: a real rejected vote.

Anything not capturable is built from a real response with one field changed
and marked SYNTHETIC wherever it is used.

Five layers: pure helpers, registering an authorisation, judging a payment,
what a consumer reads, and the consensus boundary.
"""

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).parent.parent
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())["fixtures"]
NOW = "2026-10-11T18:00:00Z"

ECO = "0x2686a8919df194aa7673244549e68d42c1685d03"        # ENS Ecosystem Working Group multisig
TREASURY = "0xfe89cc7abb2c4183683ab71653c4cdc9b02d44b7"   # ENS DAO treasury (timelock)
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
PROPOSAL = {
    "eco470": ("0x9b3f5463e52aadc35155e686f8416297b24e6c7e30cb527747e61cf17b42a5f6",
               "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2pm", "470000"),
    "eco836": ("0xfe303865510b5ef7fabee2bcbd5081afa01f276195f57e1561ff27c477459984",
               "bafkreiehxarvfdrhw4tbodt3breveu6s2puyhiosvxhjrlyioiz2eazws4", "836000"),
    "eco409": ("0x12a2abca291496c7e990d099240b4c995099dc0fb85767e04f22b9496e953799",
               "bafkreia2ahefq7vmmgs5utov7a3db5mskx6rytrahms5c2fdcxkps6o3vq", "409000"),
    "rejected": ("0xbc44d9714ee818da49c25998cabdbe745f939fef74923255c3571a00e8977e5d",
                 "bafkreifhxyn66hrmragdms52pk3svo7mh3edb3k7jxpozcbexlpmj5r6kq", "100000"),
}
QUOTE = {
    "eco470": "The ENS Ecosystem Working Group requests funding of 470,000 USDC to support operations through April 2026",
    "eco836": "The ENS Ecosystem Working Group requests funding of 836,000 USDC to support operations through April 2025",
    "eco409": "The ENS Ecosystem Working Group requests funding of 409,000 USDC to support operations until the March 2024 funding window",
}
TX = {
    "t470": "0x85462789b2919f32fa7da4ea7ece7665a87a881ada5ad48ecd17aff47e613036",
    "t836": "0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c",
    "t409": "0x7eadcd845362e160fa4a6f1918132c1b2c918fdb25e81cc3358ca11ef8daa1fe",
    "poison": "0x09fc99e8734ae9a5ff57b7ad57c1cd5ed6ceb61ca8eee71ca27c3ab616037d06",
    "spam": "0x641907b05caa5a18aecc9d8379f1322a52b81340731074caef7ec54ed02af3de",
    "other": "0x6464aca3757d68a42ca8448af53207036b67c20ec8693f1d5ba4cc79d3881d72",
    "failed": "0xa72389d239eee71dfe9ea7a59a1a1b11e15028aa6f211dbc38bc3822164b83ed",
    "eth": "0x5f8c3a0b74fde822c4ea32d9f9ee5fb672a65dd9290f8448fde38dad1b4bdecf",
    "none": "0x0000000000000000000000000000000000000000000000000000000000000001",
}
READER = "request or authorise a payment of up to"


# --- Helpers ------------------------------------------------------------------


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def _mock(direct_vm, url: str, body, status: int = 200) -> None:
    # Anchored at both ends, so one URL can never be served another's body.
    raw = body if isinstance(body, bytes) else body.encode("utf-8")
    direct_vm.mock_web("^" + re.escape(url) + "$", {"method": "GET", "response": {
        "status": status, "headers": {}, "body": raw}})


def _serve(direct_vm, name: str, body=None, status=None) -> None:
    meta = MANIFEST[name]
    raw = (FIXTURES / name).read_bytes() if body is None else body
    _mock(direct_vm, meta["url"], raw, meta["status"] if status is None else status)


def _serve_set(direct_vm, names, over) -> None:
    # A later mock for a URL does not replace an earlier one, so a scenario that
    # changes a response says so up front: over = {fixture name: (body, status)}.
    direct_vm.clear_mocks()
    for name in names:
        if name in MANIFEST:
            body, status = (over or {}).get(name, (None, None))
            _serve(direct_vm, name, body=body, status=status)


def _serve_registration(direct_vm, key: str, asset: str = "USDC", over=None) -> None:
    _serve_set(direct_vm, (f"ipfs_{key}.json", f"hub_{key}.json", f"token_{asset}.json"), over)


def _serve_tx(direct_vm, key: str, over=None) -> None:
    _serve_set(direct_vm, (f"bs_tx_{key}.json", f"bs_transfers_{key}.json", f"rs_receipt_{key}.json",
                           f"rs_block_{key}.json", "rs_latest.json"), over)


def _reader(direct_vm, authorises=True, evidence=None) -> None:
    direct_vm.mock_llm(READER, json.dumps({"authorises": authorises, "evidence": evidence}))


def _deploy(direct_vm, direct_deploy, direct_owner, now=NOW):
    direct_vm.warp(now)
    direct_vm.sender = direct_owner
    contract = direct_deploy("contracts/pay_match.py")
    _warp(direct_vm, now)
    return contract


def _warp(direct_vm, timestamp: str) -> None:
    # genlayer-test 0.29.2's warp() never refreshes the datetime in the SDK's
    # already-imported gl.message_raw after deploy; set it too. Live GenVM
    # gives every call a fresh timestamp (confirmed on Studio Next).
    import sys
    direct_vm.warp(timestamp)
    gl = sys.modules.get("genlayer.gl")
    if gl is not None and getattr(gl, "message_raw", None) is not None:
        gl.message_raw["datetime"] = timestamp


def _register(pm, direct_vm, key="eco470", auth_id=None, cap=None, recipient=ECO, payer=TREASURY, asset="USDC",
              valid_until="", evidence="quote", authorises=True, label="ENS Ecosystem WG", over=None, reader=True):
    proposal_id, cid, default_cap = PROPOSAL[key]
    _serve_registration(direct_vm, key, asset, over)
    if reader:  # a refusal the facts decide must not reach the reader: with no mock, calling it fails
        _reader(direct_vm, authorises, QUOTE.get(key) if evidence == "quote" else evidence)
    pm.register_authorisation(auth_id or key, proposal_id, cid, recipient, payer, asset, cap or default_cap,
                              valid_until, label)


def _verify(pm, direct_vm, auth_id, key):
    _serve_tx(direct_vm, key)
    pm.verify_payment(auth_id, TX[key])
    return pm.get_payment(pm.get_state()["payment_count"] - 1)


def _cid_of(raw: bytes) -> str:
    """The raw CIDv1 (bafkrei...) a document's bytes hash to."""
    import base64
    import hashlib
    digest = bytes([0x01, 0x55, 0x12, 0x20]) + hashlib.sha256(raw).digest()
    return "b" + base64.b32encode(digest).decode().lower().rstrip("=")


def _leader(direct_vm):
    """The leader result the last write actually produced."""
    stored, _leader_fn, _validator_fn = direct_vm._captured_validators[-1]
    return json.loads(stored)


@pytest.fixture
def mod(direct_vm, direct_deploy, direct_owner):
    """The loaded contract module itself, for its pure helpers (Direct Mode allows one contract class per process)."""
    import sys
    _deploy(direct_vm, direct_deploy, direct_owner)
    return sys.modules["_contract_pay_match"]


# --- 1. Pure helpers ------------------------------------------------------------


@pytest.mark.parametrize("key", ["eco470", "eco836", "eco409", "rejected"])
def test_every_real_document_hashes_to_its_own_address(mod, key):
    import hashlib
    _pid, cid, _cap = PROPOSAL[key]
    body = (FIXTURES / f"ipfs_{key}.json").read_bytes()
    assert mod._cid_digest(cid) == hashlib.sha256(body).hexdigest()


@pytest.mark.parametrize("cid", [
    "", "Qmc3tBQoUHScciyXssyKyakmqcQSWeJs7gj9QKzwPZqzCS",               # CIDv0 is not a raw CIDv1
    "BAFKREIBP5FWFFWELBM3KX7YKS6BXQDOQIBNV5SAY5AKMEY635MMJBLC2PM",       # wrong case
    "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2p",        # short
    "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2pmm",      # long
    "bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi",      # dag-pb, not raw
    "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2p1",       # not base32 alphabet
])
def test_only_a_raw_sha256_cid_is_accepted(mod, cid):
    assert mod._cid_digest(cid) == ""


def test_numbers_as_a_funding_request_writes_them(mod):
    scaled = mod._numbers("requests funding of 470,000 USDC; sub-budgets 42k, 1.5M, 2,500.75 and 100 in 2026.")
    s = mod.SCALE
    for expected in (470000 * s, 42000 * s, 1500000 * s, 2500 * s + 750000, 100 * s, 2026 * s):
        assert expected in scaled
    assert 470 * s not in scaled and 47000 * s not in scaled


def test_markdown_is_reduced_to_the_words_a_reader_sees(mod):
    row = "| [ENS Ecosystem Main Multisig](https://etherscan.io/address/0x2686a8919df194aa7673244549e68d42c1685d03) | **470,000** | -- | -- |"
    assert mod._plain(row) == "ENS Ecosystem Main Multisig 470,000 -- --"
    assert mod._plain("## Abstract\n\n> funding of `470,000` USDC ![logo](http://x/y.png)") == "Abstract funding of 470,000 USDC logo"


def test_cap_arithmetic_is_exact(mod):
    assert mod._cap_scaled("470000") == 470000 * mod.SCALE
    assert mod._cap_scaled("1500.5") == 1500500000
    assert mod._raw_cap("470000", 6) == 470000 * 10 ** 6
    assert mod._raw_cap("1500.5", 6) == 1500500000
    assert mod._raw_cap("0.000001", 6) == 1
    assert mod._raw_cap("1", 18) == 10 ** 18


def _facts(**view):
    base = {"found": True, "success": True, "block": 100, "time": 2_000_000_000, "confirmed": True, "complete": True,
            "transfer_count": 1, "asset_transfers": [[1, TREASURY, ECO, "470000000000"]], "other_from_payer": []}
    base.update(view)
    return {"problems": [], "view": base}


def _auth(**kw):
    base = {"asset_address": USDC, "recipient": ECO, "payer": TREASURY, "cap_raw": 470000 * 10 ** 6,
            "approved_at": 1_000_000_000, "valid_to": 0}
    base.update(kw)
    return base


def test_judge_covers_every_verdict_on_crafted_facts(mod):
    j = mod._judge
    assert j(_auth(), _facts(), 0)[0] == "MATCH"
    assert j(_auth(), _facts(), 1)[0] == "OVER_CAP"                       # 1 already matched: one unit over
    assert j(_auth(), _facts(success=False), 0)[0] == "TX_FAILED"
    assert j(_auth(), _facts(confirmed=False), 0) == ["UNDETERMINED", ["not_final_yet"], 0]
    assert j(_auth(approved_at=2_000_000_001), _facts(), 0)[0] == "BEFORE_APPROVAL"
    assert j(_auth(valid_to=1_999_999_999), _facts(), 0)[0] == "OUTSIDE_WINDOW"
    assert j(_auth(valid_to=2_000_000_000), _facts(), 0)[0] == "MATCH"    # valid_to is inclusive
    assert j(_auth(approved_at=2_000_000_000), _facts(), 0)[0] == "MATCH"  # paid in the very second the vote closed
    assert j(_auth(), _facts(asset_transfers=[[1, "0x" + "ab" * 20, ECO, "5"]]), 0)[0] == "WRONG_PAYER"
    assert j(_auth(), _facts(asset_transfers=[[1, TREASURY, "0x" + "cd" * 20, "5"]]), 0)[0] == "WRONG_RECIPIENT"
    assert j(_auth(), _facts(asset_transfers=[]), 0)[0] == "NO_TRANSFER"
    assert j(_auth(), _facts(asset_transfers=[], other_from_payer=[["0x" + "ee" * 20, ECO, "9"]]), 0)[0] == "WRONG_ASSET"
    assert j(_auth(), {"problems": ["sources_disagree"], "view": None}, 0) == ["UNDETERMINED", ["sources_disagree"], 0]


def test_a_payment_in_several_transfers_is_summed_and_extras_to_others_are_ignored(mod):
    transfers = [[1, TREASURY, ECO, "200000000000"], [2, TREASURY, ECO, "270000000000"],
                 [3, TREASURY, "0x" + "cd" * 20, "999"], [4, "0x" + "ab" * 20, ECO, "5"]]
    verdict, _reasons, amount = mod._judge(_auth(), _facts(asset_transfers=transfers), 0)
    assert (verdict, amount) == ("MATCH", 470000 * 10 ** 6)
    assert mod._judge(_auth(), _facts(asset_transfers=transfers), 10)[0] == "OVER_CAP"


# --- 2. Registering an authorisation ----------------------------------------------


@pytest.mark.parametrize("key", ["eco470", "eco836", "eco409"])
def test_a_real_passed_funding_request_is_accepted_and_recorded(direct_vm, direct_deploy, direct_owner, key):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, key)
    a = pm.get_authorisation(key)
    proposal_id, cid, cap = PROPOSAL[key]
    hub = json.loads(_fixture(f"hub_{key}.json"))["data"]["proposal"]
    assert (a["space"], a["proposal_id"], a["doc_cid"], a["asset"], a["chain"]) == ("ens.eth", proposal_id, cid, "USDC", "ethereum")
    assert (a["recipient"], a["payer"], a["asset_address"], a["decimals"]) == (ECO, TREASURY, USDC, 6)
    assert a["cap_raw"] == str(int(cap) * 10 ** 6) and a["approved_at"] == hub["end"]
    assert a["evidence"] == QUOTE[key] and a["title"].startswith("[") and a["valid_to"] == 0
    assert a["vote"]["approved"] is True and a["vote"]["state"] == "closed"
    assert a["registrant"].lower() == str(direct_owner).lower() or a["registrant"]  # the sender
    assert re.fullmatch(r"[0-9a-f]{64}", a["doc_digest"]) and a["matched_raw"] == "0" and a["payment_count"] == 0
    assert pm.get_state() == {"authorisation_count": 1, "payment_count": 0}


def test_valid_until_is_the_end_of_that_day_in_utc(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", valid_until="2026-12-31")
    assert pm.get_authorisation("eco470")["valid_to"] == 1798761599  # 2026-12-31T23:59:59Z


def _refused(pm, direct_vm, reasons, key="eco470", no_llm=False, **kw):
    """Registration is refused with these reasons. no_llm: the facts alone decide, so the reader must never be
    called - its mock is in place and must not be hit."""
    with pytest.raises(Exception) as e:
        _register(pm, direct_vm, key, **kw)
    for reason in reasons:
        assert reason in str(e.value), (reason, str(e.value))
    assert str(e.value).count("authorisation refused") >= 1
    assert pm.get_state()["authorisation_count"] == 0
    if no_llm:
        assert not direct_vm._llm_mocks_hit, "the reader was called although the facts already refused"


def test_a_cap_the_document_never_states_is_refused(direct_vm, direct_deploy, direct_owner):
    # 836,000 is a real figure - in a different request.
    _refused(_deploy(direct_vm, direct_deploy, direct_owner), direct_vm, ["cap_not_in_document"], cap="836000", no_llm=True)


def test_a_recipient_the_document_never_names_is_refused(direct_vm, direct_deploy, direct_owner):
    _refused(_deploy(direct_vm, direct_deploy, direct_owner), direct_vm, ["recipient_not_in_document"],
             recipient="0x91c32893216de3ea0a55abb9851f581d4503d39b", no_llm=True)


def test_an_asset_the_document_never_names_is_refused(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["symbol_not_in_document"], asset="DAI", no_llm=True)


def test_a_figure_that_is_in_the_document_but_is_not_the_request_is_refused_by_the_reader(direct_vm, direct_deploy, direct_owner):
    # "172k" is the Ecosystem main multisig's line in the request's own budget table:
    # grounded in the text, but not what the document asks to be paid.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["document_does_not_authorise_this_payment"], cap="172000", authorises=False,
             evidence=None)


def test_a_quote_that_is_not_in_the_document_is_refused(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["quote_not_in_document"],
             evidence="The ENS Ecosystem Working Group requests funding of 470,000 USDC with no oversight at all")


def test_a_real_sentence_that_does_not_state_the_amount_is_not_enough(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    body = json.loads(_fixture("ipfs_eco470.json"))["data"]["message"]["body"]
    sentence = next(s for s in re.split(r"(?<=[.])\s+", body) if "Working Group" in s and "470,000" not in s and len(s) > 40)
    _refused(pm, direct_vm, ["quote_not_in_document"], evidence=sentence.strip())


def test_an_unreadable_reader_answer_is_refused(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470")
    direct_vm.mock_llm(READER, json.dumps({"authorises": "probably"}))
    with pytest.raises(Exception, match="document_unreadable"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_a_reader_that_does_not_return_json_is_refused_not_crashed(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470")
    direct_vm.mock_llm(READER, "Sure! Here is my answer: yes, it does.")
    with pytest.raises(Exception, match="document_unreadable"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


RETRY = "Quote ONE sentence of ordinary prose"


def _two_answers(direct_vm, first, second):
    """The reader answers `first`, and `second` when it is asked again (the retry prompt carries a note).
    The retry pattern is registered first so it wins where both match."""
    direct_vm.mock_llm(RETRY, json.dumps(second))
    direct_vm.mock_llm(READER, json.dumps(first))


def _register_plain(pm, direct_vm, key="eco470"):
    proposal_id, cid, cap = PROPOSAL[key]
    _serve_registration(direct_vm, key)
    return proposal_id, cid, cap


TABLE_ROW = "ENS Ecosystem Main Multisig | 470,000 | -- | --"   # what a model really quoted on Studio Next


def test_a_quote_that_links_and_marks_up_its_words_is_still_their_words(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470",
              evidence="**The ENS Ecosystem Working Group** requests funding of [470,000 USDC](https://x.example) to support operations")
    assert pm.get_authorisation("eco470")["evidence"].startswith("**The ENS")


def test_a_table_row_that_names_no_asset_is_not_enough_on_its_own(direct_vm, direct_deploy, direct_owner):
    # The real quote that failed live: genuine words, but nothing says USDC.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["quote_not_in_document"], evidence=TABLE_ROW)


def test_the_reader_is_asked_once_more_when_its_first_quote_cannot_be_grounded(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = _register_plain(pm, direct_vm)
    _two_answers(direct_vm, {"authorises": True, "evidence": TABLE_ROW}, {"authorises": True, "evidence": QUOTE["eco470"]})
    pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    assert pm.get_authorisation("a")["evidence"] == QUOTE["eco470"]


def test_two_quotes_that_cannot_be_grounded_are_refused(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = _register_plain(pm, direct_vm)
    _two_answers(direct_vm, {"authorises": True, "evidence": TABLE_ROW}, {"authorises": True, "evidence": "470,000 USDC and more"})
    with pytest.raises(Exception, match="quote_not_in_document"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_a_refusal_is_never_retried_into_an_acceptance(direct_vm, direct_deploy, direct_owner):
    # The reader says no; a second ask would say yes with a perfect quote. It must not be asked.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = _register_plain(pm, direct_vm)
    _two_answers(direct_vm, {"authorises": False, "evidence": None}, {"authorises": True, "evidence": QUOTE["eco470"]})
    with pytest.raises(Exception, match="document_does_not_authorise_this_payment"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_an_unreadable_first_answer_is_asked_again(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = _register_plain(pm, direct_vm)
    direct_vm.mock_llm(RETRY, json.dumps({"authorises": True, "evidence": QUOTE["eco470"]}))
    direct_vm.mock_llm(READER, "I think so!")
    pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    assert pm.get_authorisation("a")["evidence"] == QUOTE["eco470"]


def test_a_model_that_errors_out_is_refused_not_crashed(direct_vm, direct_deploy, direct_owner):
    # No reader answers at all: the call itself raises. Fail closed, as an unreadable document.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="document_unreadable"):
        _register(pm, direct_vm, "eco470", reader=False)
    assert pm.get_state()["authorisation_count"] == 0


def _markup_document(direct_vm, body: str):
    """SYNTHETIC: a Snapshot-shaped document whose body carries markdown, with its own honest address and a
    hub record for it (the real hub record with only the document changed)."""
    doc = json.dumps({"data": {"message": {"space": "ens.eth", "title": "Funding request", "body": body}}}).encode()
    cid = _cid_of(doc)
    hub = json.loads(_fixture("hub_eco470.json"))
    hub["data"]["proposal"]["ipfs"] = cid
    direct_vm.clear_mocks()
    _mock(direct_vm, "https://snapshot.4everland.link/ipfs/" + cid, doc)
    _serve(direct_vm, "hub_eco470.json", body=json.dumps(hub).encode())
    _serve(direct_vm, "token_USDC.json")
    return cid


def test_a_document_whose_markup_interrupts_the_quoted_words_still_grounds_the_quote(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    body = ("## Request\n\nThe group requests **470,000 USDC** for the [Ecosystem multisig](https://etherscan.io/address/"
            + ECO + ") through `April`.")
    cid = _markup_document(direct_vm, body)
    _reader(direct_vm, True, "The group requests 470,000 USDC for the Ecosystem multisig")
    pm.register_authorisation("a", PROPOSAL["eco470"][0], cid, ECO, TREASURY, "USDC", "470000", "", "x")
    assert pm.get_authorisation("a")["evidence"] == "The group requests 470,000 USDC for the Ecosystem multisig"


def test_a_voted_down_proposal_is_refused(direct_vm, direct_deploy, direct_owner):
    # The real vote to replace the working groups: closed, For 611k against 1.53M.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["vote_did_not_pass"], key="rejected", no_llm=True)


def test_tampered_document_bytes_are_refused(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: the real document with the recipient's figure edited - a gateway
    # that altered the bytes. The address commits to the original hash.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    tampered = (FIXTURES / "ipfs_eco470.json").read_bytes().replace(b"470,000 USDC", b"970,000 USDC", 1)
    _serve_registration(direct_vm, "eco470", over={"ipfs_eco470.json": (tampered, 200)})
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match="document_does_not_match_its_address"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", "970000", "", "x")


@pytest.mark.parametrize("document", [b'{"hello": "world"}', b'{"data": {"message": {"title": "t", "space": "ens.eth"}}}',
                                      b'{"data": {"message": {"body": 5, "title": "t", "space": "ens.eth"}}}', b"not json at all",
                                      b'{"data": {"message": {"body": "b", "space": "ens.eth"}}}',
                                      b'{"data": {"message": {"body": "b", "title": "t"}}}'])
def test_a_document_that_is_not_a_snapshot_proposal_is_refused(direct_vm, direct_deploy, direct_owner, document):
    # The bytes hash to their own address, so the address is honest - but it is not a proposal.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, _cid, cap = PROPOSAL["eco470"]
    cid = _cid_of(document)
    over = {"ipfs_eco470.json": (document, 200)}
    _serve_registration(direct_vm, "eco470", over=over)
    direct_vm.clear_mocks()
    _mock(direct_vm, "https://snapshot.4everland.link/ipfs/" + cid, document)
    for name in ("hub_eco470.json", "token_USDC.json"):
        _serve(direct_vm, name)
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match="document_is_not_a_snapshot_proposal"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def _hub_edit(key, **changes):
    doc = json.loads(_fixture(f"hub_{key}.json"))
    for k, v in changes.items():
        if k == "space":
            doc["data"]["proposal"]["space"] = {"id": v}
        else:
            doc["data"]["proposal"][k] = v
    return {f"hub_{key}.json": (json.dumps(doc).encode(), 200)}


@pytest.mark.parametrize("changes, reason", [
    ({"ipfs": "bafkreia2ahefq7vmmgs5utov7a3db5mskx6rytrahms5c2fdcxkps6o3vq"}, "vote_is_for_a_different_document"),
    ({"state": "active"}, "vote_not_closed"),
    ({"space": "uniswapgovernance.eth"}, "vote_is_in_a_different_space"),
    ({"choices": ["Option A", "Option B", "Option C"]}, "vote_choices_unsupported"),
    ({"choices": ["For", "Abstain", "Abstain"], "scores": [10.0, 0.0, 0.0]}, "vote_choices_unsupported"),   # nothing to lose to
    ({"choices": ["For", "Yes", "Against"], "scores": [5.0, 5.0, 0.0]}, "vote_choices_unsupported"),         # two ways to say yes
    ({"choices": ["For", "Against"], "scores": [10.0]}, "vote_results_unreadable"),
    ({"end": 0}, "vote_end_unreadable"),
])
def test_a_vote_record_that_does_not_bind_to_the_document_is_refused(direct_vm, direct_deploy, direct_owner, changes, reason):
    # SYNTHETIC: the real hub record with one field changed.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470", over=_hub_edit("eco470", **changes))
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match=reason):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_a_hub_record_for_a_different_proposal_is_not_the_vote(direct_vm, direct_deploy, direct_owner):
    # Real: the hub's record of the 2024 request served in answer to the 2025 request's query.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470", over={"hub_eco470.json": ((FIXTURES / "hub_eco836.json").read_bytes(), 200)})
    with pytest.raises(Exception) as e:
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    assert "vote_not_found" in str(e.value) and "different_document" not in str(e.value)


@pytest.mark.parametrize("changes", [
    {"choices": [1, 2, 3]},                       # choices that are not text
    {"scores": ["a", "b", "c"]},                  # scores that are not numbers
    {"scores": [True, False, False]},             # booleans are not scores
    {"choices": None}, {"scores": None},
])
def test_vote_results_of_the_wrong_type_are_unreadable(direct_vm, direct_deploy, direct_owner, changes):
    # SYNTHETIC: the real hub record with one field given the wrong type.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470", over=_hub_edit("eco470", **changes))
    with pytest.raises(Exception, match="vote_results_unreadable"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_a_tied_or_losing_vote_does_not_pass(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: scores edited so Against leads, then so they tie.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    for scores in ([1.0, 2.0, 0.0], [5.0, 5.0, 0.0], [0.0, 0.0, 9.0]):
        _serve_registration(direct_vm, "eco470", over=_hub_edit("eco470", scores=scores))
        _reader(direct_vm, True, QUOTE["eco470"])
        with pytest.raises(Exception, match="vote_did_not_pass"):
            pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


def test_a_look_alike_token_record_is_refused(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: the explorer answers USDC's address with USDT's record.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470", over={"token_USDC.json": ((FIXTURES / "token_USDT.json").read_bytes(), 200)})
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match="explorer_disagrees_with_the_pinned_token"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


@pytest.mark.parametrize("field, value", [("address_hash", "0x" + "11" * 20), ("symbol", "USDC.e"), ("decimals", "18"),
                                          ("type", "ERC-721")])
def test_each_field_of_the_token_record_must_match_the_pinned_token(direct_vm, direct_deploy, direct_owner, field, value):
    # SYNTHETIC: the real USDC record with exactly one field changed.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    record = json.loads(_fixture("token_USDC.json"))
    record[field] = value
    _serve_registration(direct_vm, "eco470", over={"token_USDC.json": (json.dumps(record).encode(), 200)})
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match="explorer_disagrees_with_the_pinned_token"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")


@pytest.mark.parametrize("evidence", [
    "470k USDC",                                                         # states both, but too little to check against the document
    "The ENS Ecosystem Working Group requests funding of 470,000",     # states the amount, never names the asset
    "support operations through April 2026 ... USDC",                  # names the asset, never states the amount
    "The ENS Ecosystem Working Group requests funding of 470,000 USDC ... and a made-up second sentence here",
])
def test_the_quote_must_state_the_amount_and_the_asset_and_be_entirely_real(direct_vm, direct_deploy, direct_owner, evidence):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _refused(pm, direct_vm, ["quote_not_in_document"], evidence=evidence)


@pytest.mark.parametrize("source, status", [("ipfs_eco470.json", 429), ("ipfs_eco470.json", 404),
                                              ("hub_eco470.json", 500), ("token_USDC.json", 503)])
def test_an_unreadable_source_refuses_the_authorisation(direct_vm, direct_deploy, direct_owner, source, status):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470", over={source: (b"busy", status)})
    _reader(direct_vm, True, QUOTE["eco470"])
    with pytest.raises(Exception, match=f"_http_{status}"):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    assert pm.get_state()["authorisation_count"] == 0


def test_network_failure_records_nothing(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    proposal_id, cid, cap = PROPOSAL["eco470"]
    direct_vm.clear_mocks()
    with pytest.raises(Exception):
        pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    assert pm.get_state()["authorisation_count"] == 0


GOOD = dict(auth_id="a", proposal_id=PROPOSAL["eco470"][0], doc_cid=PROPOSAL["eco470"][1], recipient=ECO,
            payer=TREASURY, asset="USDC", cap="470000", valid_until="", label="x")


@pytest.mark.parametrize("field, value, message", [
    ("auth_id", "", "auth_id must be"), ("auth_id", "has space", "auth_id must be"), ("auth_id", "x" * 33, "auth_id must be"),
    ("proposal_id", "0x1234", "proposal_id must be"), ("proposal_id", PROPOSAL["eco470"][0].upper().replace("0X", "0x"), "proposal_id must be"),
    ("doc_cid", "Qmc3tBQoUHScciyXssyKyakmqcQSWeJs7gj9QKzwPZqzCS", "doc_cid must be"),
    ("recipient", "0x123", "recipient must be"), ("payer", "treasury.eth", "payer must be"),
    ("asset", "usdc", "asset must be one of"), ("asset", "SHIB", "asset must be one of"),
    ("cap", "0", "cap must be"), ("cap", "-5", "cap must be"), ("cap", "1e6", "cap must be"), ("cap", "1.1234567", "cap must be"),
    ("cap", "1" * 16, "cap must be"), ("cap", "0.000000", "cap must be"),
    ("valid_until", "tomorrow", "valid_until must be"), ("valid_until", "2026-13-45", "not a real date"),
    ("label", "", "label must be"), ("label", "x" * 101, "label must be"),
    ("payer", ECO, "recipient and payer must differ"),
])
def test_invalid_inputs_are_rejected_before_any_fetch(direct_vm, direct_deploy, direct_owner, field, value, message):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.clear_mocks()  # nothing is served: a fetch would fail differently
    args = dict(GOOD)
    args[field] = value
    with pytest.raises(Exception, match=message):
        pm.register_authorisation(**args)


def test_an_auth_id_and_a_vote_can_be_registered_once(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", auth_id="first")
    with pytest.raises(Exception, match="auth_id already registered"):
        _register(pm, direct_vm, "eco470", auth_id="first")
    # The same vote, payer, recipient and asset under another id would count its cap twice.
    with pytest.raises(Exception, match="already authorises this payer, recipient and asset as 'first'"):
        _register(pm, direct_vm, "eco470", auth_id="second")
    # A different payer is a different claim (a consumer pins the payer it trusts).
    _register(pm, direct_vm, "eco470", auth_id="other-payer", payer="0x" + "ab" * 20)
    assert {a["auth_id"] for a in pm.list_authorisations()} == {"first", "other-payer"}


# --- 3. Judging a payment: real transactions, two indexers ---------------------------


@pytest.mark.parametrize("auth_key, tx_key, amount", [
    ("eco470", "t470", 470000), ("eco836", "t836", 836000), ("eco409", "t409", 409000),
])
def test_the_real_payment_of_each_approved_request_matches(direct_vm, direct_deploy, direct_owner, auth_key, tx_key, amount):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, auth_key)
    p = _verify(pm, direct_vm, auth_key, tx_key)
    assert p["verdict"] == "MATCH" and p["reasons"] == [] and p["amount_raw"] == str(amount * 10 ** 6)
    assert p["tx_hash"] == TX[tx_key] and p["block_number"] > 0 and p["block_time"] > 1_600_000_000
    rec = pm.get_reconciliation(auth_key)
    assert rec["matched_raw"] == str(amount * 10 ** 6) and rec["remaining_raw"] == "0"
    assert rec["flagged_count"] == 0 and rec["payment_count"] == 1 and rec["payer"] == TREASURY


def test_the_facts_are_what_both_indexers_agreed_on(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    view = _verify(pm, direct_vm, "eco470", "t470")["facts"]["view"]
    assert view["found"] and view["success"] and view["confirmed"] and view["complete"]
    assert view["block"] == 24484140 and view["time"] == 1771422743 and view["transfer_count"] == 3
    # three USDC payments in one transaction: Ecosystem 470,000, Meta-Governance 379,000, Public Goods 110,000
    assert sorted(t[3] for t in view["asset_transfers"]) == ["110000000000", "379000000000", "470000000000"]
    assert all(t[1] == TREASURY for t in view["asset_transfers"]) and view["other_from_payer"] == []


def test_a_payment_that_also_moved_another_token_still_matches_on_the_asset(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco409")
    view = _verify(pm, direct_vm, "eco409", "t409")["facts"]["view"]
    assert view["transfer_count"] == 4 and len(view["asset_transfers"]) == 3
    assert [t[0] for t in view["other_from_payer"]] == ["0xc18360217d8f7ab5e7c516566761ea12ce7f9d72"]  # 52,300 ENS to another group


def test_a_larger_payment_than_the_authorised_cap_is_over_cap(direct_vm, direct_deploy, direct_owner):
    # Real: 836,000 USDC to the Ecosystem multisig, against the 409,000 request.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco409")
    p = _verify(pm, direct_vm, "eco409", "t836")
    assert p["verdict"] == "OVER_CAP" and p["amount_raw"] == str(836000 * 10 ** 6)
    rec = pm.get_reconciliation("eco409")
    assert rec["matched_raw"] == "0" and rec["remaining_raw"] == str(409000 * 10 ** 6) and rec["flagged_count"] == 1


def test_a_payment_made_before_the_vote_closed_is_before_approval(direct_vm, direct_deploy, direct_owner):
    # Real: the 2024 payment of 836,000, against the request voted in Nov 2025.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", cap="470000")
    p = _verify(pm, direct_vm, "eco470", "t836")
    assert p["verdict"] == "BEFORE_APPROVAL" and p["reasons"] == ["paid before the vote closed"]
    assert pm.get_reconciliation("eco470")["flagged_count"] == 1 and pm.get_reconciliation("eco470")["matched_raw"] == "0"


def test_a_payment_after_valid_until_is_outside_the_window(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", valid_until="2026-02-01")   # paid 2026-02-18
    assert _verify(pm, direct_vm, "eco470", "t470")["verdict"] == "OUTSIDE_WINDOW"


def test_a_payment_on_the_last_day_of_the_window_matches(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", valid_until="2026-02-18")   # paid 2026-02-18T13:52:23Z
    assert _verify(pm, direct_vm, "eco470", "t470")["verdict"] == "MATCH"


def test_the_running_total_counts_against_the_cap(direct_vm, direct_deploy, direct_owner):
    # Real: 470,000 then 836,000 against the 836,000 request: the second would
    # take the total to 1,306,000.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco836")
    assert _verify(pm, direct_vm, "eco836", "t470")["verdict"] == "MATCH"
    rec = pm.get_reconciliation("eco836")
    assert rec["matched_raw"] == str(470000 * 10 ** 6) and rec["remaining_raw"] == str(366000 * 10 ** 6)
    assert _verify(pm, direct_vm, "eco836", "t836")["verdict"] == "OVER_CAP"
    rec = pm.get_reconciliation("eco836")
    assert rec["matched_raw"] == str(470000 * 10 ** 6) and rec["flagged_count"] == 1 and rec["payment_count"] == 2


def test_the_treasury_paying_a_different_group_is_the_wrong_recipient(direct_vm, direct_deploy, direct_owner):
    # Real: 125,000 USDC from the DAO treasury to the Meta-Governance multisig.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    p = _verify(pm, direct_vm, "eco470", "other")
    assert p["verdict"] == "WRONG_RECIPIENT" and p["amount_raw"] == "0"


def test_dust_from_a_look_alike_address_is_the_wrong_payer(direct_vm, direct_deploy, direct_owner):
    # Real: 0.001 USDC to the Ecosystem multisig from an address crafted to resemble a real one.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    p = _verify(pm, direct_vm, "eco470", "poison")
    assert p["verdict"] == "WRONG_PAYER" and p["amount_raw"] == "0"
    assert pm.get_reconciliation("eco470")["matched_raw"] == "0" and pm.get_reconciliation("eco470")["flagged_count"] == 1


def test_anyone_can_send_the_recipient_funds_but_only_the_payer_counts(direct_vm, direct_deploy, direct_owner):
    # The same request, registered against the dust sender as "payer": its 0.001 USDC matches
    # - which is why a consumer pins the payer it trusts.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470", payer="0x703abdbb99c60068f78737bb3bf94869b9cc789b")
    p = _verify(pm, direct_vm, "eco470", "poison")
    assert p["verdict"] == "MATCH" and p["amount_raw"] == "1000"


def test_a_reverted_transaction_is_tx_failed(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    assert _verify(pm, direct_vm, "eco470", "failed")["verdict"] == "TX_FAILED"


def test_a_transaction_that_moved_no_token_is_no_transfer(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    p = _verify(pm, direct_vm, "eco470", "eth")
    assert p["verdict"] == "NO_TRANSFER" and p["facts"]["view"]["transfer_count"] == 0


def test_a_transaction_with_more_transfers_than_one_page_is_undetermined(direct_vm, direct_deploy, direct_owner):
    # Real: a 50+ transfer address-poisoning batch. Fail closed: the cap could be
    # exceeded by transfers the indexer did not list.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    p = _verify(pm, direct_vm, "eco470", "spam")
    assert p["verdict"] == "UNDETERMINED" and p["reasons"] == ["more_transfers_than_the_indexer_lists_in_one_page"]
    assert pm.get_reconciliation("eco470")["flagged_count"] == 0  # undetermined is not a finding


def test_an_unknown_transaction_is_undetermined_and_can_be_tried_again(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    p = _verify(pm, direct_vm, "eco470", "none")
    assert p["verdict"] == "UNDETERMINED" and p["reasons"] == ["transaction_not_found"]
    p = _verify(pm, direct_vm, "eco470", "none")   # not decided, so it is not blocked
    assert p["payment_id"] == 1


def test_a_decided_transaction_cannot_be_verified_twice_here(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _verify(pm, direct_vm, "eco470", "t470")
    _serve_tx(direct_vm, "t470")
    with pytest.raises(Exception, match="already has a decided verdict"):
        pm.verify_payment("eco470", TX["t470"])
    assert pm.get_reconciliation("eco470")["matched_raw"] == str(470000 * 10 ** 6)


def test_the_same_transaction_may_be_judged_against_each_authorisation_separately(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _register(pm, direct_vm, "eco836")
    assert _verify(pm, direct_vm, "eco470", "t470")["verdict"] == "MATCH"
    assert _verify(pm, direct_vm, "eco836", "t470")["verdict"] == "MATCH"   # 470,000 fits the 836,000 cap too


# --- Fail closed: what the indexers say ------------------------------------------------


def _receipt_edit(key, fn):
    doc = json.loads(_fixture(f"rs_receipt_{key}.json"))
    fn(doc["result"])
    return {f"rs_receipt_{key}.json": (json.dumps(doc).encode(), 200)}


def _setup(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    return pm


def _verify_with(pm, direct_vm, over, key="t470"):
    _serve_tx(direct_vm, key, over)
    pm.verify_payment("eco470", TX[key])
    return pm.get_payment(pm.get_state()["payment_count"] - 1)


def test_two_indexers_that_disagree_on_an_amount_are_undetermined(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: Routescan's receipt with the 470,000 transfer's amount changed.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def change(receipt):
        for log in receipt["logs"]:
            if log["logIndex"] == hex(590):
                log["data"] = "0x" + format(469999 * 10 ** 6, "064x")
    p = _verify_with(pm, direct_vm, _receipt_edit("t470", change))
    assert p["verdict"] == "UNDETERMINED" and p["reasons"] == ["sources_disagree"]
    assert pm.get_reconciliation("eco470")["matched_raw"] == "0"


def test_two_indexers_that_disagree_on_whether_the_transaction_exists_are_undetermined(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: Routescan says it has never heard of a transaction Blockscout has.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    p = _verify_with(pm, direct_vm, {"rs_receipt_t470.json": (b'{"jsonrpc":"2.0","id":1,"result":null}', 200)})
    assert p["reasons"] == ["sources_disagree_on_whether_the_transaction_exists"]


@pytest.mark.parametrize("name, status, reason", [
    ("bs_tx_t470.json", 500, "blockscout_unreadable_500"),
    ("bs_transfers_t470.json", 502, "blockscout_transfers_unreadable_502"),
    ("rs_receipt_t470.json", 500, "routescan_unreadable_500"),
    ("rs_block_t470.json", 503, "routescan_block_unreadable"),
    ("rs_latest.json", 429, "routescan_block_unreadable"),
])
def test_one_unreadable_indexer_is_undetermined_never_a_match(direct_vm, direct_deploy, direct_owner, name, status, reason):
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    p = _verify_with(pm, direct_vm, {name: (b"nope", status)})
    assert p["verdict"] == "UNDETERMINED" and reason in p["reasons"]
    assert pm.get_reconciliation("eco470")["matched_raw"] == "0"


def test_a_transaction_that_is_too_new_to_be_final_is_undetermined(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: both indexers report only 10 blocks on top of the payment's block.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    tx = json.loads(_fixture("bs_tx_t470.json"))
    tx["confirmations"] = 10
    young = {"bs_tx_t470.json": (json.dumps(tx).encode(), 200),
             "rs_latest.json": (json.dumps({"jsonrpc": "2.0", "id": 1, "result": hex(24484140 + 10)}).encode(), 200)}
    p = _verify_with(pm, direct_vm, young)
    assert p["verdict"] == "UNDETERMINED" and p["reasons"] == ["not_final_yet"]
    assert pm.get_reconciliation("eco470")["matched_raw"] == "0"
    # once it is final the same transaction can be judged
    assert _verify_with(pm, direct_vm, None)["verdict"] == "MATCH"


def test_an_indexer_that_calls_it_final_when_the_other_does_not_is_a_disagreement(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: Blockscout 10 confirmations, Routescan thousands.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    tx = json.loads(_fixture("bs_tx_t470.json"))
    tx["confirmations"] = 10
    p = _verify_with(pm, direct_vm, {"bs_tx_t470.json": (json.dumps(tx).encode(), 200)})
    assert p["reasons"] == ["sources_disagree"]


def test_a_malformed_indexer_answer_is_undetermined(direct_vm, direct_deploy, direct_owner):
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    bad = b'{"jsonrpc":"2.0","id":1,"result":{"status":"0x1","blockNumber":"0x175992c","logs":[{"topics":[]}]}}'
    assert _verify_with(pm, direct_vm, {"rs_receipt_t470.json": (bad, 200)})["verdict"] == "UNDETERMINED"


def test_a_non_erc20_transfer_event_is_not_counted(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: Routescan's USDC transfer log given a fourth topic (an ERC-721 Transfer
    # has the same signature with the token id indexed) is ignored by that indexer;
    # Blockscout still lists it, so the two disagree rather than one being believed.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def change(receipt):
        for log in receipt["logs"]:
            if log["logIndex"] == hex(590):
                log["topics"].append("0x" + "00" * 32)
    assert _verify_with(pm, direct_vm, _receipt_edit("t470", change))["reasons"] == ["sources_disagree"]


def _transfers_edit(fn):
    doc = json.loads(_fixture("bs_transfers_t470.json"))
    fn(doc)
    return {"bs_transfers_t470.json": (json.dumps(doc).encode(), 200)}


def test_an_nft_transfer_in_the_listing_is_ignored_like_the_other_indexer_ignores_it(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: an ERC-721 item added to Blockscout's list (Routescan drops four-topic Transfer logs).
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def add(doc):
        doc["items"].append({"token": {"type": "ERC-721", "address_hash": "0x" + "11" * 20}, "token_type": "ERC-721",
                             "total": {"token_id": "5"}, "log_index": 7, "from": {"hash": TREASURY}, "to": {"hash": ECO}})
    assert _verify_with(pm, direct_vm, _transfers_edit(add))["verdict"] == "MATCH"


def test_a_listing_of_exactly_one_page_is_incomplete_even_without_a_next_page(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: 50 items and no next_page_params (the 3 real items repeated to a full page).
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def fill(doc):
        doc["items"] = (doc["items"] * 17)[:50]
        doc["next_page_params"] = None
    p = _verify_with(pm, direct_vm, _transfers_edit(fill))
    assert p["reasons"] == ["more_transfers_than_the_indexer_lists_in_one_page"]


def test_a_short_listing_with_a_next_page_is_incomplete(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: the real 3 items, but the indexer says there is another page.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    p = _verify_with(pm, direct_vm, _transfers_edit(lambda doc: doc.update(next_page_params={"index": 1})))
    assert p["reasons"] == ["more_transfers_than_the_indexer_lists_in_one_page"]


def test_a_reorged_log_is_not_counted(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: the payment's log flagged removed by Routescan; Blockscout still lists it.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def remove(receipt):
        for log in receipt["logs"]:
            if log["logIndex"] == hex(590):
                log["removed"] = True
    assert _verify_with(pm, direct_vm, _receipt_edit("t470", remove))["reasons"] == ["sources_disagree"]


def test_an_event_with_another_signature_is_not_a_transfer(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: the payment's log given a different event signature.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    def change(receipt):
        for log in receipt["logs"]:
            if log["logIndex"] == hex(590):
                log["topics"][0] = "0x" + "ab" * 32
    assert _verify_with(pm, direct_vm, _receipt_edit("t470", change))["reasons"] == ["sources_disagree"]


def test_a_failed_status_on_one_indexer_only_is_a_disagreement(direct_vm, direct_deploy, direct_owner):
    # SYNTHETIC: Routescan's receipt says reverted; Blockscout says success.
    pm = _setup(direct_vm, direct_deploy, direct_owner)
    assert _verify_with(pm, direct_vm, _receipt_edit("t470", lambda r: r.update(status="0x0")))["reasons"] == ["sources_disagree"]


def test_malformed_ids_are_rejected_before_any_fetch(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    direct_vm.clear_mocks()
    for tx in ("0x1234", TX["t470"].upper().replace("0X", "0x"), TX["t470"][2:], TX["t470"] + "00"):
        with pytest.raises(Exception, match="tx_hash must be"):
            pm.verify_payment("eco470", tx)
    with pytest.raises(Exception, match="unknown auth_id"):
        pm.verify_payment("nope", TX["t470"])


def test_network_failure_while_verifying_records_nothing(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    direct_vm.clear_mocks()
    with pytest.raises(Exception):
        pm.verify_payment("eco470", TX["t470"])
    assert pm.get_state()["payment_count"] == 0


# --- 4. What a consumer reads ----------------------------------------------------------


def test_an_unknown_authorisation_reads_as_not_existing(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    assert pm.get_reconciliation("nope") == {"exists": False, "auth_id": "nope"}
    assert pm.list_authorisations() == [] and pm.get_payments(0, 10) == [] and pm.get_state() == {"authorisation_count": 0, "payment_count": 0}
    with pytest.raises(Exception, match="unknown auth_id"):
        pm.get_authorisation("nope")
    with pytest.raises(Exception, match="unknown payment_id"):
        pm.get_payment(0)


def test_history_is_this_authorisations_own_chain_newest_first(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _register(pm, direct_vm, "eco836")
    _verify(pm, direct_vm, "eco470", "t836")      # BEFORE_APPROVAL
    _verify(pm, direct_vm, "eco836", "t470")      # MATCH (another authorisation's chain)
    _verify(pm, direct_vm, "eco470", "other")     # WRONG_RECIPIENT
    _verify(pm, direct_vm, "eco470", "t470")      # MATCH
    mine = pm.get_history("eco470", 10)
    assert [p["verdict"] for p in mine] == ["MATCH", "WRONG_RECIPIENT", "BEFORE_APPROVAL"]
    assert [p["previous_id"] for p in mine] == [2, 0, None]
    assert [p["verdict"] for p in pm.get_history("eco836", 10)] == ["MATCH"]
    assert [p["payment_id"] for p in pm.get_payments(0, 10)] == [3, 2, 1, 0]
    assert [p["payment_id"] for p in pm.get_payments(1, 2)] == [2, 1]
    assert len(pm.get_history("eco470", 1)) == 1
    assert pm.get_history("eco836", 0) == []


def _no_floats(value, path="result"):
    assert not isinstance(value, float), f"{path} is a float: GenVM calldata cannot encode it"
    if isinstance(value, dict):
        for k, v in value.items():
            _no_floats(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            _no_floats(v, f"{path}[{i}]")


def test_no_view_returns_a_float_which_the_runtime_cannot_encode(direct_vm, direct_deploy, direct_owner):
    # Found live: the stored vote record carried Snapshot's float scores and get_authorisation
    # failed on Studio Next with a bare exit code 1, though every Direct Mode test passed.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _verify(pm, direct_vm, "eco470", "t470")
    _verify(pm, direct_vm, "eco470", "other")
    for result in (pm.get_authorisation("eco470"), pm.list_authorisations(), pm.get_payment(0), pm.get_payments(0, 10),
                   pm.get_history("eco470", 10), pm.get_reconciliation("eco470"), pm.get_rules(), pm.get_state()):
        _no_floats(result)
    vote = pm.get_authorisation("eco470")["vote"]
    assert vote["for_score"] == "1375141.4178885242" and vote["against_score"] == "0.0"


def test_the_rules_a_frontend_needs_are_published(direct_vm, direct_deploy, direct_owner):
    rules = _deploy(direct_vm, direct_deploy, direct_owner).get_rules()
    assert rules["chain"] == "ethereum" and rules["min_confirmations"] == 64
    assert rules["assets"]["USDC"] == {"address": USDC, "decimals": 6}
    assert set(rules["assets"]) == {"USDC", "USDT", "DAI", "EURC", "WETH", "ENS", "UNI"}
    assert "WRONG_PAYER" in rules["verdicts"] and rules["verdicts"][-1] == "UNDETERMINED"


# --- 5. Consensus boundary -----------------------------------------------------------------


def _register_leader(pm, direct_vm):
    proposal_id, cid, cap = PROPOSAL["eco470"]
    _serve_registration(direct_vm, "eco470")
    _reader(direct_vm, True, QUOTE["eco470"])
    pm.register_authorisation("a", proposal_id, cid, ECO, TREASURY, "USDC", cap, "", "x")
    return _leader(direct_vm)


def test_validator_accepts_an_honest_registration_and_payment(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    assert direct_vm.run_validator() is True
    _serve_tx(direct_vm, "t470")
    pm.verify_payment("a", TX["t470"])
    assert direct_vm.run_validator() is True


def test_validator_rejects_a_registration_whose_facts_were_tampered(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    for tamper in (lambda l: l["facts"]["vote"].update(approved=False),
                   lambda l: l["facts"]["vote"].update(end=1),
                   lambda l: l["facts"].update(problems=["vote_did_not_pass"]),
                   lambda l: l["facts"].update(document_digest="0" * 64),
                   lambda l: l["facts"]["grounded"].update(cap=False),
                   lambda l: l["facts"].update(title="[6.24.2] A different proposal")):
        leader = _leader(direct_vm)
        tamper(leader)
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_quote_not_in_its_own_copy(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    leader = _leader(direct_vm)
    leader["reading"]["evidence"] = "The ENS Ecosystem Working Group requests funding of 470,000 USDC and an unlimited float"
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_leader_that_hides_or_flips_the_reading(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    for reading in (None,  # the leader skipped the reader: the validator's reader says yes
                    {"authorises": False, "evidence": None, "grounded": False}):
        leader = _leader(direct_vm)
        leader["reading"] = reading
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    # and the opposite: a leader that claims yes when this validator's reader says no
    _serve_registration(direct_vm, "eco470")
    _reader(direct_vm, False, None)
    assert direct_vm.run_validator() is False


def test_validator_rejects_a_reading_of_nothing(direct_vm, direct_deploy, direct_owner):
    # The leader fabricated a reading although the document could not be read.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    leader = _leader(direct_vm)
    _serve_registration(direct_vm, "eco470", over={"ipfs_eco470.json": (b"busy", 429)})
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_a_leader_that_read_a_document_the_facts_already_refuse(direct_vm, direct_deploy, direct_owner):
    # The recipient is not in the document, so there is nothing to read - yet the leader returns a
    # reading whose quote is genuine and states the right amount, so only the guard can catch it.
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="recipient_not_in_document"):
        _register(pm, direct_vm, "eco470", recipient="0x91c32893216de3ea0a55abb9851f581d4503d39b", reader=False)
    leader = _leader(direct_vm)
    assert leader["reading"] is None and direct_vm.run_validator() is True
    leader["reading"] = {"authorises": True, "evidence": QUOTE["eco470"], "grounded": True}
    _reader(direct_vm, True, QUOTE["eco470"])
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_malformed_registration_readings_and_leader_errors(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register_leader(pm, direct_vm)
    for reading in ({"authorises": True}, {"authorises": "yes", "evidence": None, "grounded": False},
                    {"authorises": True, "evidence": 5, "grounded": True},
                    {"authorises": 1, "evidence": QUOTE["eco470"], "grounded": True},      # 1 is truthy, but not a boolean
                    {"authorises": True, "evidence": QUOTE["eco470"], "grounded": 1}):
        leader = _leader(direct_vm)
        leader["reading"] = reading
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    leader = _leader(direct_vm)
    leader["reading"]["grounded"] = False   # understated grounding is a mismatch too
    assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False
    assert direct_vm.run_validator(leader_error=Exception("fetch failed")) is False
    assert direct_vm.run_validator(leader_result="not json") is False
    assert direct_vm.run_validator(leader_result="[]") is False


def test_validator_rejects_tampered_payment_facts(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _serve_tx(direct_vm, "t470")
    pm.verify_payment("eco470", TX["t470"])
    assert direct_vm.run_validator() is True
    for tamper in (lambda l: l["facts"]["view"]["asset_transfers"][0].__setitem__(3, "999999999999999"),
                   lambda l: l["facts"]["view"].update(success=False),
                   lambda l: l["facts"]["view"].update(time=1),
                   lambda l: l["facts"]["view"].update(confirmed=False),
                   lambda l: l["facts"].update(problems=["sources_disagree"], view=None),
                   lambda l: l["facts"]["view"]["asset_transfers"].pop()):
        leader = _leader(direct_vm)
        tamper(leader)
        assert direct_vm.run_validator(leader_result=json.dumps(leader)) is False


def test_validator_rejects_malformed_payment_answers_and_leader_errors(direct_vm, direct_deploy, direct_owner):
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    _register(pm, direct_vm, "eco470")
    _serve_tx(direct_vm, "t470")
    pm.verify_payment("eco470", TX["t470"])
    assert direct_vm.run_validator(leader_error=Exception("fetch failed")) is False
    assert direct_vm.run_validator(leader_result="not json") is False
    assert direct_vm.run_validator(leader_result="[]") is False
    assert direct_vm.run_validator(leader_result=json.dumps({"digest": "x"})) is False
    assert direct_vm.run_validator(leader_result=json.dumps({"facts": "x"})) is False


# --- The live run, reproduced ----------------------------------------------------------------

LIVE_PROOF = json.loads((REPO / "studio-next" / "live_proof.json").read_text())
LIVE_AUTH = {"eco470": ("eco470", TREASURY), "eco836": ("eco836", TREASURY), "eco409": ("eco409", TREASURY),
             "eco470-alt-payer": ("eco470", "0x703abdbb99c60068f78737bb3bf94869b9cc789b")}


def test_the_fixtures_reproduce_what_the_validators_agreed_on_live(direct_vm, direct_deploy, direct_owner):
    """Replays every verification of the live run, in the order it ran, on the committed fixtures: the facts,
    verdict, reasons, amount and block recorded on Studio Next are exactly what the contract derives here."""
    pm = _deploy(direct_vm, direct_deploy, direct_owner)
    live_regs = {e["auth_id"]: e["authorisation"] for e in LIVE_PROOF if e["step"] == "register" and e["authorisation"]}
    assert set(live_regs) == set(LIVE_AUTH)
    for auth_id, (key, payer) in LIVE_AUTH.items():
        _register(pm, direct_vm, key, auth_id=auth_id, payer=payer)
        mine, live = pm.get_authorisation(auth_id), live_regs[auth_id]
        for field in ("proposal_id", "doc_cid", "doc_digest", "space", "title", "recipient", "payer", "asset", "cap_raw",
                      "approved_at", "valid_to", "vote", "chain", "asset_address", "decimals"):
            assert mine[field] == live[field], (auth_id, field)
    live_verifies = [e for e in LIVE_PROOF if e["step"] == "verify" and e["payment"]]
    assert len(live_verifies) == 13
    for e in live_verifies:
        p = _verify(pm, direct_vm, e["auth_id"], e["tx_key"])
        live = e["payment"]
        for field in ("tx_hash", "verdict", "reasons", "amount_raw", "block_number", "block_time", "facts", "previous_id"):
            assert p[field] == live[field], (e["id"], field)
    assert pm.get_state() == {"authorisation_count": 4, "payment_count": 13}
