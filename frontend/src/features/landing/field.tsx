import { useEffect, useRef } from "react";

/**
 * The field behind the "unwritten intent" band.
 *
 * An aurora is the magnetic field made visible: the field was always there, the light only
 * lets you read it. That is the claim this product makes about a team's intent, so the band
 * draws field lines rather than a colour wash — and drawing them in ink rather than in
 * green is not a compromise. A multi-hue gradient here would be a fourth colour arguing
 * with the three that carry meaning, on the one page where a reader is being told those
 * three are the only colours that mean anything.
 *
 * Four ribbons, each a band of closely spaced hairlines following one curve, brightest at
 * its core and fading at both edges. A single line is a rule; a hundred of them with a
 * falloff is a sheet of light.
 *
 * Nothing here animates. A shimmer would read as decoration, and this has to sit under
 * three paragraphs somebody is meant to read.
 */

type Ribbon = {
  /** Where the ribbon's centre starts, as a fraction of the band's height. */
  y: number;
  /** Rise per pixel travelled right. Negative sweeps upward. */
  slope: number;
  amplitude: number;
  phase: number;
  /** Pixels between the ribbon's first line and its last. */
  spread: number;
  lines: number;
  /** Alpha at the core. Every line is white; only the opacity varies. */
  peak: number;
};

const RIBBONS: Ribbon[] = [
  { y: 0.06, slope: -0.15, amplitude: 78, phase: 0.4, spread: 158, lines: 32, peak: 0.26 },
  { y: 0.4, slope: -0.085, amplitude: 112, phase: 2.1, spread: 124, lines: 26, peak: 0.17 },
  { y: 0.82, slope: -0.165, amplitude: 68, phase: 3.6, spread: 186, lines: 36, peak: 0.225 },
  { y: 1.16, slope: -0.07, amplitude: 132, phase: 5.2, spread: 138, lines: 28, peak: 0.15 },
];

/** Two device pixels is enough for a hairline; past that it is memory for nothing. */
const MAX_DENSITY = 2;

/**
 * How far past the band the sheet reaches, as a fraction of the band's own height.
 *
 * The field is drawn on a canvas taller than the section it belongs to, so the ribbons run
 * out of the band rather than being cut off at its edge — up into the hero, and a little way
 * down past it. Both are fractions rather than lengths so the canvas can be positioned with
 * percentages: a length would have to be stated twice, once in CSS and once here, and the
 * two would drift.
 */
export type Bleed = { top: number; bottom: number };

const NO_BLEED: Bleed = { top: 0, bottom: 0 };

function draw(canvas: HTMLCanvasElement, bleed: Bleed) {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (!width || !height) return;

  // Every ribbon is placed against the band, never against the canvas. The canvas is the
  // larger of the two and grows with the bleed, so measuring from it would move the whole
  // composition every time the bleed changed — which is how four ribbons across the band
  // became one ribbon somewhere below it.
  const span = height / (1 + bleed.top + bleed.bottom);
  const origin = span * bleed.top;

  // jsdom has no 2D context. The band still renders; it simply has no field in it, which
  // is the same thing a reader with canvas disabled gets.
  const context = canvas.getContext("2d");
  if (!context) return;

  const density = Math.min(globalThis.devicePixelRatio || 1, MAX_DENSITY);
  canvas.width = Math.round(width * density);
  canvas.height = Math.round(height * density);
  context.setTransform(density, 0, 0, density, 0, 0);
  context.clearRect(0, 0, width, height);
  context.lineWidth = 1;

  for (const ribbon of RIBBONS) {
    for (let index = 0; index < ribbon.lines; index += 1) {
      const across = index / (ribbon.lines - 1);
      const core = 1 - Math.abs(across - 0.5) * 2;
      const alpha = ribbon.peak * Math.pow(Math.max(core, 0), 1.5);
      if (alpha < 0.004) continue;

      const offset = (across - 0.5) * ribbon.spread;
      // Each line's amplitude drifts a little, so the ribbon's edges are not perfectly
      // parallel and the whole thing reads as drawn rather than as ruled.
      const amplitude = ribbon.amplitude * (1 + 0.16 * Math.sin(across * 6.1 + ribbon.phase));

      context.strokeStyle = `rgba(255,255,255,${alpha.toFixed(4)})`;
      context.beginPath();
      for (let x = 0; x <= width; x += 5) {
        const u = x / width;
        const y =
          origin +
          span * ribbon.y +
          offset +
          ribbon.slope * x +
          amplitude * Math.sin(u * 1.7 + ribbon.phase + across * 0.55) +
          amplitude * 0.4 * Math.sin(u * 3.5 - ribbon.phase) +
          amplitude * 0.14 * Math.sin(u * 7.1 + ribbon.phase * 1.7);
        if (x === 0) context.moveTo(x, y);
        else context.lineTo(x, y);
      }
      context.stroke();
    }
  }

  // Erase back toward the left, where the reading column sits. The field is strongest in
  // the empty half of the band and never competes with a sentence.
  const mask = context.createLinearGradient(0, 0, width, 0);
  mask.addColorStop(0, "rgba(0,0,0,1)");
  mask.addColorStop(0.4, "rgba(0,0,0,0.95)");
  mask.addColorStop(0.58, "rgba(0,0,0,0.42)");
  mask.addColorStop(0.78, "rgba(0,0,0,0.04)");
  mask.addColorStop(1, "rgba(0,0,0,0)");
  context.globalCompositeOperation = "destination-out";
  context.fillStyle = mask;
  context.fillRect(0, 0, width, height);
  context.globalCompositeOperation = "source-over";
}

export function Field({ bleed = NO_BLEED, className }: { bleed?: Bleed; className?: string }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  const { top, bottom } = bleed;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const measure = { top, bottom };
    draw(canvas, measure);

    // The band's height changes when its copy reflows, not only when the window does, so
    // this watches the element rather than the viewport.
    if (typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => draw(canvas, measure));
    });
    observer.observe(canvas);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [top, bottom]);

  // The canvas is placed and masked from the same two numbers the ribbons are drawn from.
  // It is full strength across the band and fades to nothing across each bleed, so the sheet
  // has no edge anywhere a reader can see one — which is the whole reason it is oversized.
  const whole = 1 + top + bottom;
  // Width and height are stated rather than left to `inset-0`: a canvas is a replaced
  // element, so `width: auto` is its intrinsic 300×150 and the `left`/`right` pair it was
  // given is simply over-constrained and dropped. That is a canvas painting a full field
  // into the top-left corner of the page, which is exactly what it did.
  const style = {
    top: `${-top * 100}%`,
    width: "100%",
    height: `${whole * 100}%`,
    maskImage: `linear-gradient(to bottom, transparent 0, black ${((top / whole) * 100).toFixed(3)}%, black ${(((top + 1) / whole) * 100).toFixed(3)}%, transparent 100%)`,
  };

  return <canvas ref={ref} aria-hidden="true" style={style} className={className} />;
}
