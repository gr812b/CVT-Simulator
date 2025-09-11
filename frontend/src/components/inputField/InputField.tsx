import type { InputHTMLAttributes, Ref } from 'react';
import styles from './InputField.module.scss';
import cx from 'classnames';


interface InputFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  className?: string;
  ref?: Ref<HTMLInputElement>;
}

export const InputField = ({ label, className, ref, ...props }: InputFieldProps) => {
  return (
    <div className={cx(styles.inputContainer, className)}>
      {label && (
        <label htmlFor={props.name} className={styles.label}>
          {label}
        </label>
      )}
      <input {...props} ref={ref} className={styles.input} />
    </div>
  );
};