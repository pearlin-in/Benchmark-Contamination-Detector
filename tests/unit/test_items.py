"""Tests for the benchmark item schema and its text views (D-002)."""

from __future__ import annotations

from contam.items import BenchmarkItem, View

MCQ = BenchmarkItem(
    item_id="t:1",
    benchmark="t",
    split="test",
    question="Which tool measures mass?",
    choices=("a balance", "a ruler"),
    answer="A",
)
OPEN = BenchmarkItem(item_id="t:2", benchmark="t", split="test", question="What is 5 + 7?")


def test_question_view_ignores_choices() -> None:
    assert MCQ.text(View.QUESTION) == "Which tool measures mass?"


def test_question_choices_view_appends_choices_on_new_lines() -> None:
    assert MCQ.text(View.QUESTION_CHOICES) == "Which tool measures mass?\na balance\na ruler"


def test_items_without_choices_have_one_text_for_both_views() -> None:
    assert OPEN.text(View.QUESTION) == OPEN.text(View.QUESTION_CHOICES) == "What is 5 + 7?"


def test_answer_is_never_part_of_searched_text() -> None:
    item = BenchmarkItem(
        item_id="t:3",
        benchmark="t",
        split="test",
        question="Pick one.",
        choices=("red", "blue"),
        answer="ZEBRA42",
    )
    assert "ZEBRA42" not in item.text(View.QUESTION_CHOICES)


def test_default_view_is_question_plus_choices() -> None:
    assert MCQ.text() == MCQ.text(View.QUESTION_CHOICES)
