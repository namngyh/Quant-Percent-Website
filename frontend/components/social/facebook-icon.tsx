/**
 * The Facebook "f". lucide dropped brand marks in 1.x, so it is drawn here;
 * `currentColor` lets it take the colour of whatever link it sits in.
 */
export function FacebookIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M13.5 21.95V14.5h2.5l.4-3h-2.9V9.6c0-.87.25-1.46 1.5-1.46h1.55V5.46A20.7 20.7 0 0 0 14.3 5.3c-2.24 0-3.8 1.37-3.8 3.9v2.3H8v3h2.5v7.45a10 10 0 1 1 3 0Z" />
    </svg>
  );
}
