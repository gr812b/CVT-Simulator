import styles from './Dashboard.module.scss'
import bajaLogo from '@assets/baja_logo.png'
import { Button } from '@components/button/Button';
import { useNavigate } from 'react-router-dom';
import Run from '@assets/icons/run.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import TrashCan from '@assets/icons/trash_can.svg?react';
import Plus from '@assets/icons/plus.svg?react';

export const Dashboard = () => {
  const navigate = useNavigate();

  const tempIsDisabled = true; // Placeholder for future functionality
  
  return (
    <div className={styles.dashboard}>
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div>
      <div className={styles.tableContainer}>
        <span>No Saved Simulations...</span>
      </div>
      <div className={styles.buttonsContainer}>
        <Button
          text={'Run'}
          icon={Run}
          className={styles.button}
          disabled={tempIsDisabled}
          onClick={() => console.log('Run button clicked')}
        />
        <Button
          text={'Edit'}
          icon={Edit}
          className={styles.button}
          disabled={tempIsDisabled}
          onClick={() => console.log('Edit button clicked')}
        />
        <Button
          text={'Delete'}
          icon={TrashCan}
          className={styles.button}
          disabled={tempIsDisabled}
          onClick={() => console.log('Delete button clicked')}
        />
        <Button
          text={'New'}
          icon={Plus}
          className={styles.button}
          onClick={() => navigate('/input')}
        />
      </div>
    </div>
  )
}
