# v0.1.0
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

# TrancheGate - a minimal consumer of PayMatch, proving a verdict can gate a
# grant's tranches on-chain. A tranche is only released if, in PayMatch's
# own record of the authorisation:
#   - the authorisation names the one treasury this gate trusts as payer
#     (PayMatch's payer is the registrant's claim, so the consumer pins it),
#   - nothing paid against it has been flagged (over its cap, before its
#     vote, from the wrong payer, to the wrong recipient...),
#   - every tranche already released has really been paid and matched,
#   - the authorisation's window has not closed, and
#   - this tranche fits what is left of the authorised cap.
# Tranches are released in order, by the gate's owner. Anything else reverts.
#
# GenVM v0.2.11 conventions (locally tested source of truth);
# contracts/tranche_gate_studio_next.py is the deployed port.
# Header must end in a blank line (real GenVM v0.2.11 requirement).

from genlayer import *
import datetime
import re

MAX_PAGE_LIMIT = 50


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise gl.vm.UserError(message)


def _now() -> datetime.datetime:
    return datetime.datetime.fromisoformat(gl.message_raw['datetime'])


@allow_storage
class Release:
    auth_id: str
    tranche: u32
    amount_raw: u256
    released_by: Address
    released_at: datetime.datetime


@allow_storage
class Plan:
    released_count: u32
    released_raw: u256


class TrancheGate(gl.Contract):
    owner: Address
    paymatch_address: Address
    trusted_payer: str  # lowercase 0x address of the treasury whose payments count
    releases: DynArray[Release]
    plans: TreeMap[str, Plan]

    def __init__(self, paymatch_address: str, trusted_payer: str) -> None:
        _require(re.fullmatch(r"0x[0-9a-fA-F]{40}", trusted_payer) is not None, "trusted_payer must be a 0x address")
        self.owner = gl.message.sender_address
        self.paymatch_address = Address(paymatch_address)
        self.trusted_payer = trusted_payer.casefold()

    # Owner only: the gate demonstrates a consumer, it does not move funds.
    @gl.public.write
    def release(self, auth_id: str, tranche: u32, amount_raw: u256) -> None:
        _require(gl.message.sender_address == self.owner, "only the owner can release tranches")
        _require(amount_raw > 0, "amount must be positive")
        plan = self.plans.get_or_insert_default(auth_id)
        _require(tranche == plan.released_count + 1,
                 f"tranches are released in order: the next is {plan.released_count + 1}")
        rec = gl.get_contract_at(self.paymatch_address).view().get_reconciliation(auth_id)
        _require(rec["exists"], f"{auth_id!r} refused: PayMatch has no such authorisation")
        _require(rec["payer"] == self.trusted_payer,
                 f"{auth_id!r} refused: its payer {rec['payer']} is not the treasury this gate trusts")
        _require(rec["flagged_count"] == 0,
                 f"{auth_id!r} refused: a payment against it was flagged ({rec['flagged_count']})")
        _require(not rec["valid_to"] or int(_now().timestamp()) <= rec["valid_to"],
                 f"{auth_id!r} refused: its authorisation window has closed")
        released = int(plan.released_raw)
        _require(int(rec["matched_raw"]) >= released,
                 f"{auth_id!r} refused: tranches worth {released} were released but only {rec['matched_raw']} "
                 f"has been paid and matched")
        _require(released + int(amount_raw) <= int(rec["cap_raw"]),
                 f"{auth_id!r} refused: this tranche would take releases past the authorised cap {rec['cap_raw']}")

        record = self.releases.append_new_get()
        record.auth_id = auth_id
        record.tranche = tranche
        record.amount_raw = amount_raw
        record.released_by = gl.message.sender_address
        record.released_at = _now()
        plan.released_count = u32(plan.released_count + 1)
        plan.released_raw = u256(released + int(amount_raw))

    @gl.public.view
    def get_plan(self, auth_id: str) -> dict:
        if auth_id not in self.plans:
            return {"auth_id": auth_id, "released_count": 0, "released_raw": "0"}
        p = self.plans[auth_id]
        return {"auth_id": auth_id, "released_count": p.released_count, "released_raw": str(p.released_raw)}

    @gl.public.view
    def get_releases(self, offset: u32, limit: u32) -> list:
        limit = min(limit, MAX_PAGE_LIMIT)
        out = []
        i = len(self.releases) - 1 - offset
        while i >= 0 and len(out) < limit:
            r = self.releases[i]
            out.append({"auth_id": r.auth_id, "tranche": r.tranche, "amount_raw": str(r.amount_raw),
                        "released_by": r.released_by.as_hex, "released_at": r.released_at.isoformat()})
            i -= 1
        return out

    @gl.public.view
    def get_config(self) -> dict:
        return {"owner": self.owner.as_hex, "paymatch_address": self.paymatch_address.as_hex,
                "trusted_payer": self.trusted_payer, "release_count": len(self.releases)}
