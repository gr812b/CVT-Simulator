import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@components/button/Button';
import { ParameterAccordion } from '@components/parameterAccordion/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import { LoadingOverlay } from '@components/loadingOverlay/LoadingOverlay';
import { GROUP_TITLES, PARAMETERS, type Parameter, type ParameterGroup } from '@types';
import { useParameter } from '@contexts/ParameterContext';
import { useLoading } from '@contexts/LoadingContext';
import { useSimulation } from '@contexts/SimulationContext';
import { useFormState } from '@hooks/useFormState';
import { useUnsavedChangesPrompt } from '@hooks/useUnsavedChangesPrompt';
import { runSimulation } from '@utils/api';
import { mapParametersToApiBody } from '@utils/parameterMapping';
import Home from '@assets/icons/home.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import Play from '@assets/icons/play.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import styles from './Input.module.scss';

// Precomputed list of all groups and parameters
const allGroups = Object.keys(GROUP_TITLES) as ParameterGroup[];
const allParameters = Object.keys(PARAMETERS) as Parameter[];

// Precompute expanded and collapsed states for all accordions
const expandedState: Record<ParameterGroup, boolean> = Object.fromEntries(allGroups.map(group => [group, true])) as Record<ParameterGroup, boolean>;
const collapsedState: Record<ParameterGroup, boolean> = Object.fromEntries(allGroups.map(group => [group, false])) as Record<ParameterGroup, boolean>;

export const Input = () => {
    const navigate = useNavigate();
    const { setMultipleParameters, parameters } = useParameter();
    const { setLoading, isLoading, loadingMessage } = useLoading();
    const { setSimulationResult } = useSimulation();
    const formState = useFormState(parameters);
    const { navigateWithConfirmation } = useUnsavedChangesPrompt(formState.hasChanges);

    // State to manage which accordions are expanded
    const [expanded, setExpanded] = useState<Record<ParameterGroup, boolean>>(expandedState);

    // State to track which input field was most recently being used
    const [activeField, setActiveField] = useState<Parameter | null>(null);

    // Handler to toggle individual accordion
    const toggleAccordion = (group: keyof typeof expanded) => {
        setExpanded((prev) => ({ ...prev, [group]: !prev[group] }));
    };

    // Handle form submission and API call
    const handleSubmit = async () => {
        if (!formState.validateAll()) {
            return;
        }

        try {
            // Save the form data first
            const parsedValues = formState.getParsedValues();
            setMultipleParameters(parsedValues);
            formState.markAsSaved();

            // Show loading overlay
            setLoading(true, 'Running simulation...');

            // Prepare API request body
            const apiBody = mapParametersToApiBody(parsedValues);

            // Make API call
            const result = await runSimulation(apiBody);

            // Store the result for the Playback page
            setSimulationResult(result);

            // Navigate to playback page
            navigate('/playback');
        } catch (error) {
            console.error('Simulation failed:', error);
            // You might want to show an error toast or modal here
            alert('Simulation failed. Please check your parameters and try again.');
        } finally {
            setLoading(false);
        }
    };

    // Handle manual save
    const handleSave = () => {
        if (formState.validateAll()) {
            const parsedValues = formState.getParsedValues();
            setMultipleParameters(parsedValues);
            formState.markAsSaved();
        }
    };

    // Get parameter description based on active field
    const getParameterInformation = (key: Parameter | null) => {
        const parameter = key ? PARAMETERS[key] : null;
        return (
            <ParameterDescription
                name={parameter ? parameter.label : "No Parameter Selected"}
                description={parameter ? parameter.description : "Click on an input field to see its description."}
            />
        );
    }

    return (
        <div className={styles.input}>
            <LoadingOverlay isVisible={isLoading} message={loadingMessage} />
            <Button
                text={'Home'}
                icon={Home}
                className={styles.backButton}
                onClick={() => navigateWithConfirmation('/')}
            />
            <div className={styles.inputGrid}>
                <div className={styles.parameterInputContainer}>
                    {allGroups.map((groupKey) => (
                        <ParameterAccordion
                            key={groupKey}
                            title={GROUP_TITLES[groupKey]}
                            isExpanded={expanded[groupKey]}
                            onToggle={() => toggleAccordion(groupKey)}
                        >
                            {allParameters
                                .filter(paramKey => PARAMETERS[paramKey].group === groupKey)
                                .map(paramKey => {
                                    const { label, units } = PARAMETERS[paramKey];
                                    const hasError = formState.touched[paramKey] && formState.errors[paramKey];
                                    const hasChanged = formState.isFieldChanged(paramKey);
                                    
                                    return (
                                        <InputField
                                            key={paramKey}
                                            className={styles.baseInputField}
                                            label={`${label} (${units})`}
                                            value={formState.values[paramKey]}
                                            error={hasError ? formState.errors[paramKey] : null}
                                            hasChanged={hasChanged}
                                            onChange={(e) => formState.updateField(paramKey, e.target.value)}
                                            onFocus={() => {
                                                setActiveField(paramKey);
                                                formState.touchField(paramKey);
                                            }}
                                        />
                                    );
                                })}
                        </ParameterAccordion>
                    ))}
                </div>
                <div className={styles.parameterInformationContainer}>
                    {getParameterInformation(activeField)}
                </div>
                <div className={styles.inputButtonsContainer}>
                    <Button
                        text='Expand All'
                        icon={ArrowDownCircle}
                        onClick={() => setExpanded(expandedState)}
                    />
                    <Button
                        text='Collapse All'
                        icon={ArrowUpCircle}
                        iconSide='right'
                        onClick={() => setExpanded(collapsedState)}
                    />
                </div>
                <div className={styles.nextButtonContainer}>
                    <Button
                        text='Save'
                        icon={Edit}
                        onClick={handleSave}
                        disabled={!formState.isValid()}
                    />
                    <Button
                        text='Run'
                        icon={Play}
                        onClick={handleSubmit}
                        disabled={!formState.isValid()}
                    />
                </div>
            </div>
        </div>
    );
};