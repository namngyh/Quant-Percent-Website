import { IntroCleanup } from "@/components/intro/intro-cleanup";

/**
 * Markup for the opening sequence, plus the script that decides whether it
 * runs at all.
 *
 * The animation lives entirely in CSS (`.qp-intro*` in globals.css). This file
 * only renders the elements and arms them, because the one thing the sequence
 * cannot afford is to start late: an earlier version mounted a framer-motion
 * overlay after hydration, so the page painted in full and the shutter then
 * closed over it.
 *
 * The mark is inline SVG rather than the `quant-percent-mark.svg` asset. That
 * file carries an opaque white background rect, which defeats any attempt to
 * recolour it with a filter — the previous version tinted it and got a blank
 * white square. Inline, each of the three shapes is a separate element that
 * can be animated on its own, which is what lets the mark assemble instead of
 * simply fading in.
 *
 * The script is inline and placed before the page content, so it runs before
 * the first paint. It is the only thing that adds `data-intro="play"`, and it
 * adds it only on the first page of a session with motion allowed. Everything
 * is `display: none` without that attribute, so a reader with JavaScript off,
 * or a crawler, never meets a shutter with nothing to open it.
 */

const ARM_INTRO = `(function(){try{
if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
if(sessionStorage.getItem('qp:intro')==='1')return;
sessionStorage.setItem('qp:intro','1');
document.documentElement.setAttribute('data-intro','play');
}catch(e){}})();`;

const WORDMARK = "Quant Percent";

/** Letters rise one after another; the delay is the stagger. */
const LETTER_START = 0.95;
const LETTER_STEP = 0.032;

export function SiteIntro() {
  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: ARM_INTRO }} />
      <div className="qp-intro" aria-hidden="true">
        <div className="qp-intro-panel qp-intro-panel-l" />
        <div className="qp-intro-panel qp-intro-panel-r" />

        <div className="qp-intro-stage">
          <div className="qp-intro-lockup">
            {/* The same three shapes as the brand mark, kept at the asset's
                own 100x100 coordinates so the proportions match exactly. */}
            <svg
              className="qp-intro-mark"
              viewBox="0 0 100 100"
              fill="none"
              focusable="false"
            >
              <rect
                className="qp-intro-sq-a"
                x="22"
                y="18"
                width="18"
                height="18"
              />
              <path className="qp-intro-slash" d="M70 14 78 22 30 76 22 68z" />
              <rect
                className="qp-intro-sq-b"
                x="60"
                y="58"
                width="18"
                height="18"
              />
            </svg>

            <span className="qp-intro-rule" />

            <span className="qp-intro-word">
              {WORDMARK.split("").map((char, i) => (
                <span
                  key={`${char}-${i}`}
                  style={{
                    animationDelay: `${(LETTER_START + i * LETTER_STEP).toFixed(3)}s`,
                  }}
                >
                  {char}
                </span>
              ))}
            </span>
          </div>
        </div>
      </div>
      <IntroCleanup />
    </>
  );
}
