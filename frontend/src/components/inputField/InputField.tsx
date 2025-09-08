import styles from './InputField.module.scss';
import cx from 'classnames';

interface InputFieldProps {
    value: string;
    onChange: (value: string) => void;
    label?: string;
    placeholder?: string;
    className?: string;
}

const InputField = ({ value, onChange, label, placeholder, className }: InputFieldProps) => {
    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        onChange(e.target.value);
    };

    return (
        <div className={cx(styles.inputContainer, className)}>
            {label && <label className={styles.label}>{label}</label>}
            <input
                type={'text'}
                value={value}
                onChange={handleChange}
                placeholder={placeholder}
                className={styles.input}
            />
        </div>
    );
}

export default InputField;