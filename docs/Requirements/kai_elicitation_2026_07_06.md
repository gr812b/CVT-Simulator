Q: What is your main priority with this tool in 1 sentence? <br>
A: To be able to rapidly design and tune a CVT trough quick comparisons to different parameters

Q: What is most important you in a UI? <br>
A: Ease of use, obviousness/clarity of use and should be clean. Clarity and ease of use.

Q: Of those three, how would you rank them in order of importance? <br>
A: Ease of use encapsulates clarity and obviousness.

Q: Do you prioritize form or function? <br>
A: Function, form is only important to not impede function. Would never take a reduction in functionality to make it look prettier. Form is important to make functionality more obvious and clear, but not at the expense of functionality.

Q: How are you currently accomplishing your goal with the current tool? <br>
A: Currently, running ad-hoc scripts to call backend functions and then parse those outputs into graphs and tables.

Q: What are your pain points? <br>
A: Reproducibility of results because you don't know if the scripts and inputs are always the same, creating the scripts is time consuming, and the making changes requires a lot of effort to rewrite the scripts.

Q: What is your ideal workflow? <br>
A: Would not be just one workflow

Q: What would be those workflows? <br>
A: Three workflows where the result of each one feeds into the next. The reason they are separate is that you are likely to repeat each one multiple times before moving on to the next one.

1. Input vehicle details
2. Input to get pulley geometry and metrics about that geometry. 
2a. Input pulley geometry values, tool calculates and outputs metrics about the geometry
2b. Input goals for the pulley geometry, tool calculates and outputs the pulley geometry and metrics about that geometry.
3. The user inputs actuating parameters of the CVT. The output is information about the selected inputs and how they would perform in certain metrics. No optimization just user inputs
4. Tuning flows, there's multiple versions of the tuning flow. They all share that they take all the inputs and then output time integrated results over multiple metrics. <br>
4a. Give one set of inputs. The tool would time integrate over the metrics. Outputs would be the time results over the metrics for those inputs. The goal is to be able to see how that specific set of inputs performs over the metrics. <br>
4b. Give two or more specific set of inputs. The tool would time integrate for those sets of inputs over the metrics. Outputs would be the time results over the metrics for those inputs. The goal is to be able to compare the results of different sets of inputs to see how they perform. <br>
4c. Give targets that you want to achieve and the inputs outside of the ones those targets solve for. Targets are specific sets of values which fully determine a specific set of parameters that can be solved for. The tool would determine the values of the parameters that would achieve those targets. The outputs would be the time integrated results with those parameters as well as the values of the parameters that were solved for. The goal is to be able to determine what parameters to choose to achieve the specific targets. <br>
4d. Give all inputs expect for one parameters. Outputs would be time integrated results over all values of that parameter. The goal is to be able to see how outputs change as that parameter changes.


Two main use cases:
1. The Tuner: I know my car and here is my car, I want to know how my car performs and how to make it better
2. The Designer: I want to design a new car, I have vehicle level goals that I want to achieve and I want to find the parameters that I need to achieve those goals. 
Graphs help inform decisions

Q: How often are users going to move between flows? <br>
A: Users will likely move between flows multiple times, especially when skilled. Needs to be quick and easy to move between flows. Important to minimize having to re-enter information when moving between flows. When changing parts of previous flows

Goals should be stored and the tool should never auto-update someone's previous parameters without their consent.


#### Workflow 1: Vehicle Details

Q: What are all of the inputs for this workflow? <br>
A:
- Vehicle Mass
- Coefficient of Air Resistance
- Frontal Area
- List of Torque values at different RPMs (Engine Torque Curve)
- Inertia of the entire Engine
- Effective Inertia of Wheels to Secondary Shaft
- Effective Inertia of all other rotating components to Secondary Shaft
- Tire Radius
- Name of the Vehicle
- Notes

Q: What order should the inputs be in?
A: Don't have a specific order and might not fit all on one page as engine torque curve is large and needs complex input

