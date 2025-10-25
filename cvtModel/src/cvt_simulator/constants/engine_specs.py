from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import numpy as np
from cvt_simulator.utils.conversions import rpm_to_rad_s

# Given engine specifications (torque in ft*lbs)
engineSpecs = [
    {"rpm": 1000, "torque": 0},
    {"rpm": 1800, "torque": 18},

    {"rpm": 2400, "torque": 18.5},
    {"rpm": 2600, "torque": 18.1},
    {"rpm": 2800, "torque": 17.4},
    {"rpm": 3000, "torque": 16.6},
    {"rpm": 3200, "torque": 15.4},
    {"rpm": 3400, "torque": 14.5},
    {"rpm": 3600, "torque": 13.5},
    
    {"rpm": 4000, "torque": 0},
]

# SI Units engine specs
engineData = [
    {
        "angular_velocity": (angular_velocity := rpm_to_rad_s(spec["rpm"])),
        "torque": (torque := spec["torque"] * 1.3558179483),
        "power": angular_velocity * torque,
    }
    for spec in engineSpecs
]


angular_velocities = [point["angular_velocity"] for point in engineData]
torques = [point["torque"] for point in engineData]
powers = [point["power"] for point in engineData]

torque_curve = interp1d(
    angular_velocities, torques, kind="cubic", fill_value="extrapolate"
)

def safe_torque_curve(angular_velocity):
    """
    Safe torque curve with realistic physical limits.
    
    Real engines:
    - Can't produce torque when spinning backwards (negative angular velocity)
    - Have maximum safe RPM limits beyond which they fail
    - Can't produce infinite torque
    """
    # Convert to numpy array for element-wise operations
    omega = np.asarray(angular_velocity)
    
    # Define physical limits
    MIN_ANGULAR_VELOCITY = 0.0  # rad/s (engine can't run backwards)
    MAX_ANGULAR_VELOCITY = rpm_to_rad_s(6000)  # rad/s (redline RPM)
    MAX_TORQUE = 30.0  # Nm (reasonable upper bound)
    MIN_TORQUE = -5.0  # Nm (small negative torque for engine braking)
    
    # Clamp angular velocity to safe range
    omega_clamped = np.clip(omega, MIN_ANGULAR_VELOCITY, MAX_ANGULAR_VELOCITY)
    
    # Get torque from interpolation
    torque_raw = torque_curve(omega_clamped)
    
    # Handle negative angular velocities (engine can't run backwards)
    torque_result = np.where(omega < 0, 0.0, torque_raw)
    
    # Clamp torque to physically reasonable bounds
    torque_result = np.clip(torque_result, MIN_TORQUE, MAX_TORQUE)
    
    return torque_result


if __name__ == "__main__":
    power_curve = interp1d(
        angular_velocities, powers, kind="cubic", fill_value="extrapolate"
    )

    x = np.linspace(0, 420, 1000)
    plt.plot(x, torque_curve(x))
    plt.scatter(angular_velocities, torques, color="red")
    plt.xlabel("Angular Velocity (rad/s)")
    plt.ylabel("Torque (Nm)")
    plt.title("Engine Torque Curve")

    # Add power curve on second y-axis
    ax2 = plt.gca().twinx()
    ax2.plot(x, power_curve(x), color="green")
    ax2.set_ylabel("Power (W)")
    ax2.scatter(angular_velocities, powers, color="green")

    plt.show()
