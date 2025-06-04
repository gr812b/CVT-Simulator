// RampGraphic.tsx
import styles from './RampGraphic.module.scss'
import cx from 'classnames'
import { Ramp, LineSegment, ArcSegment } from '@types'
import { useEffect, useRef } from 'react'
import Canvas, { type CanvasHandle } from '@components/canvas/Canvas'

interface RampGraphicProps {
  ramp: Ramp
  className?: string
}

const RampGraphic = ({ ramp, className }: RampGraphicProps) => {
  const canvasRef = useRef<CanvasHandle>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext()
    if (!ctx) return

    // 1) figure out scale + computed SCSS variables once
    const scale = canvas.getScale()
    const style = getComputedStyle(ctx.canvas)

    // Dash settings from SCSS (converted back to logical coords)
    const dashWidth = parseFloat(style.getPropertyValue('--dash-width')) 
    const dashLength = parseFloat(style.getPropertyValue('--dash-length'))
    const dashGap = parseFloat(style.getPropertyValue('--dash-gap'))
    const dashColor = style.getPropertyValue('--dash-color')

    // Notch settings from SCSS (converted back to logical coords)
    const notchLength = parseFloat(style.getPropertyValue('--notch-length')) / scale
    const textGap = parseFloat(style.getPropertyValue('--notch-text-gap')) /scale

    // Padding (top/right/bottom/left) from SCSS (in logical coords)
    const padding = {
      top: parseFloat(style.getPropertyValue('--padding-top')) / scale,
      right: parseFloat(style.getPropertyValue('--padding-right')) / scale,
      bottom: parseFloat(style.getPropertyValue('--padding-bottom')) / scale,
      left: parseFloat(style.getPropertyValue('--padding-left')) / scale,
    }

    // Reset canvas
    canvas.clear()

    // Helper: draw a (possibly dashed) line
    const drawLine = (
      x1: number,
      y1: number,
      x2: number,
      y2: number,
      isDash = false
    ) => {
      if (isDash) {
        // Pass the dash pattern in (dashLength, dashGap)
        canvas.drawLine(x1, y1, x2, y2, dashColor, dashWidth, [dashLength, dashGap])
      } else {
        canvas.drawLine(x1, y1, x2, y2)
      }
    }

    // Helper: draw a notch (with text label and a short solid line)
    //    - horizontal: if true, notch extends left; otherwise extends upward
    //    - target: point to connect with a dashed line back to the ramp
    //    - value: numeric value to show (e.g. cumHeight or cumLength)
    //    - unit: "cm" by default
    const drawNotch = (
      x: number,
      y: number,
      horizontal: boolean,
      targetX: number,
      targetY: number,
      value: number,
      unit: string = 'cm'
    ) => {
      // Draw the short solid notch
      const text = `${Math.abs(value).toFixed(1)} ${unit}`

      if (horizontal) {
        // horizontal notch extends left from (x,y)
        canvas.drawLine(x, y, x - notchLength, y)
        canvas.drawText(text, x - notchLength - textGap, y, 'right', 'middle')
      } else {
        // vertical notch extends upward from (x,y)
        canvas.drawLine(x, y, x, y - notchLength)
        canvas.drawText(text, x, y - notchLength - textGap, 'center', 'top')
      }

      // dashed line from notch to ramp point
      drawLine(x, y, targetX, targetY, true)
    }

    // Helper: draw a circular arc (ArcSegment)
    const drawArc = (segment: ArcSegment, startX: number, startY: number) => {
      const { radius, thetaStart, thetaEnd } = segment
      // compute center of the arc
      const centerX = startX + radius * Math.cos(thetaStart)
      const centerY = startY + radius * Math.sin(-thetaStart)
      const startAngle = Math.PI - thetaStart
      const endAngle = Math.PI - thetaEnd
      canvas.drawArc(centerX, centerY, radius, startAngle, endAngle)
    }

    // 2) iterate over all segments, keeping track of cumulative length and height
    let cumLength = 0
    let cumHeight = -ramp.minHeight // start offset so that the “bottom” of the ramp aligns at y = padding.bottom

    // Initial drawing origin
    let currentX = cumLength + padding.left
    let currentY = cumHeight + padding.bottom

    // “Notch baseline” positions (fixed x or y)
    const notchX = padding.left
    const notchY = padding.bottom

    // Loop through each segment in ramp
    ramp.forEach((segment) => {
      // compute the end point of this segment
      const endX = currentX + segment.length
      const endY = currentY + segment.height

      // draw either a straight line or an arc
      if (segment instanceof LineSegment) {
        drawLine(currentX, currentY, endX, endY)
      } else if (segment instanceof ArcSegment) {
        drawArc(segment, currentX, currentY)
      }

      // draw the “horizontal” height-notch (always at x = notchX)
      drawNotch(
        notchX,
        currentY,
        true,               // horizontal notch
        currentX,
        currentY,
        cumHeight          // label = cumulative height so far
      )

      // draw the “vertical” length-notch (always at y = notchY)
      drawNotch(
        currentX,
        notchY,
        false,              // vertical notch
        currentX,
        currentY,
        cumLength          // label = cumulative length so far
      )

      // update for next segment
      currentX = endX
      currentY = endY
      cumLength += segment.length
      cumHeight += segment.height
    })

    // 3) After all segments, draw the final notches (at the end of the ramp)
    // final “height” notch at x = notchX, y = currentY
    drawNotch(
      notchX,
      currentY,
      true,
      currentX,
      currentY,
      cumHeight
    )

    // final “length” notch at x = currentX, y = notchY
    drawNotch(
      currentX,
      notchY,
      false,
      currentX,
      currentY,
      cumLength
    )

    // If the ramp does not start exactly at y = padding.bottom, add a zero-height notch
    if (currentY !== padding.bottom) {
      drawNotch(
        notchX,
        padding.bottom,
        true,
        currentX,
        padding.bottom,
        0
      )
    }

    // 4) Draw the “outer edges” and a dashed guideline up from the base
    //   - vertical left edge of ramp
    drawLine(
      padding.left,
      padding.bottom,
      padding.left,
      padding.bottom - ramp.minHeight
    )

    //   - dashed upward from base to show total ramp height
    drawLine(
      padding.left,
      padding.bottom,
      padding.left,
      padding.bottom + ramp.height,
      true
    )

    //   - horizontal bottom edge of ramp
    drawLine(
      padding.left,
      padding.bottom,
      currentX,
      padding.bottom
    )

    //   - vertical right edge of ramp
    drawLine(
      currentX,
      padding.bottom,
      currentX,
      currentY
    )
  }, [ramp])

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
