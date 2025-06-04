import styles from './RampGraphic.module.scss'
import cx from 'classnames'
import { Ramp, LineSegment, ArcSegment } from '@types'
import { useCallback, useEffect, useRef } from 'react'
import Canvas, { type CanvasHandle } from '@components/canvas/Canvas'

interface RampGraphicProps {
    ramp: Ramp
    className?: string
}

const RampGraphic = ({ ramp, className }: RampGraphicProps) => {
    const canvasRef = useRef<CanvasHandle>(null)

    const drawLine = useCallback(
    (canvas: CanvasHandle, x1: number, y1: number, x2: number, y2: number) => {
        canvas.drawLine(x1, y1, x2, y2)
    },
    []
    )

    const drawDash = useCallback(
        (canvas: CanvasHandle, style: CSSStyleDeclaration, x1: number, y1: number, x2: number, y2: number) => {
            const dashWidth = parseFloat(style.getPropertyValue('--dash-width'))
            const dashLength = parseFloat(style.getPropertyValue('--dash-length'))
            const dashGap = parseFloat(style.getPropertyValue('--dash-gap'))
            const dashColor = style.getPropertyValue('--dash-color')
            canvas.drawLine(x1, y1, x2, y2, dashColor, dashWidth, [dashLength, dashGap])
        },
        []
    )

    const drawNotch = useCallback(
        (canvas: CanvasHandle, style: CSSStyleDeclaration, x: number, y: number, horizontal = true, target: { x: number; y: number }, value: number, unit: string = 'cm') => {
            // Get scale from canvas
            const scale = canvas.getScale()
            
            // Get values from SCSS
            const notchLength = parseFloat(style.getPropertyValue('--notch-length'))
            const textGap = parseFloat(style.getPropertyValue('--notch-text-gap'))
            
            // Ensures final notch length is unaffected by scale
            const scaledNotch = notchLength / scale
            const scaledGap = textGap / scale

            // Calculates text to be shown
            const text = `${Math.abs(value).toFixed(1)} ${unit}`

            // Draws notch and text based on direction
            if (horizontal) {
                canvas.drawLine(x, y, x - scaledNotch, y)
                canvas.drawText(text, x - scaledNotch - scaledGap, y, 'right', 'middle')
            } else {
                canvas.drawLine(x, y, x, y - scaledNotch)
                canvas.drawText(text, x, y - scaledNotch - scaledGap, 'center', 'top')
            }
            
            // Draws dashed line
            drawDash(canvas, style, x, y, target.x, target.y)
        },
        [drawDash]
    )
    
    const drawArc = useCallback(
        (canvas: CanvasHandle, segment: ArcSegment, x: number, y: number) => {
            const { radius, thetaStart, thetaEnd } = segment
            const cx = x + radius * Math.cos(thetaStart)
            const cy = y + radius * Math.sin(-thetaStart)
            const start = Math.PI - thetaStart
            const end = Math.PI - thetaEnd

            canvas.drawArc(cx, cy, radius, start, end)
        },
        []
    )

    useEffect(() => {
        const canvas = canvasRef.current
        if (!canvas) return

        const ctx = canvas.getContext()
        if (!ctx) return

        const scale = canvas.getScale()

        // Get padding from SCSS
        const style = getComputedStyle(ctx.canvas)
        const PADDING = {
            top: parseFloat(style.getPropertyValue('--padding-top')) / scale,
            right: parseFloat(style.getPropertyValue('--padding-right')) / scale,
            bottom: parseFloat(style.getPropertyValue('--padding-bottom')) / scale,
            left: parseFloat(style.getPropertyValue('--padding-left')) / scale,
        }

        // Reset canvas
        canvas.clear()

        // Track cumulative length of each segment
        let cumLength = 0
        let cumHeight = -ramp.minHeight // reverse to get offset
        const notchX = PADDING.left
        const notchY = PADDING.bottom
        let x = cumLength + PADDING.left 
        let y = cumHeight + PADDING.bottom

        ramp.forEach((segment) => {
            // Determine final point
            const endX = x + segment.length
            const endY = y + segment.height

            // Draw segment
            if (segment instanceof LineSegment) {
                drawLine(canvas, x, y, endX, endY)
            } else if (segment instanceof ArcSegment) {
                drawArc(canvas, segment, x, y)
            }

            // Draw notches
            drawNotch(canvas, style, notchX, y, true, {x, y}, cumHeight)
            drawNotch(canvas, style, x, notchY, false, {x, y}, cumLength)

            // Update tracked values to account for segment
            x = endX
            y = endY
            cumLength += segment.length
            cumHeight += segment.height
        })

        // Draw final notches
        drawNotch(canvas, style, notchX, y, true, {x, y}, cumHeight)
        drawNotch(canvas, style, x, notchY, false, {x, y}, cumLength)

        // Outer edge of ramp
        drawLine(canvas, PADDING.left, PADDING.bottom, PADDING.left, PADDING.bottom - ramp.minHeight)
        drawDash(canvas, style, PADDING.left, PADDING.bottom, PADDING.left, PADDING.bottom + ramp.height)
        drawLine(canvas, PADDING.left, PADDING.bottom, x, PADDING.bottom)
        drawLine(canvas, x, PADDING.bottom, x, y)
    }, [ramp, drawArc, drawLine, drawDash, drawNotch])

    return (
        <Canvas
            ref={canvasRef}
            className={cx(styles.ramp, className)}
            totalWidth={ramp.width}
            totalHeight={ramp.height}
        />
    )   
}

export default RampGraphic