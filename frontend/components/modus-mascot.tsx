/**
 * Model Modus mascot.
 *
 * Redrawn as vector rather than embedded as a bitmap: it renders crisply at
 * every size the site uses it, from a 32px inline badge to a hero panel, and
 * costs no extra request. If the original artwork is supplied as a file this
 * component can be swapped for it without touching the call sites.
 *
 * `decorative` (the default) hides it from assistive technology, which is
 * correct wherever the name "Model Modus" already appears beside it. Pass a
 * `label` on the rare occasion the mascot stands alone.
 */

const CREAM = "#F2EFE8";
const NAVY = "#121826";
const MINT = "#2FE0A0";
const GREY = "#98A2AE";

export function ModusMascot({
  className,
  label,
  showBackdrop = true,
}: {
  className?: string;
  /** Announce the image with this name; omit to treat it as decorative. */
  label?: string;
  /** The rounded cream plate behind the figure. */
  showBackdrop?: boolean;
}) {
  return (
    <svg
      viewBox="0 0 512 512"
      className={className}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      {showBackdrop && (
        <rect x="0" y="0" width="512" height="512" rx="96" fill={CREAM} />
      )}

      {/* Antennae. The centre one is an open capsule; the outer pair are
          filled, each with a bead above and below. */}
      <g fill={NAVY}>
        <rect x="177" y="20" width="16" height="30" rx="8" />
        <rect x="160" y="46" width="50" height="52" rx="18" />
        <circle cx="185" cy="105" r="9" />

        <rect x="248" y="14" width="16" height="26" rx="8" />
        <rect
          x="231"
          y="34"
          width="50"
          height="70"
          rx="20"
          fill="none"
          stroke={NAVY}
          strokeWidth="14"
        />
        <circle cx="256" cy="110" r="8" />

        <rect x="326" y="26" width="14" height="26" rx="7" />
        <rect x="310" y="48" width="46" height="46" rx="17" />
        <circle cx="333" cy="101" r="8" />
      </g>

      {/* Arms, drawn before the body so the joins sit underneath it. */}
      <g fill={NAVY}>
        <rect x="96" y="248" width="96" height="50" rx="25" />
        <rect x="320" y="248" width="96" height="50" rx="25" />
      </g>

      {/* Legs. */}
      <g fill={NAVY}>
        <rect x="182" y="352" width="40" height="68" rx="20" />
        <rect x="290" y="352" width="40" height="68" rx="20" />
      </g>

      {/* Body. */}
      <rect x="126" y="118" width="260" height="254" rx="76" fill={NAVY} />

      {/* Percent sign: two rings and a diagonal. The stroke widths are set so
          the ring wall and the bar read as the same weight. */}
      <circle
        cx="213"
        cy="208"
        r="39"
        fill="none"
        stroke={CREAM}
        strokeWidth="26"
      />
      <circle
        cx="301"
        cy="272"
        r="39"
        fill="none"
        stroke={CREAM}
        strokeWidth="26"
      />
      <line
        x1="203"
        y1="296"
        x2="314"
        y2="185"
        stroke={MINT}
        strokeWidth="26"
        strokeLinecap="round"
      />

      {/* Sigma and pi drawn as strokes rather than set in a typeface.
          A mark should not depend on a font being available, and the site's
          loaded faces carry no Greek subset — rendering them as text fell
          back to a system serif. */}
      <g
        fill="none"
        stroke={GREY}
        strokeWidth="13"
        strokeLinecap="square"
        strokeLinejoin="miter"
      >
        {/* Sigma: top bar, in to the waist, out to the foot, bottom bar. */}
        <path d="M96 172 H34 L70 211 L34 250 H96" />
        {/* Pi: crossbar over two legs that splay very slightly. */}
        <path d="M418 178 H486" />
        <path d="M437 178 L432 250" />
        <path d="M468 178 L472 250" />
      </g>

    </svg>
  );
}
