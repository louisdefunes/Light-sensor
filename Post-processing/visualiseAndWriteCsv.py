import csv
import time

import matplotlib.pyplot as plt
import serial


# Change the port to the one used by the ESP32 (for example COM3).
PORT = "COM3"
BAUD_RATE = 115200
SAMPLE_COUNT = 1000
SAMPLE_INTERVAL_SECONDS = 0.01
SAMPLES_TO_COLLECT = 1
FRAME_TIMEOUT_SECONDS = 5
CSV_FILENAME = "pomiary_testowe.csv"

START = 0xAA
END = 0xBB
FRAME_SIZE = SAMPLE_COUNT * 2


def read_exactly(ser, size, deadline):
    data = bytearray()
    while len(data) < size and time.monotonic() < deadline:
        chunk = ser.read(size - len(data))
        if chunk:
            data.extend(chunk)
    if len(data) != size:
        return None
    return data


def read_measurement(ser):
    while True:
        marker = ser.read(1)
        if not marker:
            continue
        if marker[0] != START:
            continue

        deadline = time.monotonic() + FRAME_TIMEOUT_SECONDS
        payload = read_exactly(ser, FRAME_SIZE, deadline)
        end_marker = read_exactly(ser, 1, deadline)
        if payload is None or end_marker != bytes([END]):
            print("Niekompletna lub uszkodzona ramka; pomijam.")
            continue
        if any(value not in (0, 1) for value in payload):
            print("Ramka zawiera nieoczekiwane wartości; pomijam.")
            continue

        return payload[:SAMPLE_COUNT], payload[SAMPLE_COUNT:]


def collect_measurements():
    measurements = []
    with serial.Serial(PORT, BAUD_RATE, timeout=0.5) as ser:
        ser.reset_input_buffer()
        print(
            f"Połączono z {ser.name}; oczekiwanie na "
            f"{SAMPLES_TO_COLLECT} pomiar(ów)."
        )

        while len(measurements) < SAMPLES_TO_COLLECT:
            user_signal, reference_signal = read_measurement(ser)
            measurements.append((user_signal, reference_signal))
            print(
                f"Odebrano pomiar {len(measurements)}/"
                f"{SAMPLES_TO_COLLECT}."
            )
    return measurements


def save_measurements(measurements):
    with open(CSV_FILENAME, "w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "measurement",
                "sample_index",
                "time_seconds",
                "user_signal",
                "reference_signal",
            ]
        )
        for measurement_number, (user_signal, reference_signal) in enumerate(
            measurements, start=1
        ):
            for sample_index, (user_value, reference_value) in enumerate(
                zip(user_signal, reference_signal)
            ):
                writer.writerow(
                    [
                        measurement_number,
                        sample_index,
                        sample_index * SAMPLE_INTERVAL_SECONDS,
                        user_value,
                        reference_value,
                    ]
                )
    print(f"Zapisano dane do pliku {CSV_FILENAME}.")


def plot_measurements(measurements):
    time_axis = [
        sample_index * SAMPLE_INTERVAL_SECONDS
        for sample_index in range(SAMPLE_COUNT)
    ]
    figure, axes = plt.subplots(
        len(measurements),
        1,
        figsize=(12, max(4, 3 * len(measurements))),
        sharex=True,
        sharey=True,
        squeeze=False,
    )

    for measurement_number, ((user_signal, reference_signal), axis) in enumerate(
        zip(measurements, axes[:, 0]), start=1
    ):
        axis.step(
            time_axis,
            user_signal,
            where="post",
            label="Sygnał użytkownika",
        )
        axis.step(
            time_axis,
            reference_signal,
            where="post",
            label="Sygnał referencyjny",
            alpha=0.8,
        )
        axis.set_title(f"Pomiar {measurement_number}")
        axis.set_ylabel("Stan")
        axis.set_yticks([0, 1])
        axis.set_ylim(-0.1, 1.1)
        axis.grid(True)
        axis.legend(loc="upper right")

    axes[-1, 0].set_xlabel("Czas [s]")
    figure.suptitle("Porównanie sygnału użytkownika z wzorcem")
    figure.tight_layout()
    plt.show()


def main():
    measurements = collect_measurements()
    save_measurements(measurements)
    plot_measurements(measurements)


if __name__ == "__main__":
    main()
