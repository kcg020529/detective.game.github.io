import time

_CACHE = {}
TTL_SECONDS = 300


def invalidate(dataset=None):
    if dataset is None:
        _CACHE.clear()
    else:
        _CACHE.pop(dataset, None)


def build_guard_inputs(catalog, records):
    allowed = {record['record_id']: record for record in records}
    guard_records = []
    for catalog_record in catalog:
        record_id = catalog_record['record_id']
        if record_id not in allowed:
            guard_records.append(catalog_record)
            continue
        cut = allowed[record_id]
        guard_records.append(cut)
        withheld = {field: (catalog_record.get(field) or '')
                    if not cut.get(field) and catalog_record.get(field) else ''
                    for field in ('summary', 'content')}
        if any(withheld.values()):
            guard_records.append({'record_id': f'{record_id}#withheld', **withheld})
    return guard_records, list(allowed)


def load_generic_entities(conn, dataset, *, now=None):
    now = time.monotonic() if now is None else now
    cached = _CACHE.get(dataset)
    if cached is None or now - cached[0] >= TTL_SECONDS:
        load_catalog(conn, dataset, now=now)
        cached = _CACHE[dataset]
    if len(cached) == 2:
        with conn.cursor() as cursor:
            cursor.execute('SELECT location_id FROM locations ORDER BY location_id')
            entities = [row['location_id'] for row in cursor.fetchall()]
        _CACHE[dataset] = (*cached, entities)
    return list(_CACHE[dataset][2])


def load_catalog(conn, dataset, *, now=None):
    now = time.monotonic() if now is None else now
    cached = _CACHE.get(dataset)
    if cached is not None and now - cached[0] < TTL_SECONDS:
        return [dict(record) for record in cached[1]]
    with conn.cursor() as cursor:
        cursor.execute('SELECT record_id, record_type, day, test_id, summary, content '
                       'FROM game_records WHERE dataset = %s ORDER BY record_id', (dataset,))
        records = [dict(row) for row in cursor.fetchall()]
    _CACHE[dataset] = (now, records)
    return [dict(record) for record in records]


_PROMPT_SENTENCES = {}

def prompt_sentences_for(character_id, *, render=None):
    """Render prompt sentences, excluding phrases this persona may say verbatim."""
    from backend.character_ai.prompt_render import fixed_reply, get_persona, render_actor_prompt
    from backend.guardrails.output.normalize import compact
    from backend.guardrails.output.prompt_check import sentences_from_text

    if render is None and character_id in _PROMPT_SENTENCES:
        return list(_PROMPT_SENTENCES[character_id])
    persona = get_persona(character_id)
    phrases = []

    def add(value):
        if isinstance(value, str):
            phrases.append(value)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    phrases.append(item)
                elif isinstance(item, dict) and isinstance(item.get('a'), str):
                    phrases.append(item['a'])

    for key in ('catchphrase', 'unknown_style', 'restricted_style', 'examples'):
        add(persona.get(key))
    for mode in ('restricted', 'off_topic', 'injection'):
        add(fixed_reply(character_id, mode).get('reply'))
    normalized_phrases = [compact(phrase) for phrase in phrases if compact(phrase)]
    if render is None:
        render = render_actor_prompt
    text = render(character_id, 'answer', memory=[], history=[])
    sentences = sentences_from_text(text)
    kept = [sentence for sentence in sentences
            if not any(phrase in compact(sentence) or compact(sentence) in phrase
                       for phrase in normalized_phrases)]
    if render is render_actor_prompt:
        _PROMPT_SENTENCES[character_id] = tuple(kept)
    return kept
