import serial
import csv
import matplotlib.pyplot as plt

# Zmień port na ten, którego używasz (COM3 lub /dev/ttyUSB0 na RPi5)
ser = serial.Serial('COM3', 115200)
ser.reset_input_buffer()
print('Połączono z', ser.name)

START = b'\xAA'
END = b'\xBB'
SAMPLES_TO_COLLECT = 1

collected_data = []

print(f"Oczekiwanie na {SAMPLES_TO_COLLECT} próbki...")

while len(collected_data) < SAMPLES_TO_COLLECT:
    b = ser.read(1)
    
    if b == START:
        payload = bytearray()
        while True:
            chunk = ser.read(1)
            if chunk == END:
                break
            payload.append(chunk[0])
            
        # Zapisujemy tylko jeśli payload ma sensowną długość (np. 1000)
        if len(payload) > 0:
            features = list(payload)
            collected_data.append(features)
            print(f"Odebrano próbkę {len(collected_data)}/{SAMPLES_TO_COLLECT} (długość: {len(features)})")

ser.close()

# 1. Zapis do CSV
csv_filename = "pomiary_testowe.csv"
with open(csv_filename, mode='w', newline='') as file:
    writer = csv.writer(file)
    # Zapisz każdą próbkę jako osobny wiersz
    for row in collected_data:
        writer.writerow(row)
print(f"Zapisano dane do pliku {csv_filename}")

# 2. Wizualizacja nakładająca się
plt.figure(figsize=(12, 6))
for i, features in enumerate(collected_data):
    # Dodajemy minimalne przesunięcie w osi Y (np. i * 0.05), 
    # żeby linie nie pokryły się w 100% i były czytelne
    offset_y = [val + (i * 0.05) for val in features]
    plt.plot(offset_y, label=f'Próbka {i+1}')

plt.title('Nałożone próbki z fotorezystora (ESP32)')
plt.xlabel('Numer próbki (czas)')
plt.ylabel('Stan (1 = zasłonięty)')
plt.legend(loc='upper right')
plt.grid(True)
plt.show()