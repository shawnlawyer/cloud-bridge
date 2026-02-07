class Connector:
    readonly = True

    def read(self):
        """Return a list of records. Must be side-effect free."""
        raise NotImplementedError

    def write(self, *_args, **_kwargs):
        """Write is explicitly prohibited for all connectors."""
        raise RuntimeError("Write operations are not permitted")
