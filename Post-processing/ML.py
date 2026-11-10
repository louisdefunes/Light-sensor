import argparse
import csv
import re
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_DATASET = SCRIPT_DIR / "dataset.csv"
DEFAULT_MODEL = SCRIPT_DIR / "one_class_svm.joblib"
SAMPLE_PERIOD_MS = 10.0
MAX_RESPONSE_DELAY_MS = 2000.0
SAMPLE_COLUMN = re.compile(r"^(user|reference)_sample_(\d+)$")
FEATURE_NAMES = (
    "best_agreement",
    "best_response_delay_ms",
    "response_polarity",
    "ones_ratio_error",
    "transition_ratio",
)


def load_recordings(path: Path) -> list[tuple[list[int], list[int]]]:
    with path.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError(f"{path} musi zawierać kolumnę 'label'.")

        columns: dict[str, list[tuple[int, str]]] = {
            "user": [],
            "reference": [],
        }
        for column in reader.fieldnames:
            match = SAMPLE_COLUMN.fullmatch(column)
            if match:
                signal_name, index_text = match.groups()
                columns[signal_name].append((int(index_text), column))

        for signal_name in columns:
            columns[signal_name].sort()
        if not columns["user"] or len(columns["user"]) != len(columns["reference"]):
            raise ValueError(
                f"{path} musi zawierać jednakową liczbę kolumn "
                "'user_sample_NNN' i 'reference_sample_NNN'."
            )
        if [index for index, _ in columns["user"]] != list(
            range(len(columns["user"]))
        ) or [index for index, _ in columns["reference"]] != list(
            range(len(columns["reference"]))
        ):
            raise ValueError(f"{path} musi mieć ciągłe indeksy próbek od zera.")

        rows = list(reader)

    if not rows:
        raise ValueError(f"{path} nie zawiera pomiarów.")

    recordings = []
    for row_number, row in enumerate(rows, start=2):
        try:
            label = int(row["label"])
            user_signal = [int(row[column]) for _, column in columns["user"]]
            reference_signal = [
                int(row[column]) for _, column in columns["reference"]
            ]
        except (TypeError, ValueError, KeyError) as error:
            raise ValueError(
                f"{path}, wiersz {row_number}: nieprawidłowa etykieta lub próbka."
            ) from error

        if label != 1:
            raise ValueError(
                f"{path}, wiersz {row_number}: OneClassSVM w tym skrypcie "
                "uczy się wyłącznie na własnych pomiarach z etykietą 1."
            )
        if any(value not in (0, 1) for value in user_signal + reference_signal):
            raise ValueError(
                f"{path}, wiersz {row_number}: sygnały muszą zawierać "
                "wyłącznie wartości 0 lub 1."
            )
        recordings.append((user_signal, reference_signal))

    return recordings


def extract_response_features(
    user_signal: list[int],
    reference_signal: list[int],
    max_response_delay_ms: float = MAX_RESPONSE_DELAY_MS,
) -> list[float]:
    if len(user_signal) != len(reference_signal) or not user_signal:
        raise ValueError("Sygnały muszą być niepuste i mieć jednakową długość.")
    if any(value not in (0, 1) for value in user_signal + reference_signal):
        raise ValueError("Sygnały muszą zawierać wyłącznie wartości 0 lub 1.")

    max_lag = min(
        int(max_response_delay_ms / SAMPLE_PERIOD_MS),
        len(user_signal) - 1,
    )
    best_agreement = -1.0
    best_lag = 0
    best_polarity = 1

    for polarity in (1, -1):
        for lag in range(max_lag + 1):
            reference_aligned = reference_signal[: len(reference_signal) - lag or None]
            user_aligned = user_signal[lag:]
            matches = sum(
                user == (reference if polarity == 1 else 1 - reference)
                for user, reference in zip(user_aligned, reference_aligned)
            )
            agreement = matches / len(user_aligned)
            if agreement > best_agreement:
                best_agreement = agreement
                best_lag = lag
                best_polarity = polarity

    user_transitions = sum(
        previous != current
        for previous, current in zip(user_signal, user_signal[1:])
    )
    reference_transitions = sum(
        previous != current
        for previous, current in zip(reference_signal, reference_signal[1:])
    )
    expected_ones_ratio = sum(reference_signal) / len(reference_signal)
    if best_polarity == -1:
        expected_ones_ratio = 1.0 - expected_ones_ratio

    return [
        best_agreement,
        best_lag * SAMPLE_PERIOD_MS,
        float(best_polarity),
        sum(user_signal) / len(user_signal) - expected_ones_ratio,
        user_transitions / max(reference_transitions, 1),
    ]


