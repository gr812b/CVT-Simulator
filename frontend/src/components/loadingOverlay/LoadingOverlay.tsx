import styles from './LoadingOverlay.module.scss';

interface LoadingOverlayProps {
  message?: string;
  isVisible?: boolean;
}

export const LoadingOverlay = ({ 
  message = 'Loading...', 
  isVisible = true 
}: LoadingOverlayProps) => {
  if (!isVisible) return null;

  return (
    <div className={styles.overlay}>
      <div className={styles.spinner}>
        <div className={styles.spinnerRing}></div>
        <p className={styles.message}>{message}</p>
      </div>
    </div>
  );
};