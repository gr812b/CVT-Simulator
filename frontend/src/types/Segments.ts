// Base abstract class for a Segment
export abstract class Segment {
    public length: number;

    constructor(length: number) {
        this.length = length;
    }

    // Ensure the distance is within the segment's bounds
    private checkDistanceInRange(distance: number): void {
        if (distance < 0 || distance > this.length) {
            throw new RangeError('Distance is out of segment bounds');
        }
    }

    // Abstract method to calculate height at a given distance
    protected abstract calculateHeight(distance: number): number;

    // Used to get the the height and check if the distance is valid
    public getHeight(distance: number): number {
        this.checkDistanceInRange(distance);
        return this.calculateHeight(distance);
    }
}

export class LineSegment extends Segment {
    public angle: number; // angle in radians

    constructor(length: number, angle: number) {
        super(length);
        this.angle = angle;
    }

    calculateHeight(distance: number): number {
        return distance * Math.sin(this.angle);
    }
}

export class ArcSegment extends Segment {
    public radius: number; 
    public thetaStart: number; // start angle in radians
    public thetaEnd: number; // end angle in radians

    constructor(length: number, thetaStart: number, thetaEnd: number) {
        super(length);
        this.radius = length / (thetaEnd - thetaStart);
        this.thetaStart = thetaStart;
        this.thetaEnd = thetaEnd;
    }

    calculateHeight(distance: number): number {
        // Calculate the angle based on the distance along the arc
        const deltaTheta = (this.thetaEnd - this.thetaStart) * (distance / this.length);
        const theta = this.thetaStart + deltaTheta + Math.PI;

        // Adjust the height calculation to account for the angle
        return -this.radius * (Math.sin(theta) - Math.sin(this.thetaStart + Math.PI));
    }
}