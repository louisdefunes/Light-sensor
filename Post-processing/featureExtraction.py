import argparse
import csv
import statistics
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR / "10 probek TEST.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "features.csv"
SUMMARY_COLUMNS = (
    "sample_count",
    "duration_ms",
    "ones_count",
    "zeros_count",
    "ones_ratio",
    "initial_state",
    "final_state",
    "transition_count",
    "rising_edges",
    "falling_edges",
    "on_run_count",
    "mean_on_duration_ms",
    "std_on_duration_ms",
    "min_on_duration_ms",
    "max_on_duration_ms",
    "off_run_count",
    "mean_off_duration_ms",
    "std_off_duration_ms",
    "min_off_duration_ms",
    "max_off_duration_ms",
    "first_transition_ms",
    "last_transition_ms",
    "mean_transition_interval_ms",
)


def load_samples(path: Path) -> list[list[int]]:
    samples = []
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        for line_number, row in enumerate(csv.reader(csv_file), start=1):
            if not row or all(not value.strip() for value in row):
                continue

            try:
                sample = [int(value.strip()) for value in row]
            except ValueError as error:
                raise ValueError(
                    f"{path}:{line_number}: oczekiwano wartości całkowitych 0 lub 1"
                ) from error

            if any(value not in (0, 1) for value in sample):
                raise ValueError(
                    f"{path}:{line_number}: sygnał zawiera wartość inną niż 0 lub 1"
                )
            samples.append(sample)

    if not samples:
        raise ValueError(f"Plik {path} nie zawiera żadnych próbek.")

    return samples


def duration_features(
    values: list[int], sample_period_ms: float, prefix: str
) -> dict[str, float | int | None]:
    if not values:
        return {
            f"{prefix}_run_count": 0,
            f"mean_{prefix}_duration_ms": None,
            f"std_{prefix}_duration_ms": None,
            f"min_{prefix}_duration_ms": None,
            f"max_{prefix}_duration_ms": None,
        }

    durations = [value * sample_period_ms for value in values]
    return {
        f"{prefix}_run_count": len(durations),
        f"mean_{prefix}_duration_ms": statistics.mean(durations),
        f"std_{prefix}_duration_ms": statistics.pstdev(durations),
        f"min_{prefix}_duration_ms": min(durations),
        f"max_{prefix}_duration_ms": max(durations),
    }


def extract_features(
    sample: list[int], sample_period_ms: float
) -> dict[str, float | int | str | None]:
    if not sample:
        raise ValueError("Próbka nie może być pusta.")

    transitions = []
    ordered_runs = []
    runs = {0: [], 1: []}
    current_value = sample[0]
    run_length = 1

    for index, value in enumerate(sample[1:], start=1):
        if value == current_value:
            run_length += 1
            continue

        runs[current_value].append(run_length)
        ordered_runs.append((current_value, run_length))
        transitions.append(index)
        current_value = value
        run_length = 1
    runs[current_value].append(run_length)
    ordered_runs.append((current_value, run_length))

    ones_count = sum(sample)
    features: dict[str, float | int | str | None] = {
        "sample_count": len(sample),
        "duration_ms": len(sample) * sample_period_ms,
        "ones_count": ones_count,
        "zeros_count": len(sample) - ones_count,
        "ones_ratio": ones_count / len(sample),
        "initial_state": sample[0],
        "final_state": sample[-1],
        "transition_count": len(transitions),
        "rising_edges": sum(
            previous == 0 and current == 1
            for previous, current in zip(sample, sample[1:])
        ),
        "falling_edges": sum(
            previous == 1 and current == 0
            for previous, current in zip(sample, sample[1:])
        ),
    }
    features.update(duration_features(runs[1], sample_period_ms, "on"))
    features.update(duration_features(runs[0], sample_period_ms, "off"))

    transition_times = [index * sample_period_ms for index in transitions]
    features["first_transition_ms"] = (
        transition_times[0] if transition_times else None
    )
    features["last_transition_ms"] = (
        transition_times[-1] if transition_times else None
    )
    features["mean_transition_interval_ms"] = (
        statistics.mean(
            later - earlier
            for earlier, later in zip(transition_times, transition_times[1:])
        )
        if len(transition_times) > 1
        else None
    )

    for number, (sample_index, transition_time) in enumerate(
        zip(transitions, transition_times), start=1
    ):
        features[f"transition_{number:02}_ms"] = transition_time
        features[f"transition_{number:02}_fraction"] = sample_index / len(sample)

    for number, (earlier, later) in enumerate(
        zip(transition_times, transition_times[1:]), start=1
    ):
        features[f"transition_interval_{number:02}_ms"] = later - earlier

    for number, (state, run_length) in enumerate(ordered_runs, start=1):
        features[f"run_{number:02}_state"] = state
        features[f"run_{number:02}_duration_ms"] = run_length * sample_period_ms
        features[f"run_{number:02}_fraction"] = run_length / len(sample)

    return features


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Oblicza cechy czasowe binarnych próbek 0/1 zapisanych "
            "po jednym pomiarze w każdym wierszu CSV."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"wejściowy CSV (domyślnie: {DEFAULT_INPUT.name})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"wyjściowy CSV (domyślnie: {DEFAULT_OUTPUT.name})",
    )
    parser.add_argument(
        "--sample-period-ms",
        type=float,
        default=10.0,
        help="nominalny odstęp między próbkami w ms (domyślnie: 10)",
    )
    args = parser.parse_args()

    if args.sample_period_ms <= 0:
        parser.error("--sample-period-ms musi być większe od zera")
    if args.input.resolve() == args.output.resolve():
        parser.error("plik wyjściowy nie może być tym samym plikiem co wejściowy")

    samples = load_samples(args.input)
    rows = []
    extracted_features = [
        extract_features(sample, args.sample_period_ms) for sample in samples
    ]
    max_transitions = max(
        features["transition_count"] for features in extracted_features
    )
    max_runs = max(
        features["on_run_count"] + features["off_run_count"]
        for features in extracted_features
    )
    event_columns = []
    for number in range(1, max_transitions + 1):
        event_columns.extend(
            (
                f"transition_{number:02}_ms",
                f"transition_{number:02}_fraction",
            )
        )
    for number in range(1, max_transitions):
        event_columns.append(f"transition_interval_{number:02}_ms")
    for number in range(1, max_runs + 1):
        event_columns.extend(
            (
                f"run_{number:02}_state",
                f"run_{number:02}_duration_ms",
                f"run_{number:02}_fraction",
            )
        )

    for measurement_number, sample in enumerate(samples, start=1):
        features = extracted_features[measurement_number - 1]
        rows.append(
            {
                "measurement": measurement_number,
                "sample_period_ms": args.sample_period_ms,
                **{column: features[column] for column in SUMMARY_COLUMNS},
                **{column: features.get(column, "") for column in event_columns},
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Przetworzono {len(rows)} pomiarów.")
    print(f"Cechy zapisano do: {args.output}")


if __name__ == "__main__":
    main()
