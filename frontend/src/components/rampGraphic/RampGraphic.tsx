// RampGraphic.tsx
import styles from './RampGraphic.module.scss'
import cx from 'classnames'
import { Ramp } from '@types'
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
      unit: string = 'in'
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

    // “Notch baseline” positions (fixed x or y)
    const notchX = padding.left
    const notchY = padding.bottom

    // Updates to 0 on first ramp
    let currentRamp = -1

    // Loop through each segment in ramp
    ramp.forEach((line) => {
      drawLine(
        line.start.x,
        line.start.y,
        line.end.x,
        line.end.y
      )


      // If new ramp starts, draw notches at the start of the ramp
      if (line.ramp > currentRamp) {

        // Draws horizontal notch
        drawNotch(
          notchX,
          line.start.y,
          true,
          line.start.x,
          line.start.y,
          line.start.y
        )

        // Draws vertical notch
        drawNotch(
          line.start.x,
          notchY,
          false,
          line.start.x,
          line.start.y,
          line.start.x
        )

        // Update current ramp
        currentRamp = line.ramp

      }

    })

    // 3) After all segments, draw the final notches (at the end of the ramp)
    const lastLine = ramp[ramp.length - 1]
    // final “height” notch at x = notchX, y = currentY
    drawNotch(
      notchX,
      lastLine.end.y,
      true,
      lastLine.end.x,
      lastLine.end.y,
      lastLine.end.y
    )

    // final “length” notch at x = currentX, y = notchY
    drawNotch(
      lastLine.end.x,
      notchY,
      false,
      lastLine.end.x,
      lastLine.end.y,
      lastLine.end.x
    )

    // 4) Draw the “outer edges” and a dashed guideline up from the base
    //   - vertical left edge of ramp
    drawLine(
      padding.left,
      padding.bottom,
      padding.left,
      padding.bottom
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
      lastLine.end.x,
      padding.bottom
    )

    //   - vertical right edge of ramp
    drawLine(
      lastLine.end.x,
      padding.bottom,
      lastLine.end.x,
      lastLine.end.y
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
