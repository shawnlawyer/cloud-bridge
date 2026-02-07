class ReadOnlyMux:
    def __init__(self, connectors):
        for c in connectors:
            if not getattr(c, "readonly", False):
                raise RuntimeError("Connector is not read-only")
        self.connectors = connectors

    def read_all(self):
        data = []
        for c in self.connectors:
            data.extend(c.read())
        return data
