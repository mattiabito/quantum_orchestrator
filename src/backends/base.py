from abc import ABC, abstractmethod
from qiskit import QuantumCircuit


class BackendAdapter(ABC):
    """
    Abstract base class for all backend providers.
    Every provider (IBM, AWS, IonQ) must implement these methods.
    The orchestrator only speaks to this interface — never to a specific provider.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the backend is reachable and operational."""
        pass

    @abstractmethod
    def estimated_queue_s(self) -> float:
        """Returns the estimated queue time in seconds."""
        pass

    @abstractmethod
    def run(self, circuit: QuantumCircuit, shots: int) -> dict:
        """
        Runs the circuit and returns a result dict with keys:
          backend, shots, counts, execution_time_s, queue_time_s, fidelity
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for logging and graphs."""
        pass