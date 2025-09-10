import { MainButton } from '@components/mainButton/MainButton';
import styles from './Input.module.scss';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import { useNavigate } from 'react-router-dom';
import { ParameterAccordion } from '@components/parameterAccordian/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';

export const Input = () => {
    const navigate = useNavigate();

    // Temporary handler for input field changes
    const handleInputChange = (value: string) => {
        console.log('Input changed to:', value);
    };
    
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
                    <ParameterAccordion title='Primary Pulley'>
                        <InputField label='Spring Pretension (m)' value='0' onChange={handleInputChange}/>
                        <InputField label='Spring Rate (N/m)' value='0' onChange={handleInputChange}/>
                    </ParameterAccordion>
                    <ParameterAccordion title='Secondary Pulley'>
                        <InputField label='Rotational Spring Pretension (deg)' value='0' onChange={handleInputChange}/>
                        <InputField label='Rotational Spring Rate (Nm/deg)' value='0' onChange={handleInputChange}/>
                        <InputField label='Linear Spring Pretension (m)' value='0' onChange={handleInputChange}/>
                        <InputField label='Linear Spring Rate (N/m)' value='0' onChange={handleInputChange}/>
                    </ParameterAccordion>
                    <ParameterAccordion title='Environment'>
                        <InputField label='Vehicle Weight (kg)' value='0' onChange={handleInputChange}/>
                        <InputField label='Driver Weight (kg)' value='0' onChange={handleInputChange}/>
                        <InputField label='Traction (%)' value='0' onChange={handleInputChange}/>
                        <InputField label='Angle of Incline (deg)' value='0' onChange={handleInputChange}/>
                        <InputField label='Total Distance (m)' value='0' onChange={handleInputChange}/>
                    </ParameterAccordion>
                </div>
                <div className={styles.parameterInformationContainer}></div>
                <div className={styles.inputButtonsContainer}>
                    <MainButton
                        text='Expand All'
                        icon={ArrowDownCircle}
                        className={styles.expandButton}
                        onClick={() => {}}
                    />
                    <MainButton
                        text='Collapse All'
                        icon={ArrowUpCircle}
                        iconSide='right'
                        className={styles.collapseButton}
                        onClick={() => {}}
                    />
                </div>
                <div className={styles.nextButtonContainer}></div>
            </div>
        </div>
    )
}