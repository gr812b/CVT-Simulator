import styles from './LoadingOverlay.module.scss';

interface LoadingOverlayProps {
  message?: string;
  isVisible?: boolean;
}

export const LoadingOverlay: React.FC<LoadingOverlayProps> = ({ 
  message = 'Loading...', 
  isVisible = true 
}) => {
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