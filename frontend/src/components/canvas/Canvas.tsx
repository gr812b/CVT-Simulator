import {
  useRef,
  useEffect,
  useImperativeHandle,
  forwardRef,
  type Ref,
} from 'react'
import cx from 'classnames'
import styles from './Canvas.module.scss'

export interface CanvasHandle {
  /** Clear the entire canvas and reapply transforms */
  clear: () => void

  /** Draw a line in logical coordinates */
  drawLine: (
    x1: number, 
    y1: number, 
    x2: number, 
    y2: number,
    strokeStyle?: string | CanvasGradient | CanvasPattern,
    lineWidth?: number,
    dashStyle?: Iterable<number>
  ) => void

  /** Draw an arc in logical coordinates */
  drawArc: (
    cx: number,
    cy: number,
    radius: number,
    startAngle: number,
    endAngle: number,
    anticlockwise?: boolean
  ) => void

  /** Draw text at logical (x, y) with logical fontSize */
  drawText: (
    text: string,
    x: number,
    y: number,
    textAlign?: CanvasTextAlign,
    textBaseline?: CanvasTextBaseline
  ) => void

  /** Get the raw CanvasRenderingContext2D if needed */
  getContext: () => CanvasRenderingContext2D | null

  /** New: retrieve the most recently computed uniform scale */
  getScale: () => number
}

interface CanvasProps {
  /** The logical “total width” of your content (unscaled units) */
  totalWidth: number

  /** The logical “total height” of your content (unscaled units) */
  totalHeight: number

  /**
   * CSS class(es) to apply to the container <div>.
   */
  className?: string
}

/**
 * <Canvas> wraps a <canvas> in a <div> (styled via SCSS). It measures the
 * container’s on-screen pixel size, computes:
 *   scale = min(containerWidthPX / totalWidth, containerHeightPX / totalHeight),
 * and then exposes drawLine/drawArc/drawText in “logical units.” 
 */
const Canvas = forwardRef(({ totalWidth, totalHeight, className }: CanvasProps, ref: Ref<CanvasHandle>) => {

  // Refs for the wrapper <div> and the <canvas> element:
  const containerRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const ctxRef = useRef<CanvasRenderingContext2D | null>(null)

  // Store the last‐computed scale and container height:
  const scaleRef = useRef<number>(1)
  const containerHeightRef = useRef<number>(0)

  useEffect(() => {
    const container = containerRef.current
    const canvas = canvasRef.current
    if (!container || !canvas) return

    // 1) Measure container’s on-screen CSS px dimensions
    const rect = container.getBoundingClientRect()
    const containerWidth = rect.width
    const containerHeight = rect.height

    // 2) Read SCSS padding dimensions if given
    const cs = getComputedStyle(container);
    const paddingLeft = parseFloat(cs.getPropertyValue('--padding-left') || '0');
    const paddingRight = parseFloat(cs.getPropertyValue('--padding-right') || '0');
    const paddingTop = parseFloat(cs.getPropertyValue('--padding-top') || '0');
    const paddingBottom = parseFloat(cs.getPropertyValue('--padding-bottom') || '0');

    // 3) Compute uniform scale so content fits
    const scaleX = (containerWidth - paddingLeft - paddingRight) / totalWidth
    const scaleY = (containerHeight - paddingTop - paddingBottom) / totalHeight
    const scale = Math.min(scaleX, scaleY)
    scaleRef.current = scale
    containerHeightRef.current = containerHeight

    // 4) Resize canvas’s internal buffer to match container exactly
    canvas.width = Math.round(containerWidth)
    canvas.height = Math.round(containerHeight)

    // 5) Grab 2D context and reset transform so that (0,0)=bottom-left
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctxRef.current = ctx

    // 6) Set transform: flip Y and move origin to bottom-left
    //    setTransform(a=1, b=0, c=0, d=-1, e=0, f=containerHeight)
    ctx.setTransform(1, 0, 0, -1, 0, containerHeight)

    // 7) Clear any previous drawing
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }, [totalWidth, totalHeight, className])

  useImperativeHandle(ref, (): CanvasHandle => {
    const clear = () => {
      const ctx = ctxRef.current
      const canvas = canvasRef.current
      const container = containerRef.current
      if (!ctx || !canvas || !container) return

      ctx.save()
      // Reset to identity, clear entire buffer, then restore bottom-left
      ctx.setTransform(1, 0, 0, 1, 0, 0)
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      // Reapply bottom-left transform
      const ch = containerHeightRef.current
      ctx.setTransform(1, 0, 0, -1, 0, ch)
      ctx.restore()

      // Apply styles from SCSS
      const style = getComputedStyle(container)
      ctx.strokeStyle = style.color
      ctx.lineWidth = parseFloat(style.strokeWidth)
      ctx.lineCap = style.strokeLinecap as CanvasLineCap
      ctx.fillStyle = style.color  
      ctx.font = `${style.fontWeight} ${style.fontSize} ${style.fontFamily}`
    }

    const drawLine = (
      x1: number, 
      y1: number, 
      x2: number, 
      y2: number,
      strokeStyle?: string | CanvasGradient | CanvasPattern,
      lineWidth?: number,
      dashStyle?: Iterable<number>
    ) => {
      const ctx = ctxRef.current
      const scale = scaleRef.current
      if (!ctx) return

      ctx.save()

      // Apply optional styles
      if (strokeStyle) ctx.strokeStyle = strokeStyle
      if (lineWidth) ctx.lineWidth = lineWidth
      if (dashStyle) ctx.setLineDash(dashStyle)

      const x1Scaled = x1 * scale
      const y1Scaled = y1 * scale
      const x2Scaled = x2 * scale
      const y2Scaled = y2 * scale

      ctx.beginPath()
      ctx.moveTo(x1Scaled, y1Scaled)
      ctx.lineTo(x2Scaled, y2Scaled)
      ctx.stroke()
      ctx.restore()
    }

    const drawArc = (
      cx: number,
      cy: number,
      radius: number,
      startAngle: number,
      endAngle: number,
    ) => {
      const ctx = ctxRef.current
      const scale = scaleRef.current
      if (!ctx) return

      const cxScaled = cx * scale
      const cyScaled = cy * scale
      const radiusScaled = radius * scale

      ctx.beginPath()
      ctx.arc(cxScaled, cyScaled, radiusScaled, startAngle, endAngle, endAngle < startAngle)
      ctx.stroke()
    }

    const drawText = (
      text: string,
      x: number,
      y: number,
      textAlign?: CanvasTextAlign,
      textBaseline?: CanvasTextBaseline
    ) => {
      const ctx = ctxRef.current
      const ch = containerHeightRef.current
      const scale = scaleRef.current
      if (!ctx) return

      ctx.save()
      // Reset transform for upright text
      ctx.setTransform(1, 0, 0, 1, 0, 0)

      // Update style if given
      if (textAlign) ctx.textAlign = textAlign
      if (textBaseline) ctx.textBaseline = textBaseline

      // Convert y * scale (from bottom) → transformedY (from top)
      const translatedY = ch - y * scale
      ctx.fillText(text, x * scale, translatedY)

      ctx.restore()
    }

    const getContext = () => ctxRef.current

    const getScale = () => scaleRef.current

    return { clear, drawLine, drawArc, drawText, getContext, getScale }
  })

  return (
    <div
      ref={containerRef}
      className={cx(styles.container, className)}
    >
      <canvas
        ref={canvasRef}
        className={styles.canvas}
      />
    </div>
  )
})

export default Canvas
