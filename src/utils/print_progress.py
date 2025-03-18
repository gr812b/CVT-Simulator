import csv
import os
import sys

filePath = "progress_percent.csv"
lockFile = "progress_percent.lock"


def print_progress(progress):
    progress_str = f"{progress*100:.2f}"

    with open(lockFile, "w") as f:
        f.write("locked")

    with open(filePath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Percent"])
        writer.writerow([progress_str])
    
    os.remove(lockFile)

    sys.stdout.write(f"\rProgress: {progress_str}%")
    sys.stdout.flush()
