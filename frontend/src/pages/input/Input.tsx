import { MainButton } from '@components/mainButton/MainButton';
import styles from './Input.module.scss';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import { useNavigate } from 'react-router-dom';
import { ParameterAccordion } from '@components/parameterAccordian/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import baja_logo from '@assets/baja_logo.png';
import { useState } from 'react';

export const Input = () => {
    const navigate = useNavigate();

    // Temporary handler for input field changes
    const handleInputChange = (value: string) => {
        console.log('Input changed to:', value);
    };

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
                        <InputField label='Spring Pretension (m)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Spring Rate (N/m)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                    </ParameterAccordion>
                    <ParameterAccordion title='Secondary Pulley' isExpanded={expanded.secondary} onToggle={() => toggleAccordion('secondary')}>
                        <InputField label='Rotational Spring Pretension (deg)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Rotational Spring Rate (Nm/deg)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Linear Spring Pretension (m)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Linear Spring Rate (N/m)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                    </ParameterAccordion>
                    <ParameterAccordion title='Environment' isExpanded={expanded.environment} onToggle={() => toggleAccordion('environment')}>
                        <InputField label='Vehicle Weight (kg)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Driver Weight (kg)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Traction (%)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Angle of Incline (deg)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                        <InputField label='Total Distance (m)' value='0' onChange={handleInputChange} className={styles.baseInputField}/>
                    </ParameterAccordion>
                </div>
                <div className={styles.parameterInformationContainer}>
                    <ParameterDescription name={'Parameter Name'} description={'This is a description of the parameter. It provides useful information to help the user understand what the parameter does and how it affects the simulation.'} imgSrc={baja_logo} />
                </div>
                <div className={styles.inputButtonsContainer}>
                    <MainButton
                        text='Expand All'
                        icon={ArrowDownCircle}
                        className={styles.expandButton}
                        onClick={expandAll}
                    />
                    <MainButton
                        text='Collapse All'
                        icon={ArrowUpCircle}
                        iconSide='right'
                        className={styles.collapseButton}
                        onClick={collapseAll}
                    />
                </div>
                <div className={styles.nextButtonContainer}></div>
            </div>
        </div>
    )
}