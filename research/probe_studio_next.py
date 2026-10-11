# v0.3.0
# { "Depends": "py-genlayer:5jycge4q8k23462jtb0b9fyey1s9qz928sz2nbrd9mg4sxqg2qng" }

# Throwaway connectivity probe - not a submission. Records what GenVM's
# fetchers actually receive for each candidate data source, because a source
# can answer a validator (a US-region sandbox) differently from a laptop.

import genlayer as gl
from genlayer.types import *
from genlayer.storage import DynArray
import json
import hashlib
import csv
import re


class Probe(gl.contract.Contract):
    results: DynArray[str]

    def __init__(self) -> None:
        pass

    @gl.public.write
    def probe_many(self, urls_json: str, ua: str) -> None:
        urls = json.loads(urls_json)

        def leader_fn() -> str:
            out = []
            for url in urls:
                try:
                    r = gl.nondet.web.get(url, headers={"user-agent": ua}) if ua else gl.nondet.web.get(url)
                    body = r.body or b""
                    text = body.decode("utf-8", "replace")
                    out.append({
                        "url": url, "status": r.status, "len": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(),
                        "ctype": str(r.headers.get("content-type", b""))[:60],
                        "head": text[:260], "tail": text[-160:],
                    })
                except Exception as e:
                    out.append({"url": url, "error": repr(e)[:300]})
            return json.dumps(out)

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    # The OFAC lists are big: fetch, parse and search them inside GenVM, and
    # report only a summary (this proves size, parse cost and shape at once).
    @gl.public.write
    def probe_csv(self, url: str, needle: str) -> None:
        def leader_fn() -> str:
            try:
                r = gl.nondet.web.get(url)
                body = r.body or b""
                text = body.decode("utf-8", "replace")
                lines = re.split(r"(?<=\n)", text)
                lines = [ln for ln in lines if ln != ""]
                rows = list(csv.reader(lines))
                widths = {}
                for row in rows:
                    widths[len(row)] = widths.get(len(row), 0) + 1
                hits = [row for row in rows if needle and needle.lower() in " ".join(row).lower()]
                return json.dumps({
                    "url": url, "status": r.status, "len": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                    "rows": len(rows), "widths": widths, "first": rows[0][:12] if rows else [],
                    "needle": needle, "hits": len(hits), "hit0": hits[0][:12] if hits else [],
                    "disposition": str(r.headers.get("content-disposition", b""))[:120],
                    "last_modified": str(r.headers.get("last-modified", b""))[:60],
                })
            except Exception as e:
                return json.dumps({"url": url, "error": repr(e)[:400]})

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    # Does GenVM expose POST? (a JSON-RPC node would be a second, independent
    # source of chain facts). Tries the plausible spellings and records which work.
    @gl.public.write
    def probe_post(self, url: str, body: str) -> None:
        def leader_fn() -> str:
            attempts = {}
            for name in ("post", "request"):
                fn = getattr(gl.nondet.web, name, None)
                if fn is None:
                    attempts[name] = "no such function"
                    continue
                try:
                    if name == "post":
                        r = fn(url, body=body, headers={"content-type": "application/json"})
                    else:
                        r = fn(url, method="POST", body=body, headers={"content-type": "application/json"})
                    b = r.body or b""
                    attempts[name] = {"status": r.status, "len": len(b), "head": b.decode("utf-8", "replace")[:300]}
                except Exception as e:
                    attempts[name] = "error: " + repr(e)[:200]
            return json.dumps({"url": url, "attempts": attempts})

        def validator_fn(leaders_res) -> bool:
            return isinstance(leaders_res, gl.vm.Return)

        self.results.append(gl.vm.run_nondet(leader_fn, validator_fn))

    @gl.public.view
    def get_results(self) -> list:
        return [r for r in self.results]
