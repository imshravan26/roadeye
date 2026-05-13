import os
import hashlib
import json
import logging
import asyncio
import threading
from pathlib import Path

# Serialise all on-chain submissions so two threads never race on next_incident_id
_solana_lock = threading.Lock()

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID
from anchorpy import Program, Provider, Wallet, Context, Idl
from anchorpy.provider import DEFAULT_OPTIONS
from solana.rpc.async_api import AsyncClient
from solana.rpc.commitment import Confirmed

LOGGER = logging.getLogger(__name__)

SOLANA_RPC_URL       = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_ID           = os.getenv("PROGRAM_ID", "")
REPORTER_PRIVATE_KEY = os.getenv("REPORTER_PRIVATE_KEY", "")  # base58 or json array


def _load_keypair() -> Keypair:
    key = REPORTER_PRIVATE_KEY.strip()
    if key.startswith("["):
        return Keypair.from_bytes(bytes(json.loads(key)))
    return Keypair.from_base58_string(key)


def _camera_id_hash(camera_id: str) -> list[int]:
    return list(hashlib.sha256(camera_id.encode()).digest())


async def _submit_async(incident_meta: dict, clip_cid: str) -> str | None:
    if not PROGRAM_ID or not REPORTER_PRIVATE_KEY:
        LOGGER.warning("Solana env vars not set — skipping on-chain submission.")
        return None

    keypair  = _load_keypair()
    wallet   = Wallet(keypair)
    # Use Confirmed commitment so registry reads always reflect the latest confirmed TX
    client   = AsyncClient(SOLANA_RPC_URL, commitment=Confirmed)
    provider = Provider(client, wallet, DEFAULT_OPTIONS)

    idl_path = Path(__file__).parent / "idl.json"
    if not idl_path.exists():
        LOGGER.error("IDL file not found at %s", idl_path)
        await client.close()
        return None

    idl = Idl.from_json(idl_path.read_text())
    program = Program(idl, Pubkey.from_string(PROGRAM_ID), provider)

    program_id_pubkey = Pubkey.from_string(PROGRAM_ID)

    registry_pda, _ = Pubkey.find_program_address(
        [b"registry"],
        program_id_pubkey,
    )

    registry_account = await program.account["Registry"].fetch(registry_pda)
    next_id = registry_account.next_incident_id

    incident_pda, _ = Pubkey.find_program_address(
        [b"incident", next_id.to_bytes(8, "little")],
        program_id_pubkey,
    )

    camera_id = os.getenv("CAMERA_ID", "default-camera-01")

    tx = await program.rpc["record_incident"](
        {
            "occurred_at":    incident_meta["occurred_at"],
            "camera_id_hash": _camera_id_hash(camera_id),
            "vehicle_class":  incident_meta["vehicle_class"],
            "distance_cm":    max(0, int(round(incident_meta["distance_m"] * 100))),
            "ttc_ms":         max(0, int(round(incident_meta["ttc_s"] * 1000))),
            "severity_score": min(100, max(0, incident_meta["severity_score"])),
            "severity_label": incident_meta["severity_label"],
            "alert_flag":     True,
            "clip_cid":       clip_cid,
        },
        ctx=Context(
            accounts={
                "registry":       registry_pda,
                "incident":       incident_pda,
                "reporter":       keypair.pubkey(),
                "system_program": SYS_PROGRAM_ID,
            }
        ),
    )

    # Wait for confirmation before releasing the lock so the next submission
    # reads the already-incremented next_incident_id from the chain.
    await client.confirm_transaction(tx, commitment=Confirmed)

    LOGGER.info("Incident recorded on Solana: %s", tx)
    await client.close()
    return str(tx)


def submit_to_solana(incident_meta: dict, clip_cid: str) -> str | None:
    with _solana_lock:          # one submission at a time — prevents PDA seed collision
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(_submit_async(incident_meta, clip_cid))
            finally:
                loop.close()
        except Exception as e:
            LOGGER.error("Solana submission failed: %s", e)
            return None