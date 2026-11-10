import time
from pathlib import Path

import serial

from ML import DEFAULT_MODEL, load_model, predict_measurement

SCRIPT_DIR = Path(__file__).resolve().parent

PORT = "COM3"
BAUD_RATE = 115200
SAMPLE_COUNT = 1000
FRAME_TIMEOUT_SECONDS = 5

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
            print("Niekompletna lub uszkodzona ramka; czekam na następną.")
            continue
        if any(value not in (0, 1) for value in payload):
            print("Ramka zawiera nieoczekiwane wartości; pomijam.")
            continue

        return payload[:SAMPLE_COUNT], payload[SAMPLE_COUNT:]


def main():
    model_path = SCRIPT_DIR / DEFAULT_MODEL.name
    model_bundle = load_model(model_path)
    print(f"Wczytano model: {model_path}")

    with serial.Serial(PORT, BAUD_RATE, timeout=0.5) as ser:
        ser.reset_input_buffer()
        print(f"Połączono z {ser.name}; oczekiwanie na ramkę pomiarową.")

        measurement_number = 0
        while True:
            user_signal, reference_signal = read_measurement(ser)
            measurement_number += 1
            print(
                f"Pomiar {measurement_number}: "
                f"odebrano po {len(user_signal)} próbek każdego sygnału."
            )
            print("Sygnał użytkownika:", list(user_signal))
            print("Sygnał referencyjny:", list(reference_signal))
            accepted, score = predict_measurement(
                model_bundle,
                list(user_signal),
                list(reference_signal),
            )
            print(f"Wynik modelu: {score:.6f}")
            print("Access Granted" if accepted else "Access Denied")


if __name__ == "__main__":
    main()
