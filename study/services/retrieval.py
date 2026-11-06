from collections import Counter
import math
import re

from study.models import TextChunk


def terms(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w']+", text.casefold()) if len(token) > 1]


def retrieve(question: str, document_ids: list[int], owner_id: int, limit: int = 5) -> list[dict]:
    query_terms = set(terms(question))
    if not query_terms:
        return []
    chunks = list(
        TextChunk.objects.filter(document_id__in=document_ids, document__owner_id=owner_id)
        .select_related("document")
    )
    if not chunks:
        return []
    document_frequency = Counter()
    chunk_terms = []
    for chunk in chunks:
        counts = Counter(terms(chunk.text))
        chunk_terms.append(counts)
        document_frequency.update(counts.keys())
    scored = []
    total = len(chunks)
    for chunk, counts in zip(chunks, chunk_terms):
        score = 0.0
        length_norm = max(1, sum(counts.values()))
        for term in query_terms:
            frequency = counts.get(term, 0)
            if frequency:
                inverse_frequency = math.log(1 + total / (1 + document_frequency[term]))
                score += inverse_frequency * (frequency / length_norm)
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {"document_id": chunk.document_id, "document_title": chunk.document.title, "page": chunk.page_number, "text": chunk.text}
        for _, chunk in scored[:limit]
    ]
