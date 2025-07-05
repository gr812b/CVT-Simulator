// Base abstract class for a Segment
export abstract class Segment {
    public length: number;

    constructor(length: number) {
        this.length = length;
    }
}

export class LineSegment extends Segment {
    public angle: number; // angle in radians

    constructor(length: number, angle: number) {
        super(length);
        this.angle = angle;
    }
}

export class ArcSegment extends Segment {
    public radius: number; 
    public thetaStart: number; // start angle in radians
    public thetaEnd: number; // end angle in radians

    constructor(length: number, thetaStart: number, thetaEnd: number) {
        super(length);
        this.radius = length / Math.abs(Math.cos(thetaEnd) - Math.cos(thetaStart))
        this.thetaStart = thetaStart;
        this.thetaEnd = thetaEnd;
    }
}