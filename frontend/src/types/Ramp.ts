export interface RampLine {
    ramp: number
    start: {x: number, y: number}
    end: {x: number, y: number}
}

export class Ramp extends Array<RampLine> {
    public width: number = 0
    public height: number = 0

    constructor(lines: RampLine[]) {
        super(...lines)
        Object.setPrototypeOf(this, Ramp.prototype)
        this.calculateDimensions()
    }

    private calculateDimensions(): void {
        if (this.length === 0) {
            // No segments → both width and height are zero
            this.width = 0
            this.height = 0
            return
        }

        // Width is the last line's end x-coordinate (lines[0].start.x is always 0)
        this.width = this[this.length - 1].end.x

        // Height is the maximum y-coordinate of all start and end points
        this.height = Math.max(...this.map(line => Math.max(line.start.y, line.end.y)));
    }
}