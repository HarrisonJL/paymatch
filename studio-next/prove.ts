// Reproducible live proof for PayMatch + TrancheGate. Every step's tx hash,
// result, votes and the contract's recorded output are appended to
// live_proof.json - the source for CONTRACT.md's tables. Steps already in
// live_proof.json are skipped, and each run stops at a time budget, so a stall
// (a sleeping laptop, a slow round) costs nothing: run the same command again.
//
//   npx tsx prove.ts <paymatch> <tranchegate | -> <phase>
//   phases: register | refuse | verify | gate | read
import * as fs from "fs";
import { client, readClient, write, safeJson } from "./lib";

const ECO = "0x2686a8919df194aa7673244549e68d42c1685d03";        // ENS Ecosystem Working Group multisig
const TREASURY = "0xfe89cc7abb2c4183683ab71653c4cdc9b02d44b7";   // ENS DAO treasury (timelock)
// A payer no authorisation uses, so a refusal reaches the check it demonstrates instead of "that vote already authorises ...".
const UNREGISTERED_PAYER = "0x" + "11".repeat(20);
const DUST_SENDER = "0x703abdbb99c60068f78737bb3bf94869b9cc789b"; // a look-alike address that sent the recipient 0.001 USDC
const PROPOSAL: Record<string, [string, string]> = {
  eco470: ["0x9b3f5463e52aadc35155e686f8416297b24e6c7e30cb527747e61cf17b42a5f6", "bafkreibp5fwffwelbm3kx7yks6bxqdoqibnv5say5akmey635mmjblc2pm"],
  eco836: ["0xfe303865510b5ef7fabee2bcbd5081afa01f276195f57e1561ff27c477459984", "bafkreiehxarvfdrhw4tbodt3breveu6s2puyhiosvxhjrlyioiz2eazws4"],
  eco409: ["0x12a2abca291496c7e990d099240b4c995099dc0fb85767e04f22b9496e953799", "bafkreia2ahefq7vmmgs5utov7a3db5mskx6rytrahms5c2fdcxkps6o3vq"],
  rejected: ["0xbc44d9714ee818da49c25998cabdbe745f939fef74923255c3571a00e8977e5d", "bafkreifhxyn66hrmragdms52pk3svo7mh3edb3k7jxpozcbexlpmj5r6kq"],
};
const TX: Record<string, string> = {
  t470: "0x85462789b2919f32fa7da4ea7ece7665a87a881ada5ad48ecd17aff47e613036",
  t836: "0x80b10aa629605bbe6d5f3baf2e3e3b86c4dbe66ee2421663317b29d01454fa8c",
  t409: "0x7eadcd845362e160fa4a6f1918132c1b2c918fdb25e81cc3358ca11ef8daa1fe",
  poison: "0x09fc99e8734ae9a5ff57b7ad57c1cd5ed6ceb61ca8eee71ca27c3ab616037d06",
  spam: "0x641907b05caa5a18aecc9d8379f1322a52b81340731074caef7ec54ed02af3de",
  other: "0x6464aca3757d68a42ca8448af53207036b67c20ec8693f1d5ba4cc79d3881d72",
  failed: "0xa72389d239eee71dfe9ea7a59a1a1b11e15028aa6f211dbc38bc3822164b83ed",
  eth: "0x5f8c3a0b74fde822c4ea32d9f9ee5fb672a65dd9290f8448fde38dad1b4bdecf",
  none: "0x0000000000000000000000000000000000000000000000000000000000000001",
};

// [id, proposal key, recipient, payer, cap, valid_until, label]
const REGISTER: [string, string, string, string, string, string, string][] = [
  ["eco470", "eco470", ECO, TREASURY, "470000", "", "ENS Ecosystem WG: 470,000 USDC (voted Nov 2025)"],
  ["eco836", "eco836", ECO, TREASURY, "836000", "", "ENS Ecosystem WG: 836,000 USDC (voted Oct 2024)"],
  ["eco409", "eco409", ECO, TREASURY, "409000", "", "ENS Ecosystem WG: 409,000 USDC (voted 2023)"],
  ["eco470-alt-payer", "eco470", ECO, DUST_SENDER, "470000", "", "the same vote with a look-alike address as payer: a consumer must pin the payer it trusts"],
];

