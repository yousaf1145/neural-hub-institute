"""
Certificates on the Polygon blockchain (Amoy testnet by default).

Only the certificate's SHA-256 hash goes on chain (no names / emails), in the NeuralHubCertificates contract
(contract/NeuralHubCertificates.sol). The database row is the to-do list; a single background worker makes the
chain match it: issue -> revoke -> reinstate. Anyone can check a hash for free with statusOf().

Two ways to talk to the chain (same contract, same results), chosen automatically (CHAIN_DRIVER=auto|python|node):
    python  web3.py inside the backend
    node    backend/chain/chain.mjs (ethers.js) — used when Windows blocks web3's native crypto files
            (Smart App Control). Needs `npm install` once in backend/chain.

backend/.env (the owner adds these himself — never commit them):
    POLYGON_RPC_URL=https://rpc-amoy.polygon.technology
    POLYGON_PRIVATE_KEY=0x...        # a NEW wallet used only for this (see: python -m modules.certificates.deploy)
    CERT_CONTRACT_ADDRESS=0x...      # printed by: node chain.mjs deploy (or python -m modules.certificates.deploy deploy)
Optional: CHAIN_NETWORK (default polygon-amoy), CHAIN_EXPLORER (default https://amoy.polygonscan.com)
"""
from __future__ import annotations

import json
import logging
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("neuralhub.chain")

REQUIRED = ("POLYGON_RPC_URL", "POLYGON_PRIVATE_KEY", "CERT_CONTRACT_ADDRESS")
CONTRACT_FILE = Path(__file__).resolve().parent / "contract" / "NeuralHubCertificates.json"
NODE_DIR = Path(__file__).resolve().parents[2] / "chain"
STATUS = {0: "none", 1: "valid", 2: "revoked"}
KNOWN = {80002: ("polygon-amoy", "https://amoy.polygonscan.com"), 137: ("polygon", "https://polygonscan.com")}
RECEIPT_TIMEOUT_S = 180

_lock = threading.RLock()      # one transaction at a time (keeps the wallet's nonce in order)
_client: dict = {}
_status_cache: dict[str, tuple[float, dict]] = {}


# ------------------------------------------------------------------ settings
def is_configured() -> bool:
    return all(os.environ.get(k) for k in REQUIRED)


def missing_settings() -> list[str]:
    """Names (never values) of the .env settings still needed."""
    return [k for k in REQUIRED if not os.environ.get(k)]


def network() -> str:
    return os.environ.get("CHAIN_NETWORK") or "polygon-amoy"


def explorer() -> str:
    return (os.environ.get("CHAIN_EXPLORER") or "https://amoy.polygonscan.com").rstrip("/")


def tx_url(tx: str) -> str:
    return f"{explorer()}/tx/{tx}" if tx else ""


def contract_url() -> str:
    addr = os.environ.get("CERT_CONTRACT_ADDRESS", "")
    return f"{explorer()}/address/{addr}" if addr else ""


def artifact() -> dict:
    return json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))


def chain_status() -> dict:
    return {"network": network(), "status": "ready" if is_configured() else "not_configured",
            "contract": os.environ.get("CERT_CONTRACT_ADDRESS", "") if is_configured() else "",
            "contractUrl": contract_url() if is_configured() else ""}


# ------------------------------------------------------------------ driver: python (web3.py) or node (ethers.js)
_driver: dict = {}


def driver() -> str:
    if _client.get("key") == ("custom",):
        return "python"  # tests plug in their own web3 chain
    want = (os.environ.get("CHAIN_DRIVER") or "auto").lower()
    if want in ("python", "node"):
        return want
    if "auto" not in _driver:
        try:  # web3's crypto needs native files that Windows Smart App Control may block
            from Crypto.Cipher import AES  # noqa: F401
            import web3  # noqa: F401

            _driver["auto"] = "python"
        except Exception as e:  # noqa: BLE001 - ImportError, or OSError from a blocked .pyd
            log.warning("Using the Node.js blockchain helper (web3.py unavailable: %s)", str(e).splitlines()[0][:120])
            _driver["auto"] = "node"
    return _driver["auto"]


