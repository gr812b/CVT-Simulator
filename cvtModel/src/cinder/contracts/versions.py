"""Explicit versions for CINDER's public serialized artifacts.

Each public artifact evolves independently.  A change to simulation-result
projection does not imply a change to saved input documents, catalogs, or
static-study projections.
"""

ASSEMBLY_DOCUMENT_SCHEMA_VERSION = 1
SIMULATION_CASE_SCHEMA_VERSION = 1
COMPONENT_CATALOG_CONTRACT_VERSION = 1
CONVENTIONS_CONTRACT_VERSION = 1
STUDY_RESULT_CONTRACT_VERSION = 1
SIMULATION_RESULT_CONTRACT_VERSION = 2
