SUPPORTED_SCHEMAS = {"1.0"}


def negotiate(version: str) -> bool:
    return version in SUPPORTED_SCHEMAS