def _node(*args: str, timeout: float = RECEIPT_TIMEOUT_S + 60) -> dict:
    exe = shutil.which("node")
    if not exe:
        raise RuntimeError("Node.js is not installed (needed for the blockchain helper).")
    if not (NODE_DIR / "node_modules" / "ethers").exists():
        raise RuntimeError("Run `npm install` once in backend/chain (the blockchain helper).")
    proc = subprocess.run([exe, "chain.mjs", *args, "--json"], cwd=NODE_DIR, env=os.environ.copy(), capture_output=True,
                          text=True, timeout=timeout, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        data = {"error": (proc.stderr or proc.stdout or "blockchain helper failed").strip()[:300]}
    if proc.returncode != 0 or "error" in data:
        raise RuntimeError(data.get("error") or "blockchain helper failed")
    return data


def wallet_info() -> dict:
    """{address, balance} of the NeuralHub wallet (for the admin page)."""
    if driver() == "node":
        d = _node("info", timeout=40)
        return {"address": d["address"], "balance": round(float(d["balance"]), 4)}
    w3, account, _ = client()
    return {"address": account.address,
            "balance": round(float(w3.from_wei(w3.eth.get_balance(account.address), "ether")), 4)}


# ------------------------------------------------------------------ web3 client
def set_client(w3, account, contract) -> None:
    """Tests (and the deploy script) can plug in their own chain."""
    with _lock:
        _client.clear()
        if w3 is not None:
            _client.update(w3=w3, account=account, contract=contract, key=("custom",))
    _status_cache.clear()


def client():
    """(w3, account, contract) — built from .env once and reused."""
    with _lock:
        key = tuple(os.environ.get(k, "") for k in REQUIRED)
        if _client and (_client["key"] == key or _client["key"] == ("custom",)):
            return _client["w3"], _client["account"], _client["contract"]
        if not is_configured():
            raise RuntimeError("Blockchain is not set up: add " + ", ".join(missing_settings()) + " to backend/.env")
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(os.environ["POLYGON_RPC_URL"], request_kwargs={"timeout": 20}))
        account = w3.eth.account.from_key(os.environ["POLYGON_PRIVATE_KEY"].strip())
        address = Web3.to_checksum_address(os.environ["CERT_CONTRACT_ADDRESS"].strip())
        contract = w3.eth.contract(address=address, abi=artifact()["abi"])
        _client.update(w3=w3, account=account, contract=contract, key=key)
        return w3, account, contract


def _h(digest: str) -> bytes:
    raw = bytes.fromhex(digest.removeprefix("0x"))
    if len(raw) != 32:
        raise ValueError("certificate hash must be 32 bytes (SHA-256)")
    return raw


def read_status(digest: str, cache_s: float = 60) -> dict:
    """What the blockchain says about this certificate (free read, cached for a minute)."""
    hit = _status_cache.get(digest)
    if hit and time.monotonic() - hit[0] < cache_s:
        return hit[1]
    if driver() == "node":
        _h(digest)
        out = _node("status", digest.removeprefix("0x"), timeout=30)
        out = {"status": out.get("status", "none"), "issuedAt": out.get("issuedAt"), "revokedAt": out.get("revokedAt")}
        _status_cache[digest] = (time.monotonic(), out)
        return out
    _, _, contract = client()
    st, issued, revoked = contract.functions.statusOf(_h(digest)).call()
    out = {"status": STATUS.get(int(st), "none"), "issuedAt": int(issued) or None, "revokedAt": int(revoked) or None}
    _status_cache[digest] = (time.monotonic(), out)
    return out


def _send(fn) -> str:
    """Sign and send one contract call from the NeuralHub wallet; wait until it is mined. Returns the tx hash."""
    w3, account, _ = client()
    with _lock:
        tx = fn.build_transaction({"from": account.address, "nonce": w3.eth.get_transaction_count(account.address, "pending"),
                                   "chainId": w3.eth.chain_id})
        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        tx_hash = w3.eth.send_raw_transaction(raw)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=RECEIPT_TIMEOUT_S)
    if receipt["status"] != 1:
        raise RuntimeError(f"transaction failed on chain ({tx_hash.hex()})")
    return "0x" + tx_hash.hex().removeprefix("0x")


def sync(digest: str, want: str) -> dict:
    """Make the chain say `want` ("valid" | "revoked") for this hash. Returns {"issueTx", "changeTx", "status"}."""
    if driver() == "node":
        _h(digest)
        with _lock:  # one transaction at a time
            out = _node("sync", digest.removeprefix("0x"), want)
        _status_cache.pop(digest, None)
        return {"issueTx": out.get("issueTx", ""), "changeTx": out.get("changeTx", ""), "status": out.get("status", want)}
    _, _, contract = client()
    h = _h(digest)
    now = read_status(digest, cache_s=0)["status"]
    out = {"issueTx": "", "changeTx": ""}
    if now == "none":
        out["issueTx"] = _send(contract.functions.issue(h))
        now = "valid"
    if want == "revoked" and now == "valid":
        out["changeTx"] = _send(contract.functions.revoke(h))
        now = "revoked"
    elif want == "valid" and now == "revoked":
        out["changeTx"] = _send(contract.functions.reinstate(h))
        now = "valid"
    _status_cache.pop(digest, None)
    out["status"] = now
    return out


