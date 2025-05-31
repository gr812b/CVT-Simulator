import styles from './Ramp.module.scss'
import cx from 'classnames'
import { Segment, LineSegment, ArcSegment } from '@types'
import { useCallback, useEffect, useRef } from 'react'

interface RampProps {
    segments: Segment[]
    className?: string
}

const Ramp = ({ segments, className }: RampProps) => {
    const canvasRef = useRef<HTMLCanvasElement>(null)

    const drawNotch = useCallback(
        (ctx: CanvasRenderingContext2D, style: CSSStyleDeclaration, x: number, y: number, horizontal = true, target: { x: number; y: number }, value: number, unit: string = 'cm') => {
            // Get values from SCSS
            const notchLength = parseFloat(style.getPropertyValue('--notch-length'))
            const textGap = parseFloat(style.getPropertyValue('--notch-text-gap'))
            const dashWidth = parseFloat(style.getPropertyValue('--dash-width'))
            const dashLength = parseFloat(style.getPropertyValue('--dash-length'))
            const dashGap = parseFloat(style.getPropertyValue('--dash-gap'))
            const dashColor = style.getPropertyValue('--dash-color')

            ctx.beginPath()
            if (horizontal) {
                ctx.moveTo(x, y)
                ctx.lineTo(x - notchLength, y)
            } else {
                ctx.moveTo(x, y)
                ctx.lineTo(x, y + notchLength)
            }
            ctx.stroke()


            // Add label to notche
            ctx.textAlign = horizontal ? 'right' : 'center'
            ctx.textBaseline = horizontal ? 'middle' : 'top'
            ctx.fillStyle = style.color  
            ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
            const offsetX = horizontal ? -notchLength - textGap : 0
            const offsetY = horizontal ? 0 : notchLength + textGap
            const text = `${value.toFixed(1)} ${unit}`
            ctx.fillText(text, x + offsetX, y + offsetY)

            // Draw dashed line from notches to ramp
            ctx.save();
            ctx.strokeStyle = dashColor;
            ctx.lineWidth = dashWidth;
            ctx.setLineDash([dashLength, dashGap]);
            ctx.beginPath();
            ctx.moveTo(x, y);
            ctx.lineTo(target.x, target.y);
            ctx.stroke();
            ctx.restore();
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
        (ctx: CanvasRenderingContext2D, segment: ArcSegment, startX: number, startY: number, scale: number) => {
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
        []
    )

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext('2d')
        if (!ctx) return

        // Get display size
        const { width: displayWidth, height: displayHeight } = canvas.getBoundingClientRect()
        canvas.width = displayWidth
        canvas.height = displayHeight

        // Get padding from SCSS
        const style = getComputedStyle(canvas)
        const PADDING = {
            top: parseFloat(style.getPropertyValue('--padding-top')),
            right: parseFloat(style.getPropertyValue('--padding-right')),
            bottom: parseFloat(style.getPropertyValue('--padding-bottom')),
            left: parseFloat(style.getPropertyValue('--padding-left')),
        }

        // Area of canvas available for ramp
        const rampWidth = displayWidth - PADDING.left - PADDING.right
        const rampHeight = displayHeight - PADDING.bottom

        // Compute actual dimensions of ramp
        const totalLength = segments.reduce((sum, s) => sum + s.length, 0)
        const totalHeight = segments.reduce((sum, s) => sum + s.getHeight(s.length), 0)

        // Minimum scale needed to keep ramp in canvas area
        const scale = Math.min(rampWidth / totalLength, rampHeight / totalHeight)

        // Reset canvas and set stroke styling
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        ctx.strokeStyle = style.color
        ctx.lineWidth = parseFloat(style.strokeWidth)
        ctx.lineCap = style.strokeLinecap as CanvasLineCap

        // For notch positioning and text
        const startX = PADDING.left
        const endY = PADDING.top + totalHeight * scale
        let cumLength = 0
        let cumHeight = 0

        // Track start of each segment
        let x = PADDING.left
        let y = PADDING.top

        // Draw initial notches
        drawNotch(ctx, style, startX, y, true, {x, y}, cumLength)
        drawNotch(ctx, style, x, endY, false, {x, y}, cumHeight)

        segments.forEach((segment) => {
            const nextX = x + segment.length * scale
            const nextY = y + segment.height * scale
            cumLength += segment.length
            cumHeight += segment.height

            if (segment instanceof LineSegment) {
                renderLine(ctx, x, y, nextX, nextY)
            } else if (segment instanceof ArcSegment) {
                renderArc(ctx, segment, x, y, scale)
            }

            x = nextX
            y = nextY

            drawNotch(ctx, style, startX, y, true, {x, y}, cumHeight)
            drawNotch(ctx, style, x, endY, false, {x, y}, cumLength)
        })

        // Outer edge of ramp
        renderLine(ctx, PADDING.left, PADDING.top, PADDING.left, y)
        renderLine(ctx, PADDING.left, y, x, y)
    }, [segments, renderArc, renderLine, drawNotch])

    return (
        <canvas
            ref={canvasRef}
            className={cx(styles.ramp, className)}
        />
    )   
}

export default Ramp