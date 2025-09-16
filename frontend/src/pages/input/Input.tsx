import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MainButton } from '@components/mainButton/MainButton';
import { ParameterAccordion } from '@components/parameterAccordion/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import { GROUP_TITLES, PARAMETERS, type Parameter, type ParameterGroup } from '@types';
import Home from '@assets/icons/home.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import Play from '@assets/icons/play.svg?react';
import styles from './Input.module.scss';

// Precomputed list of all parameter groups
const allGroups = Object.keys(GROUP_TITLES) as ParameterGroup[];

// Precompute expanded and collapsed states for all accordions
const expandedState: Record<ParameterGroup, boolean> = Object.fromEntries(allGroups.map(group => [group, true])) as Record<ParameterGroup, boolean>;
const collapsedState: Record<ParameterGroup, boolean> = Object.fromEntries(allGroups.map(group => [group, false])) as Record<ParameterGroup, boolean>;

export const Input = () => {
    const navigate = useNavigate();

    // State to manage which accordions are expanded
    const [expanded, setExpanded] = useState<Record<ParameterGroup, boolean>>(expandedState);

    // State to track which input field was most recently being used
    const [activeField, setActiveField] = useState<Parameter | null>(null);

    // Handler to toggle individual accordion
    const toggleAccordion = (group: keyof typeof expanded) => {
        setExpanded((prev) => ({ ...prev, [group]: !prev[group] }));
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
            <MainButton
                text={'Home'}
                icon={Home}
                className={styles.backButton}
                onClick={() => navigate('/')}
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
                            {Object.entries(PARAMETERS)
                                .filter(([, param]) => param.group === groupKey)
                                .map(([paramKey, param]) => (
                                    <InputField
                                        key={paramKey}
                                        className={styles.baseInputField}
                                        label={`${param.label} (${param.units})`}
                                        defaultValue={param.defaultValue}
                                        onFocus={() => setActiveField(paramKey as Parameter)}
                                    />
                                ))}
                        </ParameterAccordion>
                    ))}
                </div>
                <div className={styles.parameterInformationContainer}>
                    {getParameterInformation(activeField)}
                </div>
                <div className={styles.inputButtonsContainer}>
                    <MainButton
                        text='Expand All'
                        icon={ArrowDownCircle}
                        onClick={() => setExpanded(expandedState)}
                    />
                    <MainButton
                        text='Collapse All'
                        icon={ArrowUpCircle}
                        iconSide='right'
                        onClick={() => setExpanded(collapsedState)}
                    />
                </div>
                <div className={styles.nextButtonContainer}>
                    <MainButton
                        text='Run'
                        icon={Play}
                    />
                </div>
            </div>
        </div>
    )
}