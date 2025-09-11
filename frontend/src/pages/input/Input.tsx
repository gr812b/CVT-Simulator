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
import { useState, type ReactNode } from 'react';
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

    const handleOnWheel = (e: React.WheelEvent) => (e.target as HTMLElement).blur();

    const [activeField, setActiveField] = useState<string | null>(null);

    const infoComponents: Record<string, ReactNode> = {
        springPretension: (
            <ParameterDescription
                name="Spring Pretension"
                description="The initial tension of the primary pulley spring."
            />
        ),
        springRate: (
            <ParameterDescription
                name="Spring Rate"
                description="The stiffness of the primary pulley spring."
            />
        ),
        rotationalSpringPretension: (
            <ParameterDescription
                name="Rotational Spring Pretension"
                description="The preload angle for the secondary pulley’s rotational spring."
            />
        ),
        rotationalSpringRate: (
            <ParameterDescription
                name="Rotational Spring Rate"
                description="The stiffness of the secondary pulley’s rotational spring."
            />
        ),
        linearSpringPretension: (
            <ParameterDescription
                name="Linear Spring Pretension"
                description="The initial compression of the secondary pulley’s linear spring."
            />
        ),
        linearSpringRate: (
            <ParameterDescription
                name="Linear Spring Rate"
                description="The stiffness of the secondary pulley’s linear spring."
            />
        ),
        vehicleWeight: (
            <ParameterDescription
                name="Vehicle Weight"
                description="Total mass of the vehicle in kilograms."
            />
        ),
        driverWeight: (
            <ParameterDescription
                name="Driver Weight"
                description="Mass of the driver in kilograms."
            />
        ),
        traction: (
            <ParameterDescription
                name="Traction"
                description="Represents the grip of the tires on the surface, expressed as a percentage."
            />
        ),
        angleOfIncline: (
            <ParameterDescription
                name="Angle of Incline"
                description="The slope of the terrain in degrees."
            />
        ),
        totalDistance: (
            <ParameterDescription
                name="Total Distance"
                description="The total distance of the test course in meters."
            />
        ),
    };

    // Default info when no field is active
    const defaultInfo = (
        <ParameterDescription
            name="Parameter Information"
            description="Focus an input field to view more details about the parameter."
        />
    );

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
                        <InputField className={styles.baseInputField} label='Spring Pretension (m)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('springPretension')} {...register("primary.springPretension")} />
                        <InputField className={styles.baseInputField} label='Spring Rate (N/m)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('springRate')} {...register("primary.springRate")} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Secondary Pulley' isExpanded={expanded.secondary} onToggle={() => toggleAccordion('secondary')}>
                        <InputField className={styles.baseInputField} label='Rotational Spring Pretension (deg)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('rotationalSpringPretension')} {...register("secondary.rotationalSpringPretension")} />
                        <InputField className={styles.baseInputField} label='Rotational Spring Rate (Nm/deg)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('rotationalSpringRate')} {...register("secondary.rotationalSpringRate")} />
                        <InputField className={styles.baseInputField} label='Linear Spring Pretension (m)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('linearSpringPretension')} {...register("secondary.linearSpringPretension")} />
                        <InputField className={styles.baseInputField} label='Linear Spring Rate (N/m)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('linearSpringRate')} {...register("secondary.linearSpringRate")} />
                    </ParameterAccordion>
                    <ParameterAccordion title='Environment' isExpanded={expanded.environment} onToggle={() => toggleAccordion('environment')}>
                        <InputField className={styles.baseInputField} label='Vehicle Weight (kg)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('vehicleWeight')} {...register("environment.vehicleWeight")} />
                        <InputField className={styles.baseInputField} label='Driver Weight (kg)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('driverWeight')} {...register("environment.driverWeight")} />
                        <InputField className={styles.baseInputField} label='Traction (%)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('traction')} {...register("environment.traction")} />
                        <InputField className={styles.baseInputField} label='Angle of Incline (deg)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('angleOfIncline')} {...register("environment.angleOfIncline")} />
                        <InputField className={styles.baseInputField} label='Total Distance (m)' type='number' step='any' onWheel={handleOnWheel} onFocus={() => setActiveField('totalDistance')} {...register("environment.totalDistance")} />
                    </ParameterAccordion>
                </div>
                <div className={styles.parameterInformationContainer}>
                    {activeField ? infoComponents[activeField] : defaultInfo}
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