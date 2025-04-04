import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ------------------------------
# PARAMETERS
# ------------------------------

# Time offset in seconds to adjust real data timestamps if needed.
time_offset = -7  

# ------------------------------
# FUNCTION DEFINITIONS
# ------------------------------

def plot_engine_rpm_vs_speed(real_df, sim_df):
    """
    Plots Engine RPM vs Speed using a dual-axis plot.
    Interpolates the real engine RPM (based on speed) at the simulated speed points,
    computes the error and MSE, and then plots both curves along with the error.
    """
    # Interpolate the real engine RPM values based on speed
    interp_real_rpm = np.interp(sim_df['car_velocity'], real_df['GPS SPEED'], real_df['RPM PRIM'])
    
    # Calculate error and Mean Squared Error (MSE)
    rpm_error = sim_df['engine_rpm'] - interp_real_rpm
    mse_rpm = np.mean(rpm_error**2)
    print("MSE for Engine RPM vs Speed:", mse_rpm)
    
    # Create a dual-axis plot
    fig, ax1 = plt.subplots(figsize=(12, 8))
    
    # Primary axis: Engine RPM curves
    ax1.plot(sim_df['car_velocity'], sim_df['engine_rpm'], '-', label='Simulated Engine RPM', linewidth=2)
    ax1.plot(sim_df['car_velocity'], interp_real_rpm, '-', label='Real Engine RPM (interpolated)', linewidth=2)
    ax1.set_xlabel("Speed (km/h)")
    ax1.set_ylabel("Engine RPM")
    ax1.set_title("Engine RPM vs Speed with Error")
    ax1.legend(loc='upper left')
    
    # Secondary axis: Error plot
    ax2 = ax1.twinx()
    ax2.plot(sim_df['car_velocity'], rpm_error, '-', color='red', label='Engine RPM Error', linewidth=2)
    ax2.set_ylabel("Error (RPM)")
    ax2.legend(loc='upper right')
    
    plt.show()


def plot_velocity_analysis(real_df, sim_df):
    """
    Plots Velocity vs Time using a dual-axis plot.
    Interpolates the real velocity from the real data (GPS SPEED) onto the simulated time grid,
    computes the error and MSE, and then plots both curves along with the error.
    """
    # Interpolate the real velocity values based on time
    interp_real_velocity = np.interp(sim_df['time'], real_df['time_s'], real_df['GPS SPEED'])
    
    # Calculate error and Mean Squared Error (MSE) for velocity
    velocity_error = sim_df['car_velocity'] - interp_real_velocity
    mse_velocity = np.mean(velocity_error**2)
    print("MSE for Velocity:", mse_velocity)
    
    # Create a dual-axis plot for velocities over time
    fig, ax1 = plt.subplots(figsize=(12, 8))
    
    # Primary axis: Velocity curves
    ax1.plot(sim_df['time'], sim_df['car_velocity'], '-', label='Simulated Velocity', linewidth=2)
    ax1.plot(sim_df['time'], interp_real_velocity, '-', label='Real Velocity (interpolated)', linewidth=2)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Velocity (km/h)")
    ax1.set_title("Velocity vs Time with Error")
    ax1.legend(loc='upper left')
    
    # Secondary axis: Velocity error
    ax2 = ax1.twinx()
    ax2.plot(sim_df['time'], velocity_error, '-', color='red', label='Velocity Error', linewidth=2)
    ax2.set_ylabel("Error (km/h)")
    ax2.legend(loc='upper right')
    
    plt.show()


def plot_position_analysis(real_df, sim_df):
    """
    Estimates the real position by integrating the real GPS SPEED over time.
    Assumes the GPS SPEED is in km/h (converting it to m/s for integration) and uses the time steps in real data.
    Interpolates the estimated real position onto the simulation time grid to compare with the simulated car_position.
    Computes and prints the MSE, and creates a dual-axis plot for the positions and error.
    """
    # Convert real GPS SPEED from km/h to m/s for integration
    real_speed_ms = real_df['GPS SPEED'] / 3.6
    
    # Compute time differences in seconds; prepend the first time value to maintain array length
    time_diff = np.diff(real_df['time_s'], prepend=real_df['time_s'].iloc[0])
    
    # Estimate position by integrating speed over time (using cumulative sum)
    # Initial position is assumed to be 0.
    real_position = np.cumsum(real_speed_ms * time_diff)
    
    # Interpolate the estimated real position onto the simulation time axis
    interp_real_position = np.interp(sim_df['time'], real_df['time_s'], real_position)
    
    # Calculate error and Mean Squared Error (MSE) for position
    position_error = sim_df['car_position'] - interp_real_position
    mse_position = np.mean(position_error**2)
    print("MSE for Position:", mse_position)
    
    # Create a dual-axis plot for position over time
    fig, ax1 = plt.subplots(figsize=(12, 8))
    
    # Primary axis: Position curves
    ax1.plot(sim_df['time'], sim_df['car_position'], '-', label='Simulated Position', linewidth=2)
    ax1.plot(sim_df['time'], interp_real_position, '-', label='Real Position (integrated)', linewidth=2)
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Position (m)")
    ax1.set_title("Position vs Time with Error")
    ax1.legend(loc='upper left')
    
    # Secondary axis: Position error
    ax2 = ax1.twinx()
    ax2.plot(sim_df['time'], position_error, '-', color='red', label='Position Error', linewidth=2)
    ax2.set_ylabel("Error (m)")
    ax2.legend(loc='upper right')
    
    plt.show()


# ------------------------------
# MAIN EXECUTION
# ------------------------------

if __name__ == '__main__':
    # Read the CSV files
    # Real data expected columns: 'Timestamp (ms)', 'GPS SPEED', 'RPM PRIM'
    real_df = pd.read_csv("./src/validation/real_data.csv")
    
    # Simulated data expected columns: 'time', 'car_velocity', 'car_position', 'shift_distance', 
    # 'engine_angular_position', 'secondary_angular_position', 'engine_angular_velocity'
    sim_df = pd.read_csv("./front_end_output.csv")
    
    # Preprocess real data: adjust the time column.
    real_df['time_s'] = (real_df['Timestamp (ms)'] - real_df['Timestamp (ms)'].iloc[0]) / 1000.0 + time_offset
    
    # For simulated data, assume 'car_velocity' is already in km/h.
    # Also, assign the simulated engine RPM from the appropriate column.
    sim_df['engine_rpm'] = sim_df['engine_angular_velocity']
    
    # Call the function to plot engine RPM vs speed analysis
    plot_engine_rpm_vs_speed(real_df, sim_df)
    
    # Call the function to plot velocity analysis over time
    plot_velocity_analysis(real_df, sim_df)
    
    # Call the function to plot position analysis over time
    plot_position_analysis(real_df, sim_df)