// Refusals: [id, args, what it shows]
const REFUSE: [string, any[], string][] = [
  ["refuse-cap", ["x-cap", ...PROPOSAL.eco470, ECO, UNREGISTERED_PAYER, "USDC", "836000", "", "cap that is in another request, not this document"], "cap not in the document"],
  ["refuse-recipient", ["x-recipient", ...PROPOSAL.eco470, "0x91c32893216de3ea0a55abb9851f581d4503d39b", TREASURY, "USDC", "470000", "", "a real group address this document never names"], "recipient not in the document"],
  ["refuse-vote", ["x-vote", ...PROPOSAL.rejected, ECO, TREASURY, "USDC", "100000", "", "ENS's vote to replace the working groups, which lost"], "a vote that did not pass"],
  ["refuse-asset", ["x-asset", ...PROPOSAL.eco470, ECO, TREASURY, "DAI", "470000", "", "an asset this document never names"], "asset not named in the document"],
  ["refuse-duplicate", ["x-dup", ...PROPOSAL.eco470, ECO, TREASURY, "USDC", "470000", "", "the same vote, payer, recipient and asset under another id"], "a vote counted twice"],
  ["refuse-figure", ["x-figure", ...PROPOSAL.eco470, ECO, UNREGISTERED_PAYER, "USDC", "172000", "", "172k is the multisig's line in the request's own budget table, not the request"], "a figure in the document that is not the request (reader)"],
];

// Payment verifications: [id, auth_id, tx key, what it shows]
const VERIFY: [string, string, string, string][] = [
  ["v-eco470-match", "eco470", "t470", "the treasury paid exactly the approved 470,000 (one of three payments in the transaction)"],
  ["v-eco836-match", "eco836", "t836", "836,000 paid in 2024"],
  ["v-eco470-before", "eco470", "t836", "the 2024 payment, against a request voted a year later"],
  ["v-eco470-recipient", "eco470", "other", "the treasury paying a different group"],
  ["v-eco470-payer", "eco470", "poison", "0.001 USDC from a look-alike address"],
  ["v-eco470-failed", "eco470", "failed", "a reverted transaction"],
  ["v-eco470-nothing", "eco470", "eth", "a plain ETH transfer"],
  ["v-eco470-spam", "eco470", "spam", "a 50+ transfer poisoning batch"],
  ["v-eco470-none", "eco470", "none", "a transaction that does not exist"],
  ["v-eco836-cumulative", "eco836", "t470", "470,000 more would take the total past the 836,000 cap"],
  ["v-alt-payer-match", "eco470-alt-payer", "poison", "anyone can be registered as payer: the dust sender 'matches' its own dust"],
];

// The gate, in order: [id, kind, args..., what it shows]. A "verify" entry runs between releases.
type GateStep = { id: string; kind: "release" | "verify"; args: any[]; note: string };
const GATE: GateStep[] = [
  { id: "g-release-1", kind: "release", args: ["eco409", 1, "200000000000"], note: "tranche 1 of 200,000 USDC before anything is paid: allowed (nothing earlier is owed)" },
  { id: "g-unpaid", kind: "release", args: ["eco409", 2, "100000000000"], note: "tranche 2 while tranche 1 is unpaid: refused" },
  { id: "g-verify-409", kind: "verify", args: ["eco409", "t409"], note: "the real 409,000 payment is verified" },
  { id: "g-release-2", kind: "release", args: ["eco409", 2, "100000000000"], note: "tranche 2 once the payment is on record: allowed" },
  { id: "g-cap", kind: "release", args: ["eco409", 3, "200000000000"], note: "tranche 3 would take releases past the cap: refused" },
  { id: "g-missing", kind: "release", args: ["nope", 1, "1000000"], note: "an authorisation PayMatch has never heard of: refused" },
  { id: "g-order", kind: "release", args: ["eco409", 9, "1000000"], note: "a tranche out of order: refused" },
  { id: "g-flagged", kind: "release", args: ["eco470", 1, "1000000"], note: "eco470 has flagged payments against it: refused" },
  { id: "g-payer", kind: "release", args: ["eco470-alt-payer", 1, "1000000"], note: "an authorisation naming a payer the gate does not trust: refused" },
  { id: "g-verify-overcap", kind: "verify", args: ["eco409", "t836"], note: "the 836,000 payment against the 409,000 request: OVER_CAP, flagged" },
  { id: "g-flagged-after", kind: "release", args: ["eco409", 3, "1000000"], note: "eco409 is now flagged too: refused" },
];

function load(): any[] {
  return fs.existsSync("live_proof.json") ? JSON.parse(fs.readFileSync("live_proof.json", "utf-8")) : [];
}
function log(entry: Record<string, unknown>) {
  const all = load();
  all.push(entry);
  fs.writeFileSync("live_proof.json", JSON.stringify(all, null, 1));
}
const done = (id: string) => load().some((e) => e.id === id);

