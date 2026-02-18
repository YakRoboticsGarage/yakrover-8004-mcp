"""Generic ERC-8004 on-chain registration and update for robot plugins."""

import os

from agent0_sdk import SDK
from agent0_sdk.core.models import EndpointType
from dotenv import load_dotenv

from core.plugin import RobotPlugin

load_dotenv()


def _make_sdk(*, ipfs: bool = False) -> SDK:
    """Create an Agent0 SDK instance.

    Args:
        ipfs: Whether to configure IPFS/Pinata for metadata uploads.
    """
    kwargs = dict(
        chainId=11155111,  # Ethereum Sepolia
        rpcUrl=os.environ["RPC_URL"],
        signer=os.environ["SIGNER_PVT_KEY"],
    )
    if ipfs:
        kwargs["ipfs"] = "pinata"
        kwargs["pinataJwt"] = os.environ["PINATA_JWT"]
    return SDK(**kwargs)


def _mcp_url(url_prefix: str) -> str:
    """Build the public MCP endpoint URL for a robot."""
    ngrok_domain = os.environ["NGROK_DOMAIN"]
    return f"https://{ngrok_domain}/{url_prefix}/mcp"


def register_robot(plugin: RobotPlugin) -> None:
    """Register a robot plugin on ERC-8004 (Ethereum Sepolia).

    Reads RPC_URL, SIGNER_PVT_KEY, PINATA_JWT, and NGROK_DOMAIN from the
    environment. Uploads metadata to IPFS via Pinata, then submits the
    registration transaction and waits for it to be mined.
    """
    meta = plugin.metadata()
    sdk = _make_sdk(ipfs=True)
    mcp_endpoint = _mcp_url(meta.url_prefix)

    agent = sdk.createAgent(
        name=meta.name,
        description=meta.description,
        image=meta.image or "",
    )

    # auto_fetch=False: the SDK's EndpointCrawler doesn't support MCP
    # streamable-http transport (sends wrong headers, gets 400).
    # We set the tool list manually instead.
    agent.setMCP(mcp_endpoint, auto_fetch=False)

    mcp_ep = next(ep for ep in agent.registration_file.endpoints if ep.type == EndpointType.MCP)
    mcp_ep.meta["mcpTools"] = plugin.tool_names()

    agent.setTrust(reputation=True)
    agent.setActive(True)
    agent.setX402Support(False)

    agent.setMetadata({
        "category": "robot",
        "robot_type": meta.robot_type,
        "fleet_provider": meta.fleet_provider,
        "fleet_domain": meta.fleet_domain,
    })

    print(f"Registering '{meta.name}' on Ethereum Sepolia...")
    print(f"  MCP endpoint: {mcp_endpoint}")
    print(f"  Tools: {plugin.tool_names()}")
    print(f"  robot_type={meta.robot_type}, fleet_provider={meta.fleet_provider}, fleet_domain={meta.fleet_domain}")
    print()

    print("Submitting registration transaction...")
    tx_handle = agent.registerIPFS()
    print(f"Transaction submitted: {tx_handle.tx_hash}")

    print("Waiting for transaction to be mined...")
    mined = tx_handle.wait_mined(timeout=120)
    reg_file = mined.result

    print(f"\nAgent registered on Ethereum Sepolia!")
    print(f"Agent ID:  {reg_file.agentId}")
    print(f"Agent URI: {reg_file.agentURI}")


def update_robot(plugin: RobotPlugin, agent_id: str) -> None:
    """Update an existing on-chain robot agent.

    Loads the agent by ID, updates its MCP endpoint, tool list, and metadata
    from the plugin, re-uploads to IPFS, and submits the update transaction.

    Args:
        plugin: The robot plugin with current metadata and tool list.
        agent_id: On-chain agent ID (e.g. "11155111:989").
    """
    meta = plugin.metadata()
    sdk = _make_sdk(ipfs=True)
    mcp_endpoint = _mcp_url(meta.url_prefix)

    print(f"Loading agent {agent_id}...")
    agent = sdk.loadAgent(agent_id)
    print(f"  Name: {agent.name}")
    print(f"  Current MCP endpoint: {agent.mcpEndpoint}")
    print(f"  Current tools: {agent.mcpTools}")

    agent.setMCP(mcp_endpoint, auto_fetch=False)

    mcp_ep = next(ep for ep in agent.registration_file.endpoints if ep.type == EndpointType.MCP)
    mcp_ep.meta["mcpTools"] = plugin.tool_names()

    agent.setMetadata({
        "category": "robot",
        "robot_type": meta.robot_type,
        "fleet_provider": meta.fleet_provider,
        "fleet_domain": meta.fleet_domain,
    })

    print(f"\n  Updated MCP endpoint: {mcp_endpoint}")
    print(f"  Updated tools: {plugin.tool_names()}")
    print(f"  robot_type={meta.robot_type}, fleet_provider={meta.fleet_provider}, fleet_domain={meta.fleet_domain}")

    print("\nSubmitting update transaction...")
    tx_handle = agent.registerIPFS()
    print(f"Transaction submitted: {tx_handle.tx_hash}")

    print("Waiting for transaction to be mined...")
    mined = tx_handle.wait_mined(timeout=120)
    reg_file = mined.result

    print(f"\nAgent updated!")
    print(f"Agent ID:  {reg_file.agentId}")
    print(f"Agent URI: {reg_file.agentURI}")


def fix_metadata(plugin: RobotPlugin, agent_id_int: int) -> None:
    """Fix on-chain metadata for an existing agent.

    Directly sets metadata keys on-chain (without IPFS re-upload).
    Useful for correcting metadata after registration or migrating
    from old key names (e.g. agent_type → category).

    Args:
        plugin: The robot plugin with the correct metadata values.
        agent_id_int: Numeric agent ID on the identity registry.
    """
    meta = plugin.metadata()
    sdk = _make_sdk()

    expected = {
        "category": b"robot",
        "robot_type": meta.robot_type.encode(),
        "fleet_provider": meta.fleet_provider.encode(),
        "fleet_domain": meta.fleet_domain.encode(),
    }

    print(f"Fixing metadata for agent {agent_id_int} ({meta.name})...")
    print()

    # Read and fix each key
    for key, want in expected.items():
        current = sdk.identity_registry.functions.getMetadata(agent_id_int, key).call()
        current_str = current.decode() if current else "(empty)"
        want_str = want.decode()

        if current == want:
            print(f"  {key} = {current_str}  (already correct)")
            continue

        print(f"  {key}: {current_str} → {want_str}")
        tx = sdk.web3_client.transact_contract(
            sdk.identity_registry, "setMetadata", agent_id_int, key, want
        )
        sdk.web3_client.wait_for_transaction(tx, timeout=60)
        print(f"    Done (tx: {tx})")

    # Clean up legacy keys
    legacy_keys = ["agent_type"]
    for key in legacy_keys:
        val = sdk.identity_registry.functions.getMetadata(agent_id_int, key).call()
        if val:
            print(f"  Clearing legacy key '{key}' (was: {val.decode()})...")
            tx = sdk.web3_client.transact_contract(
                sdk.identity_registry, "setMetadata", agent_id_int, key, b""
            )
            sdk.web3_client.wait_for_transaction(tx, timeout=60)
            print(f"    Done (tx: {tx})")

    # Verify
    print("\nVerification:")
    for key in expected:
        val = sdk.identity_registry.functions.getMetadata(agent_id_int, key).call()
        print(f"  {key} = {val.decode() if val else '(empty)'}")
