import styles from './Dashboard.module.scss'
import bajaLogo from '@assets/baja_logo.png'
import { Button } from '@components/button/Button';
import { useNavigate } from 'react-router-dom';
import Play from '@assets/icons/play.svg?react';
import Edit from '@assets/icons/edit.svg?react';
import TrashCan from '@assets/icons/trash_can.svg?react';
import Plus from '@assets/icons/plus.svg?react';


export const Dashboard = () => {
  const navigate = useNavigate();
  
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
          icon={Play}
          className={styles.backButton}
        />
        <Button
          text={'Edit'}
          icon={Edit}
          className={styles.backButton}
        />
        <Button
          text={'Delete'}
          icon={TrashCan}
          className={styles.backButton}
        />
        <Button
          text={'New'}
          icon={Plus}
          className={styles.backButton}
          onClick={() => navigate('/input')}
        />
      </div>
    </div>
  )
}
