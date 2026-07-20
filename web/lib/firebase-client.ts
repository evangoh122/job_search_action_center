"use client";

import { getApps, initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, GoogleAuthProvider, type Auth } from "firebase/auth";

// Single account allowed to use this private tracker.
export const ALLOWED_EMAIL = "evangohsg@gmail.com";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID,
};

export const googleProvider = new GoogleAuthProvider();

let cachedApp: FirebaseApp | null = null;
let cachedAuth: Auth | null = null;

// Lazy on purpose: this module is imported by client components that also
// render during server-side prerendering, where NEXT_PUBLIC_FIREBASE_* env
// vars may be absent. Calling getAuth() at module scope would throw
// auth/invalid-api-key during `next build`. Every real caller only invokes
// this from a browser event handler or useEffect, never at render time.
export function getFirebaseAuth(): Auth {
  if (cachedAuth) return cachedAuth;
  cachedApp = getApps().length ? getApps()[0]! : initializeApp(firebaseConfig);
  cachedAuth = getAuth(cachedApp);
  return cachedAuth;
}

export async function getIdToken(): Promise<string | null> {
  const user = getFirebaseAuth().currentUser;
  return user ? user.getIdToken() : null;
}
