class Connector:
    readonly = True

    def read(self):
        """Return a list of records. Must be side-effect free."""
        raise NotImplementedError
