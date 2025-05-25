import styles from './Home.module.scss'
import bajaLogo from '@assets/baja_logo.png'
import { IconButton } from '../../components/iconButton/IconButton'
import Plus from '@assets/icons/plus.svg?react'

function Home() {

  return (
    <div className={styles.Home}>
      <div className={styles.header}>
        <img className={styles.logo} src={bajaLogo} alt="Baja Logo" />
        <h1 className={styles.title}>CVT Simulator</h1>
      </div >
      <IconButton
        onClick={() => console.log('New CVT')}
        icon={Plus}
        text="New"
        className={styles.newCVTButton}
      />
    </div>
  )
}

export default Home
