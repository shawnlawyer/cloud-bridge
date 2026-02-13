# Schema Evolution Policy

1. Minor versions may add optional fields only.
2. Major versions require overlap support with the previous major version.
3. Required fields may not be removed.
4. Unknown fields must be ignored.
5. Negotiation must fail closed when versions are incompatible.
