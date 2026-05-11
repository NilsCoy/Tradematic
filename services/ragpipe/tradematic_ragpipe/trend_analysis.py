from __future__ import annotations

import re


def extract_numbers(text: str) -> list[float]:
    return [float(value.replace(",", ".")) for value in re.findall(r"\d+[,.]\d+|\d+", text)]


def detect_trend(texts: list[str]) -> str:
    numbers: list[float] = []
    for text in texts:
        numbers.extend(extract_numbers(text))
    if len(numbers) < 2:
        return "Недостаточно данных"
    if numbers[-1] > numbers[0]:
        return "Рост"
    if numbers[-1] < numbers[0]:
        return "Падение"
    return "Стабильность"
