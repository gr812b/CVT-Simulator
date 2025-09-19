import type { InputHTMLAttributes } from 'react';
import styles from './InputField.module.scss';
import cx from 'classnames';


interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | null;
  className?: string;
}

export const InputField = ({ label, error, className, ...props }: InputFieldProps) => {
  return (
    <div className={cx(styles.inputContainer, { [styles.hasError]: error }, className)}>
      {label && <label className={cx(styles.label, { [styles.hasError]: error })}>{label}</label>}
      <input {...props} className={cx(styles.input, { [styles.hasError]: error })} />
      <span className={styles.error}>{error ?? ''}</span>
    </div>
  );
};