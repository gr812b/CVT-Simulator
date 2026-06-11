import { useNavigate } from 'react-router-dom';
import styles from './Home.module.scss';
import { Button } from '@components/button/Button';
import cvt_model from '@assets/images/cvt_model.png';
import Plus from '@assets/icons/plus.svg?react';
import ArrowDownCircle from '@assets/icons/arrow_down_circle.svg?react';
import PlayOutline from '@assets/icons/play_outline.svg?react';
import ChevronDown from '@assets/icons/chevron_down.svg?react';

const GITHUB_URL = 'https://github.com/gr812b/CVT-Simulator';
const PAPER_URL =
    'https://github.com/gr812b/CVT-Simulator/blob/develop/docs/CVT_Module_Formulation/CVT_Module_Formulation.pdf';
const CURRENT_YEAR = new Date().getFullYear();

export const Home = () => {
    const navigate = useNavigate();

    return (
        <div className={styles.home}>
            <section className={styles.hero}>
                <div className={styles.heroTop}>
                    <div className={styles.heroContent}>
                        <h1 className={styles.title}>
                            <b>CVT</b>
                            <b className={styles.titleAccent}>Launch</b>
                            <b>Simulator</b>
                        </h1>
                        <p className={styles.description}>
                            A dynamic drivetrain simulator for Baja SAE vehicles equipped with a CVT,
                            gear reduction box, and wheels. Models a CH440 Kohler engine, external
                            forces, torque transmission, slip&nbsp;vs.&nbsp;stick behaviour, and
                            shifting dynamics. Based on an{' '}
                            <a
                                href={PAPER_URL}
                                target="_blank"
                                rel="noopener noreferrer"
                                className={styles.inlineLink}
                            >
                                ongoing research paper
                            </a>{' '}
                            (WIP).
                        </p>
                    </div>

                    <div className={styles.heroVisual}>
                        <div className={styles.imageCard}>
                            <img
                                src={cvt_model}
                                alt="Secondary CVT assembly — flyweights, spring, and ramps"
                                className={styles.cvtImage}
                            />
                        </div>
                    </div>
                </div>

                <div className={styles.actions}>
                    <Button
                        text="View Demo"
                        icon={PlayOutline}
                        size="large"
                        onClick={() => navigate('/demo')}
                    />
                    <Button
                        text="New Simulation"
                        icon={Plus}
                        size="large"
                        onClick={() => navigate('/input')}
                    />
                    <Button
                        text="Load Simulation"
                        icon={ArrowDownCircle}
                        size="large"
                        onClick={() => navigate('/dashboard')}
                    />
                </div>

                <div className={styles.scrollIndicator}>
                    <ChevronDown className={styles.scrollChevron} />
                </div>
            </section>

            <section className={styles.gettingStarted}>
                <h2 className={styles.sectionTitle}>Getting Started</h2>
                <div className={styles.steps}>
                    <div className={styles.step}>
                        <span className={styles.stepNumber}>01</span>
                        <h3 className={styles.stepTitle}>Configure Parameters</h3>
                        <p className={styles.stepText}>
                            Click <strong>New Simulation</strong> to define your CVT parameters
                            from scratch — spring rates, helix angle, flyweight mass, and throttle
                            ramp profile. Or click <strong>Load Simulation</strong> to start from
                            a previously saved or default parameter set.
                        </p>
                    </div>

                    <div className={styles.stepDivider} />

                    <div className={styles.step}>
                        <span className={styles.stepNumber}>02</span>
                        <h3 className={styles.stepTitle}>Run the Simulation</h3>
                        <p className={styles.stepText}>
                            Hit <strong>Run</strong> on the input page. The solver resolves torque
                            transmission, slip&nbsp;vs.&nbsp;stick conditions, and CVT ratio
                            shifting across the full launch event.
                        </p>
                    </div>

                    <div className={styles.stepDivider} />

                    <div className={styles.step}>
                        <span className={styles.stepNumber}>03</span>
                        <h3 className={styles.stepTitle}>Explore Results</h3>
                        <p className={styles.stepText}>
                            The playback view animates the 3D CVT model in real time alongside
                            time-series graphs for vehicle speed, gear ratio, torque, and more.
                            Export the full dataset to CSV for further analysis.
                        </p>
                    </div>
                </div>
            </section>

            <footer className={styles.footer}>
                <span className={styles.footerText}>
                    &copy; {CURRENT_YEAR} McMaster Baja SAE &mdash; CVT Simulator. All rights reserved.
                </span>
                <div className={styles.footerLinks}>
                    <a
                        href={PAPER_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.footerLink}
                    >
                        Paper
                    </a>
                    <span className={styles.footerDot}>·</span>
                    <a
                        href={GITHUB_URL}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={styles.footerLink}
                    >
                        GitHub
                    </a>
                </div>
            </footer>
        </div>
    );
};
