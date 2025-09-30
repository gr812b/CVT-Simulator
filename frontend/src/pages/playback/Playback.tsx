import { Page } from '@components/graph2D/page';
import { runSimulation } from '@utils/api';

export const Playback = () => {

    runSimulation().then((data) => {
        console.log(data);
    });

    return (
        <div>
            <Page />
        </div>
    )
}