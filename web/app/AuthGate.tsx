"use client";

import { onAuthStateChanged, signOut } from "firebase/auth";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ALLOWED_EMAIL, getFirebaseAuth } from "@/lib/firebase-client";

type Status = "checking" | "allowed" | "denied";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    const auth = getFirebaseAuth();
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (pathname === "/login") {
        if (user && user.email === ALLOWED_EMAIL) {
          setStatus("allowed");
          router.replace("/");
          return;
        }
        setStatus("allowed");
        return;
      }
      if (!user) {
        setStatus("denied");
        router.replace("/login");
        return;
      }
      if (user.email !== ALLOWED_EMAIL) {
        setStatus("denied");
        signOut(auth);
        router.replace("/login?error=unauthorized");
        return;
      }
      setStatus("allowed");
    });
    return unsubscribe;
  }, [pathname, router]);

  if (pathname === "/login") return <>{children}</>;
  if (status !== "allowed") return null;
  return <>{children}</>;
}
