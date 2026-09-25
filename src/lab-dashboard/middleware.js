// Vercel Edge Middleware — password gate for the static dashboard.
// Runs on the Edge Runtime (Web APIs only: Request, Response, URL, crypto.subtle).
// No framework (no Next.js) is used here, so the handler is a plain default
// export, per Vercel's framework-agnostic Edge Middleware convention:
// https://vercel.com/docs/functions/edge-middleware
//
// Behavior:
// - Every request is intercepted before any static file (index.html, app.js,
//   style.css, data/*.json) is served.
// - A valid `dashboard_session` cookie lets the request continue unchanged.
// - Anything else is redirected to /login, EXCEPT requests under /api/,
//   which get a JSON 401 `{"error":"unauthorized"}` instead (no HTML
//   redirect makes sense for a JSON API consumed via fetch()).
// - POST /login verifies the submitted password against DASHBOARD_PASSWORD
//   (an env var configured in the Vercel dashboard, see README.md) and, if
//   correct, sets a signed, long-lived session cookie ("remember me").

const COOKIE_NAME = 'dashboard_session';
const SESSION_DAYS = 90;
const SESSION_MAX_AGE_SECONDS = SESSION_DAYS * 24 * 60 * 60;

async function sha256Hex(message) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(message));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

async function hmacSha256Hex(secret, message) {
  const key = await crypto.subtle.importKey(
    'raw',
    new TextEncoder().encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );
  const signature = await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(message));
  return [...new Uint8Array(signature)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

// Fixed-length digest comparison avoids leaking string length / early-exit timing.
function timingSafeEqual(a, b) {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let i = 0; i < a.length; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

function getCookie(request, name) {
  const header = request.headers.get('cookie') || '';
  const match = header.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Session token = "<expiryMs>.<hmac(expiryMs)>". Unguessable without the
// secret (DASHBOARD_PASSWORD) and self-expiring, without needing a session
// store — appropriate for a personal, two-user dashboard.
async function createSessionCookieValue(secret) {
  const expiresAt = Date.now() + SESSION_MAX_AGE_SECONDS * 1000;
  const signature = await hmacSha256Hex(secret, String(expiresAt));
  return `${expiresAt}.${signature}`;
}

async function isValidSessionCookie(value, secret) {
  if (!value) return false;
  const [expiresAtStr, signature] = value.split('.');
  if (!expiresAtStr || !signature) return false;

  const expiresAt = Number(expiresAtStr);
  if (!Number.isFinite(expiresAt) || expiresAt < Date.now()) return false;

  const expectedSignature = await hmacSha256Hex(secret, expiresAtStr);
  return timingSafeEqual(expectedSignature, signature);
}

export const config = {
  matcher: '/:path*',
};

export default async function middleware(request) {
  const secret = process.env.DASHBOARD_PASSWORD;
  const url = new URL(request.url);
  const { pathname } = url;

  if (!secret) {
    return new Response(
      'Falta configurar la variable de entorno DASHBOARD_PASSWORD en Vercel ' +
        '(Settings → Environment Variables). Ver README.md.',
      { status: 500, headers: { 'content-type': 'text/plain; charset=utf-8' } }
    );
  }

  const isLoginPath = pathname === '/login' || pathname === '/login.html';

  if (request.method === 'POST' && pathname === '/login') {
    const form = await request.formData();
    const submittedPassword = String(form.get('password') || '');

    const passwordOk = timingSafeEqual(
      await sha256Hex(submittedPassword),
      await sha256Hex(secret)
    );

    if (!passwordOk) {
      return Response.redirect(new URL('/login?error=1', url), 303);
    }

    const cookieValue = await createSessionCookieValue(secret);
    // Response.redirect(...) devuelve headers inmutables en el runtime de Vercel
    // (TypeError: immutable al intentar .append()) -- hay que construir la
    // respuesta a mano con un Headers propio (mutable) desde el arranque.
    const headers = new Headers({ Location: new URL('/', url).toString() });
    headers.append(
      'Set-Cookie',
      `${COOKIE_NAME}=${cookieValue}; Path=/; Max-Age=${SESSION_MAX_AGE_SECONDS}; ` +
        'HttpOnly; Secure; SameSite=Lax'
    );
    return new Response(null, { status: 303, headers });
  }

  if (isLoginPath) {
    // Already logged in and browsing to /login on purpose: send them home.
    if (request.method === 'GET') {
      const existingCookie = getCookie(request, COOKIE_NAME);
      if (await isValidSessionCookie(existingCookie, secret)) {
        return Response.redirect(new URL('/', url), 303);
      }
    }
    return undefined; // let Vercel serve the static login.html
  }

  const cookieValue = getCookie(request, COOKIE_NAME);
  const sessionValid = await isValidSessionCookie(cookieValue, secret);

  // API routes never redirect to /login (there's no browser navigation to
  // redirect): missing/expired session means a JSON 401 so fetch() callers
  // can handle it programmatically instead of following an HTML redirect.
  if (pathname.startsWith('/api/')) {
    if (!sessionValid) {
      return new Response(JSON.stringify({ error: 'unauthorized' }), {
        status: 401,
        headers: { 'content-type': 'application/json; charset=utf-8' },
      });
    }
    return undefined; // valid session: continue to the API route
  }

  if (!sessionValid) {
    return Response.redirect(new URL('/login', url), 303);
  }

  return undefined; // valid session: continue to the original static asset
}
