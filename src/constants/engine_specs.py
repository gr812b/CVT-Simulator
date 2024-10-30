import math
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt
import numpy as np

# Given engine specifications (torque in ft*lbs)
engineSpecs = [
    {'rpm': 2400, 'torque': 18.5},
    {'rpm': 2600, 'torque': 18.1},
    {'rpm': 2800, 'torque': 17.4},
    {'rpm': 3000, 'torque': 16.6},
    {'rpm': 3200, 'torque': 15.4},
    {'rpm': 3400, 'torque': 14.5},
    {'rpm': 3600, 'torque': 13.5},
]

# SI Units engine specs
engineData = [
    {
        'angular_velocity': (angular_velocity := spec['rpm'] * (2 * math.pi) / 60),
        'torque': (torque := spec['torque'] * 1.3558179483),
        'power': angular_velocity * torque
    }
    for spec in engineSpecs
]


angular_velocities = [point['angular_velocity'] for point in engineData]
torques = [point['torque'] for point in engineData]
powers = [point['power'] for point in engineData]

torque_curve = interp1d(angular_velocities, torques, kind='cubic', fill_value="extrapolate")



if __name__ == "__main__":
  power_curve = interp1d(angular_velocities, powers, kind='cubic', fill_value="extrapolate")

  x = np.linspace(180, 420, 1000)
  plt.plot(x, torque_curve(x))
  plt.scatter(angular_velocities, torques, color='red')
  plt.xlabel('Angular Velocity (rad/s)')
  plt.ylabel('Torque (Nm)')
  plt.title('Engine Torque Curve')
  

  # Add power curve on second y-axis
  ax2 = plt.gca().twinx()
  ax2.plot(x, power_curve(x), color='green')
  ax2.set_ylabel('Power (W)')
  ax2.scatter(angular_velocities, powers, color='green')

  plt.show()
