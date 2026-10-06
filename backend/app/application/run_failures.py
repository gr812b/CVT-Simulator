"""Safe run failures shared by the CINDER adapter and its bounded child.

The exception cause stays in worker logs. Only the stable code, safe message,
and execution phase are sent to the application.
"""


class RunFailure(RuntimeError):
    def __init__(self, code: str, message: str, *, phase: str = "simulation"):
        super().__init__(message)
        self.code = code
        self.phase = phase

    def as_error(self) -> dict:
        return {
            "code": self.code,
            "message": str(self),
            "details": {"phase": self.phase},
        }
