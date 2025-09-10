from models.dataTypes import CarForceBreakdown
from models.engine_model import EngineModel
from models.external_load_model import LoadModel


class CarModel:
    def __init__(
        self,
        car_mass: float,
        load_model: LoadModel,
        engine_model: EngineModel,
    ):
        self.car_mass = car_mass
        self.load_model = load_model
        self.engine_model = engine_model

    def calculate_acceleration(self, velocity: float, angular_velocity: float):
        engineForces = self.engine_model.get_breakdown(angular_velocity)
        load_force = self.load_model.get_breakdown(velocity)

        engine = engineForces.power / velocity
        accel = (engine - load_force.net) / self.car_mass

        return CarForceBreakdown(
            engineForces,
            load_force,
            accel
        )
