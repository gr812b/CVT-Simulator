# CVT Simulator Source Code

This repository contains the source code for **CVT Simulator**. The folders and files for this project are organized as follows:

## Folder Structure

- **constants/**  
  Contains all the constant definitions and configuration values that are used throughout the project. Keeping these values in a dedicated folder helps to manage configurations centrally.

- **frontend/**  
  Houses the user interface components. This includes the Unity project or any other assets required for the presentation layer of the application.

- **simulations/**  
  Contains the core logic for running simulations. This folder includes modules and scripts that implement the simulation functionality.

- **utils/**  
  Provides utility functions and helper modules used across various parts of the project. These tools simplify repetitive tasks and improve code maintainability.

## Files

- **README.md**  
  This file, which provides an overview of the source code structure and guidelines for working with the project.

- **calculate_forces.py**  
  A Python script dedicated to computing forces for claculating an equilibrium quickly, useful for quickly determining if the tuning parameters are sound.

- **main.py**  
  The main entry point for the backend of the application. Running this file orchestrates the interaction between the various components in the backend.

## Getting Started

1. **Installation:**  
   Follow the installation instructions in the project documentation to set up your environment and install any necessary dependencies.

2. **Running the Application:**  
   Execute the main script with:
   ```bash
   python main.py
   ```
   Open the Unity editor in order to view the front end.

3. **Testing and Development:**  
   For details on testing or contributing to the project, please refer to the additional documentation provided or the inline comments within the code files.

## Additional Information

For more in-depth explanations of each module or folder, please check the source code files and any accompanying documentation. Your contributions and feedback are welcome!
