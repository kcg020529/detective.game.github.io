import threading

MODEL_NAME = 'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
VECTOR_SIZE = 384

# 모델은 프로세스 안에서 한 번만 올린다. 채팅 한 번마다 FastEmbedder()를 새로 만들어도 모델을 다시 읽지 않는다.
_LOCK = threading.Lock()
_SHARED = {'model': None, 'tokenizer': None}


class FastEmbedder:
    @property
    def model(self):
        with _LOCK:
            if _SHARED['model'] is None:
                from fastembed import TextEmbedding

                _SHARED['model'] = TextEmbedding(MODEL_NAME)
            return _SHARED['model']

    def count_tokens(self, text):
        with _LOCK:
            tokenizer = _SHARED['tokenizer']
            if tokenizer is not None:
                return len(tokenizer.encode(text).ids)
        tokenizer_json = self.model.model.tokenizer.to_str()
        with _LOCK:
            if _SHARED['tokenizer'] is None:
                from tokenizers import Tokenizer

                tokenizer = Tokenizer.from_str(tokenizer_json)
                tokenizer.no_truncation()
                _SHARED['tokenizer'] = tokenizer
            return len(_SHARED['tokenizer'].encode(text).ids)

    def embed_query(self, text):
        return next(self.model.query_embed(text))

    def embed_documents(self, texts):
        return list(self.model.passage_embed(texts))
