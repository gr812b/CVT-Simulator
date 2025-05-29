import styles from './Ramp.module.scss'
import cx from 'classnames'
import { Segment, LineSegment, ArcSegment } from '@types'
import { useEffect, useRef } from 'react'

interface RampProps {
    segments: Segment[]
    className?: string
}

const Ramp = ({ segments, className }: RampProps) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)

    useEffect(() => {

        const renderSegment = (ctx: CanvasRenderingContext2D, segment: Segment, startX: number, startY: number) => {
            if (segment instanceof LineSegment) {
                return renderLineSegment(ctx, segment, startX, startY)
            } else if (segment instanceof ArcSegment) {
                return renderArcSegment(ctx, segment, startX, startY)
            } else {
                throw new Error('Unknown segment type')
            }
        }

        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        ctx.clearRect(0, 0, canvas.width, canvas.height)

        let currentX = 0
        let currentY = 0

        segments.forEach((segment) => {
            const result = renderSegment(ctx, segment, currentX, currentY)
            currentX = result.x
            currentY = result.y
        })

        ctx.strokeStyle = 'white'
        ctx.lineWidth = 10
    }, [segments])


    const renderLineSegment = (ctx: CanvasRenderingContext2D, segment: LineSegment, startX: number, startY: number) => {
        const endX = startX + segment.length * Math.cos(segment.angle)
        const endY = startY + segment.length * Math.sin(segment.angle)

        ctx.beginPath()
        ctx.moveTo(startX, startY)
        ctx.lineTo(endX, endY)
        ctx.stroke()

        return { x: endX, y: endY }
    }

    const renderArcSegment = (ctx: CanvasRenderingContext2D, segment: ArcSegment, startX: number, startY: number) => {
        const centerX = startX + segment.radius * Math.cos(-segment.thetaStart)
        const centerY = startY + segment.radius * Math.sin(-segment.thetaStart)

        const thetaStart = -segment.thetaStart + Math.PI
        const thetaEnd = -segment.thetaEnd + Math.PI

        ctx.beginPath()
        ctx.arc(centerX, centerY, segment.radius, thetaStart, thetaEnd, true)
        ctx.stroke()

        const endX = centerX + segment.radius * Math.cos(segment.thetaEnd)
        const endY = centerY + segment.radius * Math.sin(segment.thetaEnd)

        return { x: endX, y: endY }
    }

    // Calculate the bounds of the canvas based on the segment dimensions
    const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0)
    const totalHeight = segments.reduce((sum, segment) => sum + segment.getHeight(segment.length), 0)

    return (
        <canvas
            ref={canvasRef}
            className={cx(styles.ramp, className)}
            width={totalLength}
            height={totalHeight}
        />
    )   
}

export default Ramp