"""Synthetic data generation helpers for tests and CLI demos."""

import random
from typing import Any


def make_rng(seed: int = 42) -> random.Random:
    """Create a deterministic random number generator instance."""
    return random.Random(seed)


def synthetic_background(n: int = 20, seed: int = 42) -> list[str]:
    """Generate synthetic background web documents for testing."""
    rng = make_rng(seed)
    docs = []
    topics = [
        "Python programming language features and async frameworks.",
        "World history and cultural evolution through trade routes.",
        "Advances in renewable energy sources like solar and wind.",
        "Culinary techniques for baking sourdough bread at home.",
        "Basic mathematics, calculus principles, and geometry notes.",
    ]
    for i in range(n):
        topic = rng.choice(topics)
        docs.append(
            f"Document ID doc_{i}: {topic} Additional filler text to simulate web crawl content {i}."
        )
    return docs


def synthetic_items(n: int = 10, seed: int = 42) -> list[dict[str, Any]]:
    """Generate synthetic benchmark items for testing and evaluation."""
    rng = make_rng(seed)
    items = []
    for i in range(n):
        items.append(
            {
                "item_id": f"syn_{i}",
                "benchmark": "synthetic_math",
                "split": "test",
                "question": f"What is {i} plus {i} multiplied by 3?",
                "choices": ["A) " + str(i), "B) " + str(i * 3), "C) " + str(i * 4)],
                "answer": "B",
                "question_plus_choices": f"What is {i} plus {i} multiplied by 3? A) {i} B) {i * 3} C) {i * 4}",
            }
        )
    return items
