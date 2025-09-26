import type { InputHTMLAttributes } from 'react';
import styles from './InputField.module.scss';
import cx from 'classnames';


interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string | null;
  className?: string;
  hasChanged?: boolean; // New prop to indicate if field has been changed
}

export const InputField = ({ label, error, className, hasChanged, ...props }: InputFieldProps) => {
  return (
    <div className={cx(styles.inputContainer, { [styles.hasError]: error, [styles.hasChanged]: hasChanged }, className)}>
      {label && (
        <label className={styles.label}>
          {label}
          {hasChanged && <span className={styles.changeIndicator} />}
        </label>
      )}
      <input {...props} className={styles.input} />
      <span className={styles.error}>{error}</span>
    </div>
  );
};