from typing import Mapping


def consensus(scores: Mapping[str, float]) -> str:
    if not scores:
        raise ValueError("No candidates to score")
    return sorted(scores.items(), key=lambda x: (-x[1], x[0]))[0][0]