function revertMessage(tx: any): string {
  const found: string[] = [];
  const walk = (o: any) => {
    if (typeof o === "string") {
      const m = o.match(/(authorisation refused: [^\n"]*|[^\n"]* refused: [^\n"]*|that vote already authorises[^\n"]*|that transaction already has[^\n"]*|tranches are released in order[^\n"]*|only the owner[^\n"]*)/);
      if (m) found.push(m[0]);
    } else if (o && typeof o === "object") Object.values(o).forEach(walk);
  };
  walk(tx);
  return found[0] ?? "";
}

async function main() {
  const [pm, gate, phase] = process.argv.slice(2);
  const c = client();
  const r = readClient();
  const votes = (tx: any) => tx.last_round?.validator_votes_name ?? [];
  const started = Date.now();
  const outOfTime = () => Date.now() - started > 330_000;
  // Studio Next's RPC allows 30 requests a minute: pace reads under it.
  const view = async (address: string, fn: string, args: unknown[] = []) => {
    await new Promise((res) => setTimeout(res, 2200));
    return JSON.parse(safeJson(await r.readContract({ address, functionName: fn, args })));
  };
  const verify = async (id: string, auth: string, txKey: string, note: string) => {
    const { hash, tx } = await write(c, pm, "verify_payment", [auth, TX[txKey]]);
    const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
    let payment: any = null;
    if (!message) {
      const state = await view(pm, "get_state");
      payment = await view(pm, "get_payment", [state.payment_count - 1]);
    }
    log({ id, step: "verify", auth_id: auth, tx_key: txKey, subject: TX[txKey], note, tx: hash, result: tx.txExecutionResultName,
          votes: votes(tx), revert: message, payment });
    console.log(`  ${auth} <- ${txKey}: ${payment ? payment.verdict + " " + safeJson(payment.reasons) + " amount " + payment.amount_raw : message}`);
  };
  const stop = () => { console.log("  (time budget reached - run this phase again to continue)"); };

  if (phase === "register") {
    for (const [id, key, recipient, payer, cap, until, label] of REGISTER) {
      if (done("reg-" + id)) continue;
      if (outOfTime()) return stop();
      const [proposal, cid] = PROPOSAL[key];
      const { hash, tx } = await write(c, pm, "register_authorisation", [id, proposal, cid, recipient, payer, "USDC", cap, until, label]);
      const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
      const a = message ? null : await view(pm, "get_authorisation", [id]);
      log({ id: "reg-" + id, step: "register", auth_id: id, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message, authorisation: a });
      console.log(`  ${id}: ${tx.txExecutionResultName} ${message}`);
    }
  } else if (phase === "refuse") {
    for (const [id, args, note] of REFUSE) {
      if (done(id)) continue;
      if (outOfTime()) return stop();
      // A refusal that needs another registration to exist first (the duplicate) is only meaningful after "register".
      const { hash, tx } = await write(c, pm, "register_authorisation", args);
      const message = revertMessage(tx);
      log({ id, step: "refuse", args, note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message });
      console.log(`  ${id}: ${tx.txExecutionResultName} ${message}`);
    }
  } else if (phase === "verify") {
    for (const [id, auth, txKey, note] of VERIFY) {
      if (done(id)) continue;
      if (outOfTime()) return stop();
      await verify(id, auth, txKey, note);
    }
  } else if (phase === "gate") {
    if (gate === "-" || !gate) throw new Error("the gate phase needs the TrancheGate address");
    for (const s of GATE) {
      if (done(s.id)) continue;
      if (outOfTime()) return stop();
      if (s.kind === "verify") {
        await verify(s.id, s.args[0], s.args[1], s.note);
      } else {
        // release(auth_id, tranche, amount_raw): the amount is a u256, so it goes as a BigInt.
        const callArgs = [s.args[0], s.args[1], BigInt(s.args[2])];
        const { hash, tx } = await write(c, gate, "release", callArgs);
        const message = tx.txExecutionResultName === "FINISHED_WITH_ERROR" ? revertMessage(tx) : "";
        const plan = await view(gate, "get_plan", [s.args[0]]);
        log({ id: s.id, step: "gate", call: "release", args: s.args, note: s.note, tx: hash, result: tx.txExecutionResultName, votes: votes(tx), revert: message, plan });
        console.log(`  release(${s.args.join(", ")}) -> ${tx.txExecutionResultName} ${message}`);
      }
    }
  } else if (phase === "read") {
    const recs: Record<string, any> = {};
    for (const [id] of REGISTER) {
      recs[id] = await view(pm, "get_reconciliation", [id]);
      console.log(`  ${id}: matched ${recs[id].matched_raw} of ${recs[id].cap_raw}, flagged ${recs[id].flagged_count}, payments ${recs[id].payment_count}`);
    }
    const history = await view(pm, "get_history", ["eco470", 20]);
    const state = await view(pm, "get_state");
    const rules = await view(pm, "get_rules");
    const config = gate && gate !== "-" ? await view(gate, "get_config") : null;
    const releases = gate && gate !== "-" ? await view(gate, "get_releases", [0, 20]) : [];
    if (!done("read")) log({ id: "read", step: "read", reconciliation: recs, state, rules, history_eco470: history.map((h: any) => [h.payment_id, h.verdict, h.previous_id]), gate_config: config, releases });
    console.log("  state:", safeJson(state), "history eco470:", safeJson(history.map((h: any) => `${h.payment_id}:${h.verdict}`)));
  }
  process.exit(0);
}

main().catch((e) => {
  console.error(e?.shortMessage ?? e?.message ?? e);
  process.exit(1);
});
