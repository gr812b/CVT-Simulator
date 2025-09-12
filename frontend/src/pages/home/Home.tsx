import styles from './Home.module.scss'
import bajaLogo from '@assets/baja_logo.png'

export const Home = () => {
  return (
    <div className={styles.Home}>
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div>
    </div>
  )
}
