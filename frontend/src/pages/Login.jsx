import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  isSupabaseConfigured,
  supabase,
  supabaseConfigError
} from "../supabase";
import {
  getRateLimitMessage,
  isRateLimitError,
  startCooldown
} from "./authRateLimit";
import "./Auth.css";

export default function Login() {

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resendLoading, setResendLoading] = useState(false);
  const [resendCooldownSeconds, setResendCooldownSeconds] = useState(0);
  const [showResendConfirmation, setShowResendConfirmation] = useState(false);
  const navigate = useNavigate();

  async function handleLogin(event) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    setShowResendConfirmation(false);

    if (!isSupabaseConfigured) {
      setErrorMessage(
        `${supabaseConfigError} Fix frontend/.env, then restart the frontend server.`
      );
      return;
    }

    if (!email.trim() || !password) {
      setErrorMessage("Please enter both email and password.");
      return;
    }

    setLoading(true);

    const { data, error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    setLoading(false);

    if (error) {
      const message = error.message || "Unable to login.";
      const emailNotConfirmed = message.toLowerCase().includes("email not confirmed");

      setErrorMessage(
        emailNotConfirmed
          ? "Email not confirmed. Please confirm your email first, or resend the confirmation link below."
          : message
      );
      setShowResendConfirmation(emailNotConfirmed);
    } else if (data.session) {
      navigate("/", { replace: true });
    }
  }

  async function handleResendConfirmation() {
    setErrorMessage("");
    setSuccessMessage("");

    if (resendCooldownSeconds > 0) {
      setErrorMessage(getRateLimitMessage(resendCooldownSeconds));
      return;
    }

    if (!isSupabaseConfigured) {
      setErrorMessage(
        `${supabaseConfigError} Fix frontend/.env, then restart the frontend server.`
      );
      return;
    }

    if (!email.trim()) {
      setErrorMessage("Please enter your email, then resend confirmation.");
      return;
    }

    setResendLoading(true);

    const { error } = await supabase.auth.resend({
      type: "signup",
      email: email.trim(),
      options: {
        emailRedirectTo: `${window.location.origin}/#/auth/callback`,
      },
    });

    setResendLoading(false);

    if (error) {
      if (isRateLimitError(error)) {
        startCooldown(setResendCooldownSeconds);
        setSuccessMessage(
          `${getRateLimitMessage()} Please check your inbox/spam folder for the confirmation email already sent.`
        );
      } else {
        setErrorMessage(error.message);
      }
    } else {
      setSuccessMessage("Confirmation email sent. Open your email, confirm your account, then login.");
      setShowResendConfirmation(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="auth-badge">AI Math Solver</span>
          <h1>Welcome back</h1>
          <p>Login to continue solving math, physics, and chemistry problems.</p>
        </div>

        <form className="auth-form" onSubmit={handleLogin}>
          <label>
            Email
            <input
              id="login-email"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
            />
          </label>

          <label>
            Password
            <input
              id="login-password"
              name="password"
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
            />
          </label>

          {errorMessage && (
            <div className="auth-alert">
              {errorMessage}
            </div>
          )}

          {successMessage && (
            <div className="auth-alert auth-alert-success">
              {successMessage}
            </div>
          )}

          {showResendConfirmation && (
            <button
              className="auth-secondary-button"
              type="button"
              onClick={handleResendConfirmation}
              disabled={resendLoading || resendCooldownSeconds > 0}
            >
              {resendLoading
                ? "Sending..."
                : resendCooldownSeconds > 0
                  ? `Try again in ${resendCooldownSeconds}s`
                  : "Resend confirmation email"}
            </button>
          )}

          <button
            className="auth-button"
            type="submit"
            disabled={loading}
          >
            {loading ? "Logging in..." : "Login"}
          </button>
        </form>

        <p className="auth-switch">
          New here? <Link to="/signup">Create an account</Link>
        </p>
      </section>
    </main>
  );
}
