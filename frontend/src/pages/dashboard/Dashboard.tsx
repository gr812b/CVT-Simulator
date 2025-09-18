import styles from './Dashboard.module.scss'
import bajaLogo from '@assets/baja_logo.png'

export const Dashboard = () => {
  return (
    <div className={styles.dashboard}>
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div>
    </div>
  )
}
