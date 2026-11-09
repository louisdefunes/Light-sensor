import csv
import re
from pathlib import Path

import numpy as np
from sklearn.impute import SimpleImputer
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM, SVC


SCRIPT_DIR = Path(__file__).resolve().parent
DATASETS = (
    ("surowy", SCRIPT_DIR / "dataset.csv"),
    ("cechy", SCRIPT_DIR / "datasetF.csv"),
)
TRANSITION_COLUMN = re.compile(r"^transition_(\d+)_ms$")
FEATURE_TRANSITION_LIMIT = 8
TEST_SIZE = 0.25
RANDOM_STATE = 11


def load_dataset(path: Path, dataset_type: str) -> tuple[np.ndarray, np.ndarray]:
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if not reader.fieldnames or "label" not in reader.fieldnames:
            raise ValueError(f"{path} musi zawierać kolumnę 'label'.")

        if dataset_type == "surowy":
            feature_columns = [
                column
                for column in reader.fieldnames
                if column.startswith("sample_")
            ]
        else:
            transition_columns = sorted(
                (
                    column
                    for column in reader.fieldnames
                    if TRANSITION_COLUMN.match(column)
                ),
                key=lambda column: int(TRANSITION_COLUMN.match(column).group(1)),
            )
            feature_columns = [
                "transition_count",
                *transition_columns[:FEATURE_TRANSITION_LIMIT],
            ]
            feature_columns = [
                column for column in feature_columns if column in reader.fieldnames
            ]

        rows = list(reader)

    if not rows or not feature_columns:
        raise ValueError(f"{path} nie zawiera pomiarów ani odpowiednich cech.")

    valid_rows = []
    invalid_count = 0
    try:
        for row in rows:
            values = [
                float(row[column]) if row[column].strip() else np.nan
                for column in feature_columns
            ]
            transition_count = (
                float(row["transition_count"])
                if "transition_count" in row and row["transition_count"].strip()
                else None
            )
            if transition_count is None and dataset_type == "surowy":
                transition_count = sum(
                    current != previous for previous, current in zip(values, values[1:])
                )
            elif transition_count is None:
                transition_count = sum(
                    not np.isnan(value)
                    for column, value in zip(feature_columns, values)
                    if TRANSITION_COLUMN.match(column)
                )
            if transition_count == 0:
                invalid_count += 1
                continue
            valid_rows.append((int(row["label"]), values))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path} zawiera nieprawidłowe etykiety lub cechy.") from error

    if invalid_count:
        print(f"  Odrzucono {invalid_count} próbek bez zmian stanu.")
    if not valid_rows:
        raise ValueError(f"{path} nie zawiera prawidłowych próbek.")

    labels = np.array([label for label, _ in valid_rows], dtype=int)
    features = np.array([values for _, values in valid_rows], dtype=float)

    if not np.isin(labels, (0, 1)).all():
        raise ValueError(f"{path}: etykiety muszą być binarne (1=Igor, 0=inni).")
    if np.isinf(features).any():
        raise ValueError(f"{path} zawiera nieskończone wartości cech.")

    return features, labels


def print_metrics(
    model_name: str,
    predictions: np.ndarray,
    labels: np.ndarray,
    accepted_label: int,
) -> None:
    genuine = labels == 1
    impostors = labels == 0
    false_rejections = int(np.count_nonzero(predictions[genuine] != accepted_label))
    false_acceptances = int(np.count_nonzero(predictions[impostors] == accepted_label))

    frr = false_rejections / np.count_nonzero(genuine)
    far = false_acceptances / np.count_nonzero(impostors)
    print(
        f"  {model_name}: "
        f"FRR {false_rejections}/{np.count_nonzero(genuine)} = {frr:.1%}; "
        f"FAR {false_acceptances}/{np.count_nonzero(impostors)} = {far:.1%}"
    )


def evaluate_dataset(
    dataset_name: str,
    dataset_path: Path,
    test_size: float,
    random_state: int,
) -> None:
    features, labels = load_dataset(dataset_path, dataset_name)
    if np.count_nonzero(labels == 1) < 2 or np.count_nonzero(labels == 0) < 2:
        raise ValueError(f"{dataset_path}: potrzeba co najmniej 2 próbek każdej klasy.")

    x_train, x_test, y_train, y_test = train_test_split(
        features,
        labels,
        test_size=test_size,
        random_state=random_state,
        stratify=labels,
    )

    svc = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        SVC(class_weight="balanced"),
    )
    svc.fit(x_train, y_train)
    svc_predictions = svc.predict(x_test)

    genuine_train = x_train[y_train == 1]
    one_class_svm = make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        OneClassSVM(kernel="rbf", nu=0.1, gamma="scale"),
    )
    one_class_svm.fit(genuine_train)
    one_class_predictions = one_class_svm.predict(x_test)

    train_igor_count = int(np.count_nonzero(y_train == 1))
    train_other_count = int(np.count_nonzero(y_train == 0))
    test_igor_count = int(np.count_nonzero(y_test == 1))
    test_other_count = int(np.count_nonzero(y_test == 0))
    print(
        f"\n{dataset_name} ({dataset_path.name}), {features.shape[1]} cech\n"
        f"  Podział: trening {len(x_train)} "
        f"(Igor {train_igor_count}, inni {train_other_count}); "
        f"test {len(x_test)} "
        f"(Igor {test_igor_count}, inni {test_other_count})\n"
        f"  SVC uczy się na: {len(x_train)} próbkach "
        f"(Igor {train_igor_count}, inni {train_other_count})\n"
        f"  OneClassSVM uczy się na: {len(genuine_train)} próbkach Igora"
    )
    print_metrics("SVC", svc_predictions, y_test, accepted_label=1)
    print_metrics("OneClassSVM", one_class_predictions, y_test, accepted_label=1)


def main() -> None:
    for dataset_type, dataset_path in DATASETS:
        if not dataset_path.is_file():
            print(f"Pominięto {dataset_path.name}: plik nie istnieje.")
            continue
        evaluate_dataset(
            dataset_type,
            dataset_path,
            test_size=TEST_SIZE,
            random_state=RANDOM_STATE,
        )


if __name__ == "__main__":
    main()
