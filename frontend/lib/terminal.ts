/**
 * QP Terminal lives on its own subdomain, behind the proxy's password, rather
 * than under a path of this site: its frontend asks for `/api/...` and
 * `/static/...` from the root, and `/api/*` already belongs to the website API.
 *
 * NEXT_PUBLIC_* is inlined at build time. Production relies on the default, so
 * nothing has to be threaded through the Docker build; set the variable only to
 * point a local build at a Terminal running elsewhere (e.g. localhost:8000).
 */
export const TERMINAL_URL =
  process.env.NEXT_PUBLIC_TERMINAL_URL ?? "https://terminal.quantpercent.com";

/**
 * What the site's own links open: the website page that checks the session
 * and forwards to TERMINAL_URL. Linking to the subdomain directly works too
 * (its gate redirects here), but costs a signed-out visitor a round trip
 * through the Terminal's host before they see the sign-in form. Unprefixed on
 * purpose: the locale middleware adds the visitor's language.
 */
export const TERMINAL_ENTRY = "/terminal";
