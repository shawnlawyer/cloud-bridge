from .envelope import Envelope

MAX_HOPS = 8


def route(envelope: Envelope, registry) -> str:
    if envelope.hop_count < 0:
        raise RuntimeError("Routing halted: negative hop count")
    if envelope.hop_count >= MAX_HOPS:
        raise RuntimeError("Routing halted: hop cap reached")

    return registry.lookup(envelope.to_agent)
