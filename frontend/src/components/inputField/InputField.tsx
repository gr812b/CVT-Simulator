import type { InputHTMLAttributes } from 'react';
import styles from './InputField.module.scss';
import cx from 'classnames';


interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  className?: string;
}

export const InputField = ({ label, className, ...props }: InputFieldProps) => {
  return (
    <div className={cx(styles.inputContainer, className)}>
      {label && (
        <label className={styles.label}>
          {label}
        </label>
      )}
      <input {...props} className={styles.input} />
    </div>
  );
};