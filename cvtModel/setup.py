"""Editable-install configuration for the CINDER package.

The repository can temporarily retain ``src/cvt_simulator`` while it is being
retired.  This distribution intentionally installs only ``cinder`` so old code
cannot become an accidental dependency of the new public package.
"""

from pathlib import Path

from setuptools import find_packages, setup

ROOT = Path(__file__).resolve().parent

setup(
    name="cinder-cvt",
    version="0.1.0",
    description="Mechanics-first dynamic modelling for rubber V-belt CVTs.",
    long_description=(ROOT / "README.md").read_text(encoding="utf-8"),
    long_description_content_type="text/markdown",
    python_requires=">=3.10",
    package_dir={"": "src"},
    packages=find_packages(where="src", include=("cinder", "cinder.*")),
    package_data={"cinder": ["py.typed"]},
    install_requires=[
        "numpy>=1.24",
        "scipy>=1.10",
    ],
    extras_require={
        "dev": [
            "black>=24.0",
            "coverage>=7.0",
            "flake8>=7.0",
            "pytest>=8.0",
        ],
    },
)
