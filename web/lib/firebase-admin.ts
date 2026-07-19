import { applicationDefault, cert, getApps, initializeApp, type App } from "firebase-admin/app";
import { getAuth } from "firebase-admin/auth";

// Single account allowed to use this private tracker.
export const ALLOWED_EMAIL = "evangohsg@gmail.com";

export class AuthError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

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

export async function verifyRequestUser(request: Request): Promise<{ uid: string; email: string }> {
  const header = request.headers.get("authorization") || "";
  const token = header.startsWith("Bearer ") ? header.slice(7) : "";
  if (!token) throw new AuthError(401, "Missing bearer token");

  const app = getAdminApp();
  let decoded;
  try {
    decoded = await getAuth(app).verifyIdToken(token, true);
  } catch {
    throw new AuthError(401, "Invalid or expired token");
  }

  if (!decoded.email_verified) throw new AuthError(403, "Email not verified");
  if (decoded.firebase?.sign_in_provider !== "google.com") throw new AuthError(403, "Only Google sign-in is permitted");
  if (decoded.email !== ALLOWED_EMAIL) throw new AuthError(403, "Not authorized");
  return { uid: decoded.uid, email: decoded.email! };
}
