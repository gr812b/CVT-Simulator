# CVT-Simulator

**Authors:**
- [Kai Arseneau](https://github.com/gr812b)
- [Travis Wing](https://github.com/t-wing11)
- [Cameron Dunn](https://github.com/camdnnn)
- [Grace McKenna](https://github.com/gr4cem)

**Date of project start**: September 10, 2024

Our project aims to create an advanced CVT simulation tool that integrates complex mathematical models, a rendering engine, and a user-friendly interface to accurately model the transmission's dynamics. The objective is to streamline the tuning process, allowing for faster adjustments to the transmission and reducing the need for labor-intensive physical testing. By simulating real-world behavior, the tool will help engineers experiment with different tuning parameters to achieve optimal performance, improving vehicle acceleration and torque output.

## License

This project is licensed under the **Creative Commons Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)** license.

- Free for use in personal, educational, or non-commercial projects.
- **Commercial use requires a separate license**. Please contact Kai Arseneau, Cameron Dunn, Travis Wing or Grace McKenna for inquiries regarding commercial licenses.

For more details, see the [LICENSE](./LICENSE) file.

## Project Structure
The folders and files for this project are as follows:

- docs - Documentation for the project
- refs - Reference material used for the project, including papers
- src - Source code
- test - Test cases

## Setup

## Python setup

1. Create and activate a virtual environment
```bash
python -m venv venv
venv\Scripts\activate # or source venv/bin/activate on Mac
```
2. Install the dependencies and setup package
```bash
pip install -e .
```
3. Run the tests
```bash
python -m unittest discover -s tests
```
4. Manually run linter and formatter
```bash
black src/ test/
flake8 src/ test/
```
5. If you want to setup the pre-commit, run:
```bash
pre-commit install
```
