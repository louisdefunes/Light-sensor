import serial
import joblib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent

ser = serial.Serial('COM3', 115200)
ser.reset_input_buffer()
print('Connected to', ser.name)

START = b'\xAA'
END = b'\xBB'
p_flag = 0

while True:
    b = ser.read()
    if p_flag:
        print(b)
    if not b:
        continue

    if b == START:
        p_flag = 1
        payload = bytearray()
        while True:
            chunk = ser.read(1)
            if not chunk:
                continue
            if chunk == END:
                print(b)
                p_flag = 0
                break
            payload.append(chunk[0])
        print('features:\n', list(payload))

        model = joblib.load(SCRIPT_DIR / "model.joblib")
        wynik = model.predict([list(payload)])[0]

        print ("Access granted" if wynik == 1 else "Access denied")

