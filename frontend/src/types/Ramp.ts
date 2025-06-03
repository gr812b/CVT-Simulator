import { ArcSegment, type Segment } from "@types";

export class Ramp extends Array<Segment> {
    public width: number = 0
    public minHeight: number = 0
    public maxHeight: number = 0
    public isDecreasing: boolean = true

    constructor(...segments: Segment[]) {
        super(...segments)
        Object.setPrototypeOf(this, Ramp.prototype)
        this.calculateDimensions()
    }

    public get height(): number {
        return this.maxHeight - this.minHeight
    }

    private calculateDimensions(): void {
        if (this.length === 0) {
            // No segments → both width and height are zero
            this.width = 0
            this.minHeight = 0
            this.maxHeight = 0
            return
        }

        let totalWidth = 0
        let heightOffset = 0 // Height each segment starts at relative to the start
        let globalMin = Infinity
        let globalMax = -Infinity

        this.forEach((segment) => {
            totalWidth += segment.length

            // Determine which points could be min or max
            const candidates = [0, segment.length]

            // Assuming sign(thetaStart) === sign(thetaEnd) and 0 ≤ |thetaStart| < |thetaEnd| ≤ π
            if (segment instanceof ArcSegment) {
                if (segment.thetaStart < Math.PI/2 && Math.PI/2 < segment.thetaEnd) {
                    candidates.push(segment.length * (Math.PI/2 - segment.thetaStart) / (segment.thetaEnd - segment.thetaStart))
                } else if (segment.thetaEnd < -Math.PI/2 && -Math.PI/2 < segment.thetaStart) {
                    candidates.push(segment.length * (-Math.PI/2 - segment.thetaStart) / (segment.thetaEnd - segment.thetaStart))
                }
            }

            // Evaluate the candidates
            candidates.forEach(distance => {
                const height = heightOffset + segment.getHeight(distance)
                if (height < globalMin) globalMin = height
                if (height > globalMax) globalMax = height
            })

            // Add segment to height offset
            heightOffset += segment.height
        })

        // Update state variables based on calculated values
        this.width = totalWidth
        this.minHeight = globalMin
        this.maxHeight = globalMax
        this.isDecreasing = heightOffset < 0

    }
}