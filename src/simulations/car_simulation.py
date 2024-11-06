class CarSimulator:
    def __init__(self, car_mass: float):  # kg
        self.car_mass = car_mass

    def calculate_acceleration(self, force: float) -> float:
        return force / self.car_mass
