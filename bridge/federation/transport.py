def send(envelope, destination: str) -> dict:
    return {"sent": True, "destination": destination, "id": str(envelope.id)}