def make_feature_matrix(
    recordings: list[tuple[list[int], list[int]]],
    max_response_delay_ms: float = MAX_RESPONSE_DELAY_MS,
) -> np.ndarray:
    return np.asarray(
        [
            extract_response_features(user, reference, max_response_delay_ms)
            for user, reference in recordings
        ],
        dtype=float,
    )


def train_model(
    dataset_path: Path,
    model_path: Path,
    nu: float,
    max_response_delay_ms: float,
) -> None:
    recordings = load_recordings(dataset_path)
    features = make_feature_matrix(recordings, max_response_delay_ms)

    estimator = make_pipeline(
        StandardScaler(),
        OneClassSVM(kernel="rbf", nu=nu, gamma="scale"),
    )
    estimator.fit(features)
    training_predictions = estimator.predict(features)

    model_bundle: dict[str, Any] = {
        "estimator": estimator,
        "feature_names": FEATURE_NAMES,
        "sample_period_ms": SAMPLE_PERIOD_MS,
        "max_response_delay_ms": max_response_delay_ms,
        "nu": nu,
        "training_sample_count": len(recordings),
    }
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_bundle, model_path)

    rejected = int(np.count_nonzero(training_predictions == -1))
    print(f"Wytrenowano OneClassSVM na {len(recordings)} własnych pomiarach.")
    print(f"Liczba cech odpowiedzi: {features.shape[1]} ({', '.join(FEATURE_NAMES)}).")
    print(
        f"Próbki treningowe oznaczone jako odstające: "
        f"{rejected}/{len(recordings)}."
    )
    print(f"Model zapisano do: {model_path}")
    print("Ocena na danych treningowych nie jest miarą skuteczności na nowych osobach.")


def load_model(model_path: Path = DEFAULT_MODEL) -> dict[str, Any]:
    model_bundle = joblib.load(model_path)
    if not isinstance(model_bundle, dict) or "estimator" not in model_bundle:
        raise ValueError(f"{model_path} nie zawiera obsługiwanego modelu.")
    return model_bundle


def predict_measurement(
    model_bundle: dict[str, Any],
    user_signal: list[int],
    reference_signal: list[int],
) -> tuple[bool, float]:
    features = extract_response_features(
        user_signal,
        reference_signal,
        model_bundle["max_response_delay_ms"],
    )
    feature_row = np.asarray([features], dtype=float)
    prediction = int(model_bundle["estimator"].predict(feature_row)[0])
    score = float(model_bundle["estimator"].decision_function(feature_row)[0])
    return prediction == 1, score


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Trenuje OneClassSVM na własnych, sparowanych sygnałach "
            "użytkownika i referencyjnych; zapisuje model joblib."
        )
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
        help=f"wejściowy dataset (domyślnie: {DEFAULT_DATASET})",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=DEFAULT_MODEL,
        help=f"plik modelu joblib (domyślnie: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--nu",
        type=float,
        default=0.1,
        help="górne oszacowanie udziału odstających próbek treningowych (domyślnie: 0.1)",
    )
    parser.add_argument(
        "--max-response-delay-ms",
        type=float,
        default=MAX_RESPONSE_DELAY_MS,
        help=(
            "maksymalne opóźnienie odpowiedzi uwzględniane przy dopasowaniu "
            f"(domyślnie: {MAX_RESPONSE_DELAY_MS:g} ms)"
        ),
    )
    args = parser.parse_args()

    if not 0 < args.nu <= 1:
        parser.error("--nu musi należeć do przedziału (0, 1]")
    if args.max_response_delay_ms < 0:
        parser.error("--max-response-delay-ms nie może być ujemne")
    if args.dataset.resolve() == args.model.resolve():
        parser.error("plik modelu nie może być tym samym plikiem co dataset")

    train_model(
        args.dataset,
        args.model,
        args.nu,
        args.max_response_delay_ms,
    )


if __name__ == "__main__":
    main()
