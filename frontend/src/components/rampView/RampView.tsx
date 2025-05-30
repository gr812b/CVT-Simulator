import styles from './RampView.module.scss'
import cx from 'classnames'
import { Segment, LineSegment, ArcSegment } from '@types'
import { useCallback, useEffect, useMemo, useRef } from 'react'

interface RampViewProps {
    segments: Segment[]
    className?: string
}

const CANVAS = {
  WIDTH: 800,
  HEIGHT: 600,
  PADDING: { top: 50, right: 50, bottom: 150, left: 150 },
  STROKE: { color: 'white', width: 10, cap: 'round' as CanvasLineCap },
  NOTCH: { length: 15 },
}

const RampView = ({ segments, className }: RampViewProps) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)
    // Precompute totals and scale just once per segments array
    const { totalLength, totalHeight, scale } = useMemo(() => {
        const totalLength = segments.reduce((sum, s) => sum + s.length, 0)
        const totalHeight = segments.reduce((sum, s) => sum + s.getHeight(s.length), 0)
        const rampWidth = CANVAS.WIDTH - CANVAS.PADDING.left - CANVAS.PADDING.right
        const rampHeight = CANVAS.HEIGHT - CANVAS.PADDING.bottom
        const scale = Math.min(rampWidth / totalLength, rampHeight / totalHeight)
        return { totalLength, totalHeight, scale }
    }, [segments])

    const drawNotch = useCallback(
        (ctx: CanvasRenderingContext2D, x: number, y: number, horizontal = true, value: number, target?: { x: number; y: number }) => {
            const { length } = CANVAS.NOTCH

            ctx.beginPath()
            if (horizontal) {
                ctx.moveTo(x, y)
                ctx.lineTo(x - length, y)
            } else {
                ctx.moveTo(x, y)
                ctx.lineTo(x, y + length)
            }
            ctx.stroke()

            ctx.font = '24px Roboto, sans-serif'
            ctx.fillStyle = 'white'
            ctx.textAlign = horizontal ? 'right' : 'center'
            ctx.textBaseline = horizontal ? 'middle' : 'top'
            const textGap = 10
            const offsetX = horizontal ? -length - textGap : 0
            const offsetY = horizontal ? 0 : length + textGap
            const text = `${value.toFixed(1)} cm`
            ctx.fillText(text, x + offsetX, y + offsetY)

            if (target) {
                ctx.save();
                ctx.strokeStyle = 'rgba(255,255,255,0.2)';
                ctx.lineWidth = 5;
                ctx.setLineDash([10, 20]);
                ctx.beginPath();
                ctx.moveTo(x, y);
                ctx.lineTo(target.x, target.y);
                ctx.stroke();
                ctx.restore();
            }
        },
        []
    )

    const renderLine = useCallback(
        (ctx: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number) => {
            ctx.beginPath()
            ctx.moveTo(x1, y1)
            ctx.lineTo(x2, y2)
            ctx.stroke()
        },
        []
    )
    
    const renderArc = useCallback(
        (ctx: CanvasRenderingContext2D, segment: ArcSegment, startX: number, startY: number) => {
            const { radius, thetaStart, thetaEnd } = segment
            const rScaled = radius * scale
            const cx = startX + rScaled * Math.cos(-thetaStart)
            const cy = startY + rScaled * Math.sin(-thetaStart)
            const start = -thetaStart + Math.PI
            const end = -thetaEnd + Math.PI

            ctx.beginPath()
            ctx.arc(cx, cy, rScaled, start, end, true)
            ctx.stroke()
        },
        [scale]
    )

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.strokeStyle = 'white'
        ctx.lineWidth = 10
        ctx.lineCap = 'round'

        // For notches
        const startX = CANVAS.PADDING.left
        const endY = CANVAS.PADDING.top + totalHeight * scale
        let cumLength = 0
        let cumHeight = 0

        let x = CANVAS.PADDING.left
        let y = CANVAS.PADDING.top

        // Draw initial notches
        drawNotch(ctx, startX, y, true, cumLength)
        drawNotch(ctx, x, endY, false, cumHeight)

        segments.forEach((segment) => {
            const nextX = x + segment.length * scale
            const nextY = y + segment.height * scale
            cumLength += segment.length
            cumHeight += segment.height

            if (segment instanceof LineSegment) {
                renderLine(ctx, x, y, nextX, nextY)
            } else if (segment instanceof ArcSegment) {
                renderArc(ctx, segment, x, y)
            }

            x = nextX
            y = nextY

            drawNotch(ctx, startX, y, true, cumHeight, {x, y})
            drawNotch(ctx, x, endY, false, cumLength, {x, y})
        })

        // Outer edge of ramp
        renderLine(ctx, CANVAS.PADDING.left, CANVAS.PADDING.top, CANVAS.PADDING.left, y)
        renderLine(ctx, CANVAS.PADDING.left, y, x, y)
    }, [segments, totalHeight, totalLength, scale, renderArc, renderLine, drawNotch])

    return (
        <canvas
            ref={canvasRef}
            className={cx(styles.ramp, className)}
            width={CANVAS.WIDTH}
            height={CANVAS.HEIGHT}
        />
    )   
}

export default RampView