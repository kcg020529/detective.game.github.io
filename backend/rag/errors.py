class RagRequestError(ValueError):
    def __init__(self, code='INVALID_REQUEST'):
        self.code = code
        super().__init__(code)


class RagUnavailable(RuntimeError):
    def __init__(self, code='RAG_UNAVAILABLE'):
        self.code = code
        super().__init__(code)
