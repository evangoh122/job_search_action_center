import { applicationDefault, cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

// Single account allowed to use this private tracker.
export const ALLOWED_EMAIL = "evangohsg@gmail.com";

/** Thrown by {@link verifyRequestUser} to carry the HTTP status an API route should respond with. */
export class AuthError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/**
 * Returns the singleton Firebase Admin app, initializing it on first use.
 *
 * Prefers an explicit service account JSON (`FIREBASE_SERVICE_ACCOUNT_JSON`) so the app runs
 * identically in local dev; falls back to ambient credentials for Cloud Run / Firebase App Hosting.
 *
 * @returns The initialized (or already-existing) Firebase Admin app.
 */
function getAdminApp(): App {
  const existing = getApps();
  if (existing.length) return existing[0];

  const serviceAccountJson = process.env.FIREBASE_SERVICE_ACCOUNT_JSON;
  if (serviceAccountJson) {
    return initializeApp({ credential: cert(JSON.parse(serviceAccountJson)) });
  }
  // Falls back to GOOGLE_APPLICATION_CREDENTIALS or the ambient service
  // account on Cloud Run / Firebase App Hosting.
  return initializeApp({ credential: applicationDefault() });
}

/**
 * Verifies the bearer token on an incoming request and enforces that it belongs to the single
 * allowed, Google-verified account for this private tracker.
 *
 * The checks run in order — missing token, invalid/expired token, unverified email, non-Google
 * provider, then wrong account — so the caller always gets the most specific applicable reason.
 *
 * @param request - The incoming request; expects an `Authorization: Bearer <idToken>` header.
 * @returns The verified user's Firebase UID and email.
 * @throws {AuthError} 401 if the token is missing, invalid, or expired.
 * @throws {AuthError} 403 if the email is unverified, the sign-in provider isn't Google, or the account isn't {@link ALLOWED_EMAIL}.
 */
export async function verifyRequestUser(request: Request): Promise<{ uid: string; email: string }> {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) throw new AuthError(401, "Missing bearer token");

  const app = getAdminApp();
  let decoded;
  try {
    // `checkRevoked = true` so a signed-out/revoked session is rejected even if the ID token itself hasn't expired yet.
    decoded = await getAuth(app).verifyIdToken(token, true);
  } catch {
    throw new AuthError(401, "Invalid or expired token");
  }

  // Defense in depth beyond token validity: require a verified email, require Google as the
  // sign-in provider (no password/other-IdP accounts), and pin to the single allowed address.
  if (!decoded.email_verified) throw new AuthError(403, "Email not verified");
  if (decoded.firebase?.sign_in_provider !== "google.com") throw new AuthError(403, "Only Google sign-in is permitted");
  if (decoded.email !== ALLOWED_EMAIL) throw new AuthError(403, "Not authorized");
  return { uid: decoded.uid, email: decoded.email! };
}
