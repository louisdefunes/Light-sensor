import argparse
import csv
from pathlib import Path

from featureExtraction import extract_features


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent
SAMPLE_PREFIX = "pomiary_testowe"
SAMPLE_PERIOD_MS = 10.0


def load_recordings() -> list[tuple[int, list[int]]]:
    files = sorted(
        path
        for path in DATA_DIR.glob(f"{SAMPLE_PREFIX}*.csv")
        if path.stem.upper() != SAMPLE_PREFIX.upper()
    )
    if not files:
        raise FileNotFoundError(f"Nie znaleziono plików pomiarowych w {DATA_DIR}")

    recordings = []
    invalid_count = 0
    expected_sample_count = None
    for path in files:
        person = path.stem[len(SAMPLE_PREFIX) :].strip("_").upper()
        if not person:
            raise ValueError(f"Nie można ustalić osoby z nazwy pliku {path.name}.")
        label = int(person == "IGOR")

        with path.open("r", newline="", encoding="utf-8-sig") as source:
            for line_number, row in enumerate(csv.reader(source), start=1):
                if not row or all(not value.strip() for value in row):
                    continue
                try:
                    sample = [int(value.strip()) for value in row]
                except ValueError as error:
                    raise ValueError(
                        f"{path.name}, wiersz {line_number}: "
                        "oczekiwano próbek całkowitych."
                    ) from error

                if any(value not in (0, 1) for value in sample):
                    raise ValueError(
                        f"{path.name}, wiersz {line_number}: "
                        "próbka zawiera wartość inną niż 0 lub 1."
                    )
                if all(value == sample[0] for value in sample):
                    print(
                        f"Pominięto nieprawidłową próbkę bez zmian stanu: "
                        f"{path.name}, wiersz {line_number}."
                    )
                    invalid_count += 1
                    continue
                if expected_sample_count is None:
                    expected_sample_count = len(sample)
                elif len(sample) != expected_sample_count:
                    raise ValueError(
                        f"{path.name}, wiersz {line_number}: oczekiwano "
                        f"{expected_sample_count} próbek, otrzymano {len(sample)}."
                    )
                recordings.append((label, sample))

    if not recordings:
        raise ValueError("Pliki pomiarowe nie zawierają żadnych próbek.")
    if not any(label == 1 for label, _ in recordings):
        raise ValueError("Nie znaleziono nagrań Igora do etykietowania.")
    if not any(label == 0 for label, _ in recordings):
        raise ValueError("Nie znaleziono nagrań pozostałych osób.")

    print(f"Pominięto nieprawidłowych próbek: {invalid_count}")
    return recordings


def write_raw_dataset(recordings: list[tuple[int, list[int]]]) -> Path:
    output_path = SCRIPT_DIR / "dataset.csv"
    sample_count = len(recordings[0][1])
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(
            ["label", *[f"sample_{index:03}" for index in range(sample_count)]]
        )
        for label, sample in recordings:
            writer.writerow([label, *sample])
    return output_path


def write_feature_dataset(recordings: list[tuple[int, list[int]]]) -> Path:
    output_path = SCRIPT_DIR / "datasetF.csv"
    extracted = [
        (label, extract_features(sample, SAMPLE_PERIOD_MS))
        for label, sample in recordings
    ]

    columns = list(dict.fromkeys(
        column
        for _, features in extracted
        for column in features
    ))
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=["label", *columns])
        writer.writeheader()
        for label, features in extracted:
            writer.writerow(
                {"label": label, **{column: features.get(column) for column in columns}}
            )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Buduje surowy dataset.csv i/lub cechowy datasetF.csv."
    )
    parser.add_argument(
        "--mode",
        choices=("raw", "features", "both"),
        default="both",
        help="który dataset utworzyć (domyślnie: oba)",
    )
    args = parser.parse_args()

    recordings = load_recordings()
    if args.mode in ("raw", "both"):
        print(f"Zapisano {len(recordings)} pomiarów do {write_raw_dataset(recordings)}")
    if args.mode in ("features", "both"):
        print(
            f"Zapisano {len(recordings)} pomiarów do "
            f"{write_feature_dataset(recordings)}"
        )


if __name__ == "__main__":
    main()
