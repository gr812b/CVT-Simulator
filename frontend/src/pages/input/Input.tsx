import { MainButton } from '@components/mainButton/MainButton';
import styles from './Input.module.scss';
import ArrowLeft from '@assets/icons/arrow_left.svg?react';
import ArrowUpCircle from '@assets/icons/arrow_up_circle.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import Play from '@assets/icons/play.svg?react';
import { useNavigate } from 'react-router-dom';
import { ParameterAccordion } from '@components/parameterAccordian/ParameterAccordion';
import { InputField } from '@components/inputField/InputField';
import { ParameterDescription } from '@components/parameterDescription/ParameterDescription';
import baja_logo from '@assets/baja_logo.png';
import { useState } from 'react';
import { z } from 'zod';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';

// Form schema
const schema = z.object({
    primary: z.object({
        springPretension: z.transform(Number).pipe(z.number()),
        springRate: z.transform(Number).pipe(z.number()),
    }),
    secondary: z.object({
        rotationalSpringPretension: z.transform(Number).pipe(z.number()),
        rotationalSpringRate: z.transform(Number).pipe(z.number()),
        linearSpringPretension: z.transform(Number).pipe(z.number()),
        linearSpringRate: z.transform(Number).pipe(z.number()),
    }),
    environment: z.object({
        vehicleWeight: z.transform(Number).pipe(z.number()),
        driverWeight: z.transform(Number).pipe(z.number()),
        traction: z.transform(Number).pipe(z.number()),
        angleOfIncline: z.transform(Number).pipe(z.number()),
        totalDistance: z.transform(Number).pipe(z.number()),
    }),
});

export const Input = () => {
    const navigate = useNavigate();

    const {
        register,
        handleSubmit,
        // formState: { errors },
    } = useForm<z.infer<typeof schema>>({
        resolver: zodResolver(schema),
        defaultValues: {
            primary: { springPretension: 0, springRate: 0 },
            secondary: { rotationalSpringPretension: 0, rotationalSpringRate: 0, linearSpringPretension: 0, linearSpringRate: 0 },
            environment: { vehicleWeight: 0, driverWeight: 0, traction: 0, angleOfIncline: 0, totalDistance: 0 },
        },
    });

    const onSubmit = (data: z.infer<typeof schema>) => {
        console.log("Form Data:", data);
        //TODO: Handle form submission (e.g., send data to backend or update state)
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
            <form className={styles.inputGrid} onSubmit={handleSubmit(onSubmit)}>
                <div className={styles.parameterInputContainer}>
                    <ParameterAccordion title='Primary Pulley' isExpanded={expanded.primary} onToggle={() => toggleAccordion('primary')}>
                        <InputField className={styles.baseInputField} label='Spring Pretension (m)' type='number' step='any' {...register("primary.springPretension")} />
                        <InputField className={styles.baseInputField} label='Spring Rate (N/m)' type='number' step='any' {...register("primary.springRate")} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Secondary Pulley' isExpanded={expanded.secondary} onToggle={() => toggleAccordion('secondary')}>
                        <InputField className={styles.baseInputField} label='Rotational Spring Pretension (deg)' type='number' step='any' {...register("secondary.rotationalSpringPretension")} />
                        <InputField className={styles.baseInputField} label='Rotational Spring Rate (Nm/deg)' type='number' step='any' {...register("secondary.rotationalSpringRate")} />
                        <InputField className={styles.baseInputField} label='Linear Spring Pretension (m)' type='number' step='any' {...register("secondary.linearSpringPretension")} />
                        <InputField className={styles.baseInputField} label='Linear Spring Rate (N/m)' type='number' step='any' {...register("secondary.linearSpringRate")} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Environment' isExpanded={expanded.environment} onToggle={() => toggleAccordion('environment')}>
                        <InputField className={styles.baseInputField} label='Vehicle Weight (kg)' type='number' step='any' {...register("environment.vehicleWeight")} />
                        <InputField className={styles.baseInputField} label='Driver Weight (kg)' type='number' step='any' {...register("environment.driverWeight")} />
                        <InputField className={styles.baseInputField} label='Traction (%)' type='number' step='any' {...register("environment.traction")} />
                        <InputField className={styles.baseInputField} label='Angle of Incline (deg)' type='number' step='any' {...register("environment.angleOfIncline")} />
                        <InputField className={styles.baseInputField} label='Total Distance (m)' type='number' step='any' {...register("environment.totalDistance")} />
                    </ParameterAccordion>
                </div>
                <div className={styles.parameterInformationContainer}>
                    <ParameterDescription name={'Parameter Name'} description={'This is a description of the parameter. It provides useful information to help the user understand what the parameter does and how it affects the simulation.'} imgSrc={baja_logo} />
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
            </form>
        </div>
    )
}