# ------------------------------------------------------------------ background worker
_jobs: "queue.Queue[str]" = queue.Queue()
_queued: set[str] = set()
_worker: dict = {"thread": None}


def enqueue(cert_id: str) -> bool:
    """Ask the worker to bring this certificate up to date on chain (no-op when the chain is not set up)."""
    if not is_configured():
        return False
    with _lock:
        if cert_id in _queued:
            return True
        _queued.add(cert_id)
        _jobs.put(cert_id)
        t = _worker["thread"]
        if t is None or not t.is_alive():
            t = threading.Thread(target=_run, name="certificate-chain", daemon=True)
            _worker["thread"] = t
            t.start()
    return True


def _run() -> None:
    while True:
        try:
            cert_id = _jobs.get(timeout=60)
        except queue.Empty:
            return  # idle: the next enqueue() starts a new worker
        with _lock:  # a change made while this job runs queues it again
            _queued.discard(cert_id)
        try:
            process(cert_id)
        except Exception as e:  # noqa: BLE001 - a bad job must not kill the worker
            log.error("Chain job %s crashed: %s", cert_id, e)


def process(cert_id: str) -> Optional[str]:
    """Bring one registry row and the chain in line; record the result on the row. Returns the new chain_status."""
    from core import db as core_db
    from modules.certificates.models import CertificateRecord

    with core_db.session_scope() as db:
        row = db.get(CertificateRecord, cert_id)
        if row is None:
            return None
        digest, want = row.hash, ("revoked" if row.status == "revoked" else "valid")
    try:
        res = sync(digest, want)
        err, status = "", ("revoked" if res["status"] == "revoked" else "anchored")
    except Exception as e:  # noqa: BLE001 - no gas, RPC down, ... -> "failed", the admin can retry
        res, status = {"issueTx": "", "changeTx": ""}, "failed"
        err = _short_error(e)
        log.warning("Certificate %s not written to the blockchain: %s", cert_id, err)
    with core_db.session_scope() as db:
        row = db.get(CertificateRecord, cert_id)
        if row is None:
            return None
        row.chain_status, row.chain_error, row.chain_network = status, err[:300], network()
        if res["issueTx"]:
            row.chain_tx = res["issueTx"]
        if res["changeTx"]:
            row.chain_revoke_tx = res["changeTx"]
        if status != "failed":
            row.chain_at = datetime.now(timezone.utc)
    return status


def _short_error(e: Exception) -> str:
    text = str(e) or e.__class__.__name__
    low = text.lower()
    if "insufficient funds" in low:
        return "The NeuralHub wallet has no test POL for gas. Get free POL from the Amoy faucet."
    if "notowner" in low or "0x30cd7471" in low:
        return "This wallet is not the owner of the certificate contract."
    if "timeout" in low or "timed out" in low or "connection" in low:
        return "Could not reach the blockchain (RPC). It will work again on retry."
    key = os.environ.get("POLYGON_PRIVATE_KEY", "")
    if key and key in text:  # never store the key anywhere
        text = text.replace(key, "***")
    return text.splitlines()[0][:300]


def mark_pending(row) -> None:
    """Called when a certificate is issued / revoked / restored: the worker will update the chain."""
    if is_configured():
        row.chain_status, row.chain_error, row.chain_network = "pending", "", network()


def out_of_sync(db) -> list[str]:
    """Certificates whose blockchain record does not match the registry yet (new, failed, or revoked/restored since)."""
    from sqlalchemy import and_, or_, select

    from modules.certificates.models import CertificateRecord as C

    return list(db.scalars(select(C.id).where(or_(
        C.chain_status.in_(("not_configured", "pending", "failed")),
        and_(C.status == "revoked", C.chain_status == "anchored"),
        and_(C.status == "valid", C.chain_status == "revoked")))))


def summary(db) -> dict:
    from sqlalchemy import func, select

    from modules.certificates.models import CertificateRecord as C

    counts = dict(db.execute(select(C.chain_status, func.count()).group_by(C.chain_status)).all())
    return {"anchored": int(counts.get("anchored", 0)), "revokedOnChain": int(counts.get("revoked", 0)),
            "pending": int(counts.get("pending", 0)), "failed": int(counts.get("failed", 0)),
            "outOfSync": len(out_of_sync(db)), "queued": len(_queued)}
