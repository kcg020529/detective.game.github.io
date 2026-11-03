"""Re-run the two 100-question Input Guard holdout sets with the live LLM."""

import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

from backend.guardrails.input.input_guard import inspect_input
from backend.guardrails.input.llm_input_guard import LEVEL_SCORE, classify_with_llm


ROOT = Path(__file__).resolve().parents[3]
SOURCES = (
    ROOT / "experiments/evaluation/input_guard/cases/input_guard_holdout_cases.json",
    ROOT / "experiments/evaluation/input_guard/cases/input_guard_holdout_cases_02.json",
)
OUTPUT = ROOT / "experiments/evaluation/input_guard/results/input_guard_holdout_retest_200_2026-11-03.json"


def load_cases():
    cases = []
    for source in SOURCES:
        for group in json.loads(source.read_text(encoding="utf-8")):
            for question in group["questions"]:
                cases.append((len(cases) + 1, source.name, group["group"], question, group["expected_level"]))
    if len(cases) != 200 or len({item[3] for item in cases}) != 200:
        raise ValueError("Expected 200 unique questions")
    return cases


def run_case(case):
    n, source, group, question, expected = case
    rules = inspect_input(question)
    model = None
    error = None
    for attempt in range(3):
        try:
            model = classify_with_llm(question)
            break
        except ValueError as exc:
            error = str(exc)
            if attempt < 2:
                sleep(attempt + 1)
    final = max((rules.level, model), key=LEVEL_SCORE.__getitem__) if model else rules.level
    signals = list(rules.signals)
    if model in ("warn", "high_risk"):
        signals.append(f"llm_{model}")
    return {
        "n": n, "source": source, "group": group, "question": question,
        "expected": expected, "rules": rules.level, "model": model,
        "final": final, "signals": signals,
        "model_status": "ok" if model else "fallback",
        "match": final == expected if model else None,
        "error": error if model is None else None,
    }


def main():
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise SystemExit("DEEPSEEK_API_KEY is required")
    started = datetime.now(timezone.utc).isoformat()
    cases = load_cases()
    results = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(run_case, case) for case in cases]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 20 == 0:
                print(f"completed {len(results)}/200", flush=True)
    results.sort(key=lambda item: item["n"])
    payload = {
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "case_count": len(results),
        "model_ok": sum(item["model_status"] == "ok" for item in results),
        "matches": sum(item["match"] is True for item in results),
        "mismatches": sum(item["match"] is False for item in results),
        "fallbacks": sum(item["model_status"] == "fallback" for item in results),
        "results": results,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in payload.items() if key != "results"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
