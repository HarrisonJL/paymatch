"""
Direct Mode tests for TrancheGate.

Direct Mode can't simulate cross-contract calls without a "glsim" hook (the
same documented limitation as this account's earlier consumers), so release()'s
read of PayMatch.get_reconciliation() is proven live instead - an allowed
release and refused ones, all linked in CONTRACT.md. What's tested here is
everything that runs before that call.
"""

import pytest

PM_ADDRESS = "0x" + "44" * 20   # never actually called in these tests
TREASURY = "0xFe89cc7aBB2C4183683ab71653C4cdc9B02D44b7"


def _deploy(direct_vm, direct_deploy, owner, payer=TREASURY):
    direct_vm.sender = owner
    return direct_deploy("contracts/tranche_gate.py", PM_ADDRESS, payer)


def test_config_and_empty_state(direct_vm, direct_deploy, direct_owner):
    gate = _deploy(direct_vm, direct_deploy, direct_owner)
    cfg = gate.get_config()
    assert cfg["paymatch_address"].lower() == PM_ADDRESS and cfg["release_count"] == 0
    assert cfg["trusted_payer"] == TREASURY.lower()          # stored lower-case, compared lower-case
    assert gate.get_plan("any") == {"auth_id": "any", "released_count": 0, "released_raw": "0"}
    assert gate.get_releases(0, 10) == []


@pytest.mark.parametrize("payer", ["", "treasury.eth", "0x123", "0x" + "zz" * 20])
def test_the_trusted_payer_must_be_an_address(direct_vm, direct_deploy, direct_owner, payer):
    with pytest.raises(Exception, match="trusted_payer must be a 0x address"):
        _deploy(direct_vm, direct_deploy, direct_owner, payer)


def test_only_the_owner_can_release(direct_vm, direct_deploy, direct_owner, direct_alice):
    gate = _deploy(direct_vm, direct_deploy, direct_owner)
    direct_vm.sender = direct_alice
    with pytest.raises(Exception, match="only the owner can release tranches"):
        gate.release("eco470", 1, 100)


def test_zero_amount_is_rejected_before_any_cross_contract_call(direct_vm, direct_deploy, direct_owner):
    gate = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="amount must be positive"):
        gate.release("eco470", 1, 0)


@pytest.mark.parametrize("tranche", [0, 2, 7])
def test_tranches_are_released_in_order_starting_at_one(direct_vm, direct_deploy, direct_owner, tranche):
    gate = _deploy(direct_vm, direct_deploy, direct_owner)
    with pytest.raises(Exception, match="the next is 1"):
        gate.release("eco470", tranche, 100)
