MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
VECTOR_SIZE = 384


class FastEmbedder:
    def __init__(self):
        self._model = None
        self._tokenizer = None

    @property
    def model(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(MODEL_NAME)
        return self._model

    def count_tokens(self, text):
        if self._tokenizer is None:
            from tokenizers import Tokenizer

            self._tokenizer = Tokenizer.from_str(self.model.model.tokenizer.to_str())
            self._tokenizer.no_truncation()
        return len(self._tokenizer.encode(text).ids)

    def embed_query(self, text):
        return next(self.model.query_embed(text))

    def embed_documents(self, texts):
        return list(self.model.passage_embed(texts))
