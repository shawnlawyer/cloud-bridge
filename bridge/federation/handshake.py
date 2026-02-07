def handshake(local_id: str, remote_id: str, known_bridges: set[str] | None = None) -> bool:
    if not local_id or not remote_id:
        return False
    if local_id == remote_id:
        return False
    if known_bridges and remote_id in known_bridges:
        return False
    return True
