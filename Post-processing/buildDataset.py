import argparse
import csv
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SCRIPT_DIR.parent / "pomiary_testowe.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "dataset.csv"
SAMPLE_COUNT = 1000


def load_recordings(path: Path) -> list[tuple[list[int], list[int]]]:
    recordings: dict[int, dict[int, tuple[int, int]]] = defaultdict(dict)

    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        expected_columns = {
            "measurement",
            "sample_index",
            "user_signal",
            "reference_signal",
        }
        if not reader.fieldnames or not expected_columns.issubset(reader.fieldnames):
            raise ValueError(
                f"{path} musi zawierać kolumny: "
                f"{', '.join(sorted(expected_columns))}."
            )

        for line_number, row in enumerate(reader, start=2):
            try:
                measurement = int(row["measurement"])
                sample_index = int(row["sample_index"])
                user_value = int(row["user_signal"])
                reference_value = int(row["reference_signal"])
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"{path}, wiersz {line_number}: "
                    "nieprawidłowa wartość pomiaru lub sygnału."
                ) from error

            if measurement < 1:
                raise ValueError(
                    f"{path}, wiersz {line_number}: numer pomiaru musi być dodatni."
                )
            if not 0 <= sample_index < SAMPLE_COUNT:
                raise ValueError(
                    f"{path}, wiersz {line_number}: indeks próbki musi być "
                    f"w zakresie 0..{SAMPLE_COUNT - 1}."
                )
            if user_value not in (0, 1) or reference_value not in (0, 1):
                raise ValueError(
                    f"{path}, wiersz {line_number}: sygnały muszą zawierać "
                    "wyłącznie wartości 0 lub 1."
                )
            if sample_index in recordings[measurement]:
                raise ValueError(
                    f"{path}, wiersz {line_number}: powtórzony indeks "
                    f"{sample_index} w pomiarze {measurement}."
                )

            recordings[measurement][sample_index] = (user_value, reference_value)

    if not recordings:
        raise ValueError(f"{path} nie zawiera żadnych pomiarów.")

    result = []
    for measurement, samples in sorted(recordings.items()):
        if len(samples) != SAMPLE_COUNT:
            raise ValueError(
                f"Pomiar {measurement} zawiera {len(samples)} próbek; "
                f"oczekiwano {SAMPLE_COUNT}."
            )
        if set(samples) != set(range(SAMPLE_COUNT)):
            raise ValueError(
                f"Pomiar {measurement} nie zawiera wszystkich indeksów "
                f"0..{SAMPLE_COUNT - 1}."
            )

        user_signal = [samples[index][0] for index in range(SAMPLE_COUNT)]
        reference_signal = [samples[index][1] for index in range(SAMPLE_COUNT)]
        result.append((user_signal, reference_signal))

    return result


def write_dataset(
    recordings: list[tuple[list[int], list[int]]], path: Path
) -> None:
    sample_columns = [
        f"user_sample_{index:03}" for index in range(SAMPLE_COUNT)
    ] + [f"reference_sample_{index:03}" for index in range(SAMPLE_COUNT)]

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.writer(destination)
        writer.writerow(["label", *sample_columns])
        for user_signal, reference_signal in recordings:
            writer.writerow([1, *user_signal, *reference_signal])


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Tworzy dataset.csv z własnych pomiarów, zachowując osobno "
            "sygnał użytkownika i sygnał referencyjny."
        )
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"wejściowy CSV (domyślnie: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"wyjściowy CSV (domyślnie: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    if args.input.resolve() == args.output.resolve():
        parser.error("plik wyjściowy nie może być tym samym plikiem co wejściowy")

    recordings = load_recordings(args.input)
    write_dataset(recordings, args.output)
    print(
        f"Zapisano {len(recordings)} pomiarów "
        f"({SAMPLE_COUNT} próbek na sygnał) do {args.output}."
    )


if __name__ == "__main__":
    main()
