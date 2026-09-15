"""Fixed-pivot primary flyweight design service.

The geometry/path-domain kernel is intentionally importable without CINDER so
it can be tested in isolation.  Service/CINDER symbols are loaded lazily when
requested by the application.
"""

from .models import ArchitectureDesign, OperatingCondition, PackagingZone, RampDesign

__all__ = [
    "ArchitectureDesign",
    "OperatingCondition",
    "PackagingZone",
    "RampDesign",
    "FixedPivotPrimaryDesignService",
    "PrimaryDesignError",
]


def __getattr__(name: str):
    if name in {"FixedPivotPrimaryDesignService", "PrimaryDesignError"}:
        from .service import FixedPivotPrimaryDesignService, PrimaryDesignError

        return {
            "FixedPivotPrimaryDesignService": FixedPivotPrimaryDesignService,
            "PrimaryDesignError": PrimaryDesignError,
        }[name]
    raise AttributeError(name)
