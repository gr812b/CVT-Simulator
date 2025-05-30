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
    const paddingX = 10
    const paddingY = 10

    useEffect(() => {

        const renderSegment = (ctx: CanvasRenderingContext2D, segment: Segment, startX: number, startY: number, endX: number, endY: number) => {
            if (segment instanceof LineSegment) {
                renderLineSegment(ctx, startX, startY, endX, endY)
            } else if (segment instanceof ArcSegment) {
                renderArcSegment(ctx, segment, startX, startY)
            } else {
                throw new Error('Unknown segment type')
            }
        }

        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.strokeStyle = 'white'
        ctx.lineWidth = 10
        ctx.lineCap = 'round'

        let startX = paddingX
        let startY = paddingY

        segments.forEach((segment) => {
            const endX = startX + segment.length
            const endY = startY + segment.getHeight(segment.length)

            renderSegment(ctx, segment, startX, startY, endX, endY)

            startX = endX
            startY = endY
        })

        // Draw the egdes of the ramp
        ctx.beginPath()
        ctx.moveTo(paddingX, paddingY)
        ctx.lineTo(paddingX, startY)
        ctx.lineTo(startX, startY)
        ctx.stroke()

    }, [segments])

    const renderLineSegment = (ctx: CanvasRenderingContext2D, startX: number, startY: number, endX: number, endY: number) => {
        ctx.beginPath()
        ctx.moveTo(startX, startY)
        ctx.lineTo(endX, endY)
        ctx.stroke()
    }

    const renderArcSegment = (ctx: CanvasRenderingContext2D, segment: ArcSegment, startX: number, startY: number) => {
        const centerX = startX + segment.radius * Math.cos(-segment.thetaStart)
        const centerY = startY + segment.radius * Math.sin(-segment.thetaStart)

        const thetaStart = -segment.thetaStart + Math.PI
        const thetaEnd = -segment.thetaEnd + Math.PI

        ctx.beginPath()
        ctx.arc(centerX, centerY, segment.radius, thetaStart, thetaEnd, true)
        ctx.stroke()
    }

    // Calculate the bounds of the canvas based on the segment dimensions
    const totalLength = segments.reduce((sum, segment) => sum + segment.length, 0)
    const totalHeight = segments.reduce((sum, segment) => sum + segment.getHeight(segment.length), 0)

    return (
        <canvas
            ref={canvasRef}
            className={cx(styles.ramp, className)}
            width={totalLength + paddingX * 2}
            height={totalHeight + paddingY * 2}
        />
    )   
}

export default Ramp