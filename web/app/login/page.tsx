"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { signInWithPopup, signOut } from "firebase/auth";
import { getFirebaseAuth, googleProvider, ALLOWED_EMAIL } from "@/lib/firebase-client";

function LoginContent() {
  const searchParams = useSearchParams();
  const unauthorized = searchParams.get("error") === "unauthorized";
  const [error, setError] = useState<string | null>(unauthorized ? `Only ${ALLOWED_EMAIL} may sign in.` : null);
  const [loading, setLoading] = useState(false);

  async function handleSignIn() {
    setError(null);
    setLoading(true);
    try {
      const auth = getFirebaseAuth();
      const result = await signInWithPopup(auth, googleProvider);
      if (result.user.email !== ALLOWED_EMAIL) {
        await signOut(auth);
        setError(`Only ${ALLOWED_EMAIL} may sign in.`);
      }
    } catch {
      setError("Sign-in failed. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: "100dvh", display: "grid", placeItems: "center", background: "#f0f9ff", fontFamily: "Arial, sans-serif" }}>
      <div style={{ background: "#fff", border: "1px solid #bae6fd", borderRadius: 14, padding: 32, width: "min(360px, 90vw)", textAlign: "center" }}>
        <h1 style={{ fontSize: 20, marginBottom: 6, color: "#0c4a6e" }}>Job Search Action Center</h1>
        <p style={{ color: "#52738a", fontSize: 14, marginBottom: 20 }}>Private access only.</p>
        <button
          onClick={handleSignIn}
          disabled={loading}
          style={{ minHeight: 44, width: "100%", borderRadius: 10, border: 0, background: "#0369a1", color: "#fff", fontWeight: 700, cursor: loading ? "wait" : "pointer" }}
        >
          {loading ? "Signing in…" : "Sign in with Google"}
        </button>
        {error && <p style={{ color: "#b91c1c", fontSize: 13, marginTop: 14 }}>{error}</p>}
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginContent />
    </Suspense>
  );
}
