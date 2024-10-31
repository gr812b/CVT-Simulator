class CarSimulator:
    def __init__(self, car_mass):
        self.car_mass = car_mass

    def calculate_acceleration(self, force):
        return force / self.car_mass
