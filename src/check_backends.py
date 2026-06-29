from qiskit_ibm_runtime import QiskitRuntimeService
from dotenv import load_dotenv
import os

load_dotenv()

service = QiskitRuntimeService(
    channel="ibm_cloud",
    token=os.getenv("IBM_API_KEY"),
    instance=os.getenv("IBM_INSTANCE")
)

print("Backend disponibili nel tuo account:")
for b in service.backends():
    s = b.status()
    print(f"  {b.name:<30} operational: {s.operational}   pending jobs: {s.pending_jobs}")