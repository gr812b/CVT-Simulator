"""Host systems shipped with CINDER."""

from .base import CVTHost, NoHost
from .secondary_shaft_angle import SecondaryShaftAngleHost
from .tire_vehicle import TireVehicleHost

__all__ = ["CVTHost", "NoHost", "SecondaryShaftAngleHost", "TireVehicleHost"]
