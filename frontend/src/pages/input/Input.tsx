import { MainButton } from '@components/mainButton/MainButton';
import styles from './Input.module.scss';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import Play from '@assets/icons/play.svg?react';
import { useNavigate } from 'react-router-dom';
import { ParameterAccordion } from '@components/parameterAccordion/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import { useState } from 'react';
import { PARAMETERS } from 'types/parameter';

export const Input = () => {
    const navigate = useNavigate();

    // State to manage which accordions are expanded
    const [expanded, setExpanded] = useState({
        primary: true,
        secondary: true,
        environment: true,
    });

    // Handler to toggle individual accordion
    const toggleAccordion = (key: keyof typeof expanded) => {
        setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
    };

    // Sets all accordions to expanded
    const expandAll = () => setExpanded({ primary: true, secondary: true, environment: true });

    // Sets all accordions to collapsed
    const collapseAll = () => setExpanded({ primary: false, secondary: false, environment: false });

    const [activeField, setActiveField] = useState<string | null>(null);

    // Get parameter description based on active field
    const getParameterDescription = (field: string | null) => {
        const parameter = PARAMETERS.find(param => param.key === field);

        // Return ParameterDescription component
        if (parameter) {
            return <ParameterDescription name={parameter.label} description={parameter.description} />;
        } else {
            return <ParameterDescription name="No Parameter Selected" description="Click on an input field to see its description." />;
        }
    }

    return (
        <div className={styles.input}>
            <MainButton
                text={'Back'}
                icon={ArrowLeft}
                className={styles.backButton}
                onClick={() => navigate('/')}
            />
            <div className={styles.inputGrid}>
                <div className={styles.parameterInputContainer}>
                    <ParameterAccordion title='Primary Pulley' isExpanded={expanded.primary} onToggle={() => toggleAccordion('primary')}>
                        <InputField className={styles.baseInputField} label='Spring Pretension (m)' onFocus={() => setActiveField('springPretension')} />
                        <InputField className={styles.baseInputField} label='Spring Rate (N/m)' onFocus={() => setActiveField('springRate')} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Secondary Pulley' isExpanded={expanded.secondary} onToggle={() => toggleAccordion('secondary')}>
                        <InputField className={styles.baseInputField} label='Rotational Spring Pretension (deg)' onFocus={() => setActiveField('rotationalSpringPretension')} />
                        <InputField className={styles.baseInputField} label='Rotational Spring Rate (Nm/deg)' onFocus={() => setActiveField('rotationalSpringRate')} />
                        <InputField className={styles.baseInputField} label='Linear Spring Pretension (m)' onFocus={() => setActiveField('linearSpringPretension')} />
                        <InputField className={styles.baseInputField} label='Linear Spring Rate (N/m)' onFocus={() => setActiveField('linearSpringRate')} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Environment' isExpanded={expanded.environment} onToggle={() => toggleAccordion('environment')}>
                        <InputField className={styles.baseInputField} label='Vehicle Weight (kg)' onFocus={() => setActiveField('vehicleWeight')} />
                        <InputField className={styles.baseInputField} label='Driver Weight (kg)' onFocus={() => setActiveField('driverWeight')} />
                        <InputField className={styles.baseInputField} label='Traction (%)' onFocus={() => setActiveField('traction')} />
                        <InputField className={styles.baseInputField} label='Angle of Incline (deg)' onFocus={() => setActiveField('angleOfIncline')} />
                        <InputField className={styles.baseInputField} label='Total Distance (m)' onFocus={() => setActiveField('totalDistance')} />
                    </ParameterAccordion>
                </div>
                <div className={styles.parameterInformationContainer}>
                    {getParameterDescription(activeField)}
                </div>
                <div className={styles.inputButtonsContainer}>
                    <MainButton
                        text='Expand All'
                        icon={ArrowDownCircle}
                        onClick={expandAll}
                        type='button'
                    />
                    <MainButton
                        text='Collapse All'
                        icon={ArrowUpCircle}
                        iconSide='right'
                        onClick={collapseAll}
                        type='button'
                    />
                </div>
                <div className={styles.nextButtonContainer}>
                    <MainButton
                        text='Run'
                        icon={Play}
                        type='submit'
                    />
                </div>
            </div>
        </div>
    )
}