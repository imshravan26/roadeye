import asyncio
import json
import os
from pathlib import Path

from anchorpy import Context, Idl, Program, Provider, Wallet
from anchorpy.provider import DEFAULT_OPTIONS
from dotenv import load_dotenv
from solana.rpc.async_api import AsyncClient
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.system_program import ID as SYS_PROGRAM_ID


load_dotenv(Path(__file__).parent / ".env")

SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.devnet.solana.com")
PROGRAM_ID = os.getenv("PROGRAM_ID", "")
REPORTER_PRIVATE_KEY = os.getenv("REPORTER_PRIVATE_KEY", "")


def load_keypair() -> Keypair:
    key = REPORTER_PRIVATE_KEY.strip()
    if key.startswith("["):
        return Keypair.from_bytes(bytes(json.loads(key)))
    return Keypair.from_base58_string(key)


async def main() -> None:
    if not PROGRAM_ID:
        raise RuntimeError("PROGRAM_ID is missing from dlbackend/.env")
    if not REPORTER_PRIVATE_KEY:
        raise RuntimeError("REPORTER_PRIVATE_KEY is missing from dlbackend/.env")

    keypair = load_keypair()
    client = AsyncClient(SOLANA_RPC_URL)
    provider = Provider(client, Wallet(keypair), DEFAULT_OPTIONS)

    try:
        idl_path = Path(__file__).parent / "api" / "idl.json"
        idl = Idl.from_json(idl_path.read_text())
        program_id = Pubkey.from_string(PROGRAM_ID)
        program = Program(idl, program_id, provider)

        registry_pda, _ = Pubkey.find_program_address([b"registry"], program_id)

        try:
            existing = await program.account["Registry"].fetch(registry_pda)
            print(f"Registry already initialized: {registry_pda}")
            print(f"next_incident_id={existing.next_incident_id}")
            return
        except Exception:
            pass

        tx = await program.rpc["initialize"](
            ctx=Context(
                accounts={
                    "registry": registry_pda,
                    "authority": keypair.pubkey(),
                    "system_program": SYS_PROGRAM_ID,
                }
            )
        )
        print(f"Registry initialized: {registry_pda}")
        print(f"Transaction: {tx}")
        print(f"Explorer: https://explorer.solana.com/tx/{tx}?cluster=devnet")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
