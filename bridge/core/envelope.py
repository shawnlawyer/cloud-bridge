from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from uuid import UUID, uuid4

from .versioning import negotiate


@dataclass(frozen=True)
class Envelope:
    id: UUID = field(default_factory=uuid4)
    gtid: str = ""
    schema_version: str = ""
    from_agent: str = ""
    to_agent: str = ""
    payload: dict = field(default_factory=dict)
    hop_count: int = 0

    def __post_init__(self) -> None:
        if not self.schema_version:
            raise ValueError("schema_version is required")
        if not negotiate(self.schema_version):
            raise ValueError(f"Unsupported schema version: {self.schema_version}")
        if not self.gtid:
            raise ValueError("gtid is required")
        if not self._is_valid_gtid(self.gtid):
            raise ValueError("gtid format is invalid")
        if not self.from_agent:
            raise ValueError("from_agent is required")
        if not self.to_agent:
            raise ValueError("to_agent is required")
        if not isinstance(self.payload, dict):
            raise TypeError("payload must be a dict")
        if self.hop_count < 0:
            raise ValueError("hop_count must be >= 0")

    def increment_hop(self, max_hops: int) -> "Envelope":
        if self.hop_count >= max_hops:
            raise RuntimeError("Hop limit exceeded")
        return replace(self, hop_count=self.hop_count + 1)

    @staticmethod
    def _is_valid_gtid(gtid: str) -> bool:
        # Format: cb:<epoch>:<origin-bridge-id>:<local-thread-id>
        # Keep permissive to allow UUIDs and other stable IDs.
        pattern = r"^cb:\d+:[^:\s]+:[^:\s]+$"
        return re.match(pattern, gtid) is not None
