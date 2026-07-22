import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  isSupabaseConfigured,
  supabase,
  supabaseConfigError
} from "../supabase";
import "./Auth.css";

function getCallbackParams() {
  const params = new URLSearchParams(window.location.search);
  const hash = window.location.hash.replace(/^#/, "");
  const hashQuery = hash.includes("?")
    ? hash.slice(hash.indexOf("?") + 1)
    : hash;
  const hashParams = new URLSearchParams(hashQuery);

  return { params, hashParams };
}

export default function AuthCallback() {
  const navigate = useNavigate();
  const [message, setMessage] = useState("Confirming your account...");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    async function finishAuth() {
      if (!isSupabaseConfigured) {
        setErrorMessage(
          `${supabaseConfigError} Fix frontend/.env, then restart the frontend server.`
        );
        return;
      }

      const { params, hashParams } = getCallbackParams();
      const code = params.get("code") || hashParams.get("code");
      const accessToken = hashParams.get("access_token");
      const refreshToken = hashParams.get("refresh_token");
      const urlError =
        params.get("error_description") ||
        hashParams.get("error_description") ||
        params.get("error") ||
        hashParams.get("error");

      if (urlError) {
        setErrorMessage(urlError.replace(/\+/g, " "));
        return;
      }

      if (code) {
        const { error } = await supabase.auth.exchangeCodeForSession(code);

        if (error) {
          setErrorMessage(error.message);
          return;
        }
      }

      if (accessToken && refreshToken) {
        const { error } = await supabase.auth.setSession({
          access_token: accessToken,
          refresh_token: refreshToken,
        });

        if (error) {
          setErrorMessage(error.message);
          return;
        }
      }

      const { data, error } = await supabase.auth.getSession();

      if (error) {
        setErrorMessage(error.message);
        return;
      }

      if (data.session) {
        setMessage("Account confirmed. Opening Math Solver...");
        navigate("/", { replace: true });
        return;
      }

      setMessage("Account confirmed. Please login to continue.");
      setTimeout(() => {
        navigate("/login", { replace: true });
      }, 1200);
    }

    finishAuth();
  }, [navigate]);

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="auth-badge">AI Math Solver</span>
          <h1>Email confirmation</h1>
          <p>{message}</p>
        </div>

        {errorMessage && (
          <>
            <div className="auth-alert">
              {errorMessage}
            </div>

            <p className="auth-switch">
              <Link to="/login">Back to login</Link>
            </p>
          </>
        )}
      </section>
    </main>
  );
}
