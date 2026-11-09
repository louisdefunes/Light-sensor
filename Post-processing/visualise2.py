import csv
from pathlib import Path

import matplotlib.pyplot as plt


csv_path = Path(__file__).resolve().parent.parent / "pomiary_testoweIGOR.csv"

with csv_path.open("r", newline="", encoding="utf-8-sig") as file:
    samples = [[int(value) for value in row] for row in csv.reader(file) if row]

if not samples:
    raise ValueError(f"Nie znaleziono próbek w pliku {csv_path}")

fig, ax = plt.subplots(figsize=(12, 6))
colors = plt.colormaps["turbo"].resampled(len(samples))
for index, sample in enumerate(samples):
    ax.plot(
        sample,
        color=colors(index),
        alpha=0.65,
        linewidth=1,
    )

colorbar = fig.colorbar(
    plt.cm.ScalarMappable(
        norm=plt.Normalize(vmin=1, vmax=max(2, len(samples))),
        cmap=colors,
    ),
    ticks=range(1, len(samples) + 1, max(1, len(samples) // 10)),
    ax=ax,
)
colorbar.set_label("Numer próbki")
ax.set_title(f"Nałożone próbki z fotorezystora ({len(samples)} pomiarów)")
ax.set_xlabel("Numer próbki (czas)")
ax.set_ylabel("Stan (0/1)")
ax.grid(True)
fig.tight_layout()
plt.show()
