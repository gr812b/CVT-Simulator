from setuptools import setup, find_packages

setup(
    name="cvt_simulator",
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        "numpy",
        "scipy",
        "matplotlib",
        "black",
        "flake8",
        "pandas",
    ],
)