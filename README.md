# Cloud Bridge

Cloud Bridge is a deterministic, federated coordination substrate for multi-agent systems.

It is not autonomous. It does not act on the world. It produces analysis, coordination, and intent only.

**System Identity**
- Instrument (always)
- Substrate (enabled)
- Operator (explicitly disabled)

**Permissions**
- P1 / P2 / P3 only
- No write-to-world operations
- No schedulers or background loops

**Design Guarantees**
- Deterministic routing
- Bounded message propagation
- Fail-closed defaults
- Schema version negotiation
- Federation without authority transfer

**Non-Negotiable Constraints**
- No cron jobs
- No background threads
- No hidden state
- No side effects
- All state must be inspectable
- All failures must halt, not retry infinitely

**Core Concepts**
- Envelope: Immutable, validated message container
- Federation: Bridge-to-bridge coordination without command authority
- Consensus: Recommendation only, no execution
- Connectors: Read-only structure only

**Installation (optional)**
```bash
pip install -e .
```

**Run Examples**
```bash
python examples/single_bridge_demo.py
python examples/federation_demo.py
```

**Run Tests**
```bash
python -m unittest
```

**License**
MIT