#### Workflow 2a: Input Pulley Geometry Values

Q: What are all of the inputs for this workflow? <br>
A:
- Primary minimum radius of the outside surface of the belt
- Secondary maximum radius of the outside surface of the belt
- Belt selection (from a list of available belts) (no custom belts)

#### Workflow 2b: Input Pulley Geometry Goals

Q: What are all of the inputs for this workflow? <br>
A:
- Maximum torque
- Top speed 
- Average speed
- Belt Selection (from a list of available belts) (no custom belts)

#### Workflow 2: Generate Pulley Geometry and Metrics

Q: What is the datatype of the pulley geometry? <br>
A: Pulley geometry is stored as the following values
- Primary minimum radius of the outside surface of the belt
- Secondary maximum radius of the outside surface of the belt
- Belt selection (from a list of available belts) (no custom belts)

Q: What are the metrics and graphs that are outputted from this workflow? <br>
A:

Important to understand CVT setup
- Center to center distance
- (Primary radius at every shift value, Secondary radius at every shift value, all shift values) 3d model or y axis is radius, x axis is shift with two lines
- CVT Ratio vs Shift value (can be included in previous graph with a second y axis on the right)

Important to understand the possible range of CVT setups
- Static CVT ratio sensitivity surface with respect to primary outer radius, secondary outer radius and dR per mm shift. 3d surface graph with line for resolved path
- Sensitivity projection coloured by primary radius with secondary outer radius on x axis and dR per mm shift on y axis and primary outer radius as colour. 2d graph with a line for resolved path
- Sensitivity projection coloured by secondary radius with primary outer radius on x axis and dR per mm shift on y axis and secondary outer radius as colour. 2d graph with a line for resolved path
- Radius plane ratio and belt-length families with primary outer radius on x axis and secondary outer radius on y axis with curves for different CVT Ratios and different belt lengths. 2d graph with a line for resolved path
- Wrap angles along resolved shift path with global shift position on x axis and wrap angles on y axis with two lines for primary and secondary wrap angles. 
- CVT Ratio along resolved shift path with global shift position on x axis and CVT Ratio on y axis. 1 line for CVT Ratio

#### Workflow 3: Select CVT Actuating Parameters

Q: What are all of the inputs for this workflow? <br>
A:
Select one force generating mechanism from a dropdown list <br>
Repeat for both primary and secondary pulleys

Q: What are the dropdown options? <br>
A:

Subject to expand, don't have all the answers yet
- Centrifugal Ramp + Axial Spring
- Helical Ramp + Torsional Spring
- Electronic Actuator (needs additional inputs for the actuator)

Q: What are the additional inputs for the Centrifugal Ramp + Axial Spring? <br>
A:

Axial Spring:
- Spring Constant
- Initial Compression


Centrifugal Ramp:
- Flyweight Mass
- Initial Flyweight Radius
- 2D Ramp Input

Q: What are the additional inputs for the Helical Ramp + Torsional Spring? <br>
A:

Torsional Spring:
- Torsional Spring Constant
- Compressional Spring Constant
- Initial Rotation
- Initial Compression

Helical Ramp:
- Helical Ramp Input
Other:
- Movable Sheave Inertia

Q: What are the additional inputs for the Electronic Actuator? <br>
A:

A function that takes in the following 5 numbers as inputs:
1. Primary Rotation Speed
2. Belt Transport Speed
3. Secondary Rotation Speed
4. Shift Coordinate Speed
5. Shift Coordinate


Which outputs the multipliers for the following 8 numbers and the 9th number is the bias offset as output:
1. Primary Angular Acceleration
2. Secondary Angular Acceleration
3. Belt Acceleration
4. Shift Acceleration
5. Primary Torque
6. Secondary Torque
7. Primary Normal Resultant
8. Secondary Normal Resultant
9. Bias Offset

Q: What are the outputs for this workflow? <br>
A: Save the parameters, maybe have you run actuator flow in the future to see graphs




