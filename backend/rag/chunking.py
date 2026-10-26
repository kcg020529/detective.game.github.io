CHUNK_MAX_TOKENS = 128
CHUNK_OVERLAP_TOKENS = 16


def _largest_prefix(text, token_count, max_tokens):
    low, high = 1, len(text)
    best = 0
    while low <= high:
        middle = (low + high) // 2
        if token_count(text[:middle]) <= max_tokens:
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    if not best:
        raise ValueError('max_tokens is smaller than the tokenizer special-token cost')
    newline = text.rfind('\n', 0, best)
    if newline >= best // 2:
        return newline + 1
    return best


def _overlap_start(chunk, token_count, overlap_tokens):
    if overlap_tokens == 0:
        return len(chunk)
    low, high = 0, len(chunk)
    while low < high:
        middle = (low + high) // 2
        if token_count(chunk[middle:]) <= overlap_tokens:
            high = middle
        else:
            low = middle + 1
    return low


def chunk_text(text, token_count, *, max_tokens=CHUNK_MAX_TOKENS, overlap_tokens=CHUNK_OVERLAP_TOKENS):
    if not isinstance(text, str):
        raise TypeError('text must be a string')
    if type(max_tokens) is not int or max_tokens < 1:
        raise ValueError('max_tokens must be a positive integer')
    if type(overlap_tokens) is not int or not 0 <= overlap_tokens < max_tokens:
        raise ValueError('overlap_tokens must be between zero and max_tokens')
    if not text:
        return []

    chunks = []
    remaining = text
    while token_count(remaining) > max_tokens:
        end = _largest_prefix(remaining, token_count, max_tokens)
        chunk = remaining[:end]
        chunks.append(chunk)
        start = _overlap_start(chunk, token_count, overlap_tokens)
        remaining = chunk[start:] + remaining[end:]
    chunks.append(remaining)
    return chunks
