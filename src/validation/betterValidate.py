import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ------------------------------
# PARAMETERS
# ------------------------------

# Time offset in seconds to adjust real data timestamps if needed (not used in speed domain here)
time_offset = 0.5  

# ------------------------------
# READ CSV FILES
# ------------------------------

# Read real data CSV file.
# Expected columns: 'Timestamp (ms)', 'GPS SPEED', 'RPM PRIM'
real_df = pd.read_csv("./src/validation/real_data.csv")

# Read simulated data CSV file.
# Expected columns: 'time', 'car_velocity', 'car_position', 'shift_distance', 
# 'engine_angular_position', 'secondary_angular_position', 'engine_angular_velocity'
sim_df = pd.read_csv("./front_end_output.csv")

# ------------------------------
# PREPROCESS DATA
# ------------------------------

# For real data, the speed is already in km/h so no conversion is necessary.
# Adjust real data timestamps if needed (for time-based alignment, though not used in the speed-RPM plot).
real_df['time_s'] = (real_df['Timestamp (ms)'] - real_df['Timestamp (ms)'].iloc[0]) / 1000.0 + time_offset

# For simulated data, assume 'car_velocity' is already in km/h.
# Also, take the simulated engine RPM directly from the 'engine_angular_velocity' column.
sim_df['engine_rpm'] = sim_df['engine_angular_velocity']

# ------------------------------
# INTERPOLATION BASED ON SPEED
# ------------------------------

# Although both files report speed in km/h, their speed values might not exactly match.
# Interpolate the real engine RPM to estimate its values at the simulated speed points.
interp_real_rpm = np.interp(sim_df['car_velocity'], real_df['GPS SPEED'], real_df['RPM PRIM'])

# ------------------------------
# ERROR ANALYSIS (MSE)
# ------------------------------

# Calculate the error between simulated engine RPM and the interpolated real engine RPM.
rpm_error = sim_df['engine_rpm'] - interp_real_rpm

# Compute the Mean Squared Error (MSE) for the engine RPM error.
mse_rpm = np.mean(rpm_error**2)
print("MSE for Engine RPM vs Speed:", mse_rpm)

# ------------------------------
# PLOTTING: Dual Axis Plot
# ------------------------------

fig, ax1 = plt.subplots(figsize=(12, 8))

# Plot the engine RPM curves on the primary y-axis (as lines)
ax1.plot(sim_df['car_velocity'], sim_df['engine_rpm'], '-', label='Simulated Engine RPM', linewidth=2)
ax1.plot(sim_df['car_velocity'], interp_real_rpm, '-', label='Real Engine RPM (interpolated)', linewidth=2)
ax1.set_xlabel("Speed (km/h)")
ax1.set_ylabel("Engine RPM")
ax1.set_title("Engine RPM vs Speed with Error")
ax1.legend(loc='upper left')

# Create a second y-axis for the error
ax2 = ax1.twinx()
ax2.plot(sim_df['car_velocity'], rpm_error, '-', color='red', label='Engine RPM Error', linewidth=2)
ax2.set_ylabel("Error (RPM)")
ax2.legend(loc='upper right')

plt.show()
