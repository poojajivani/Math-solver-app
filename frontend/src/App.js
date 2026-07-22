import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { isSupabaseConfigured, supabase } from "./supabase";

import Login from "./pages/Login";
import Signup from "./pages/Signup";
import AuthCallback from "./pages/AuthCallback";
import MathSolver from "./MathSolver";
import "./pages/Auth.css";

function AuthLoading() {
  return (
    <main className="auth-page">
      <section className="auth-card auth-loading-card">
        <span className="auth-badge">AI Math Solver</span>
        <div className="auth-spinner" />
        <p>Opening Math Solver...</p>
      </section>
    </main>
  );
}

function ProtectedRoute({ children }) {
  const [session, setSession] = useState(undefined);

  useEffect(() => {
    if (!isSupabaseConfigured) {
      setSession(null);
      return;
    }

    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, session) => {
      setSession(session);
    });

    return () => subscription.unsubscribe();
  }, []);

  if (session === undefined) {
    return <AuthLoading />;
  }

  return session ? children : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route path="/signup" element={<Signup />} />

      <Route path="/auth/callback" element={<AuthCallback />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <MathSolver />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}
