import { useState } from "react";
import { Link } from "react-router-dom";
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

export default function Signup() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [cooldownSeconds, setCooldownSeconds] = useState(0);
  const [showLoginLink, setShowLoginLink] = useState(false);
  const [signupCompleted, setSignupCompleted] = useState(false);

  async function handleSignup(event) {
    event.preventDefault();
    setErrorMessage("");
    setSuccessMessage("");
    setShowLoginLink(false);

    if (signupCompleted) {
      setSuccessMessage("Confirmation email already sent. Please check your inbox/spam folder, then login after confirming.");
      setShowLoginLink(true);
      return;
    }

    if (cooldownSeconds > 0) {
      setErrorMessage(getRateLimitMessage(cooldownSeconds));
      return;
    }

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

    if (password.length < 6) {
      setErrorMessage("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);

    // Clear any old stored session before signup. A new signup must not enter
    // MathSolver until that new email is confirmed and the user logs in.
    await supabase.auth.signOut();

    const { data, error } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        emailRedirectTo: `${window.location.origin}/#/auth/callback`,
      },
    });

    setLoading(false);

    if (error) {
      if (isRateLimitError(error)) {
        startCooldown(setCooldownSeconds);
        setShowLoginLink(true);
        setSuccessMessage(
          `${getRateLimitMessage()} Please check your inbox/spam folder for the confirmation email already sent.`
        );
      } else {
        setErrorMessage(error.message);
      }
    } else if (
      data.user &&
      Array.isArray(data.user.identities) &&
      data.user.identities.length === 0
    ) {
      setErrorMessage("This email already has an account. Please login instead of signing up again.");
      setShowLoginLink(true);
    } else if (data.session) {
      await supabase.auth.signOut();
      setSuccessMessage("Signup successful. Please confirm your email before logging in.");
      setSignupCompleted(true);
      setShowLoginLink(true);
    } else {
      setSuccessMessage("Signup successful. Please check your email and confirm your account, then login.");
      setSignupCompleted(true);
      setShowLoginLink(true);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card">
        <div className="auth-brand">
          <span className="auth-badge">AI Math Solver</span>
          <h1>Create account</h1>
          <p>Save your work and access your solver from any device.</p>
        </div>

        <form className="auth-form" onSubmit={handleSignup}>
          <label>
            Email
            <input
              id="signup-email"
              name="email"
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
                setSignupCompleted(false);
              }}
              autoComplete="email"
            />
          </label>

          <label>
            Password
            <input
              id="signup-password"
              name="password"
              type="password"
              placeholder="Minimum 6 characters"
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
                setSignupCompleted(false);
              }}
              autoComplete="new-password"
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

          {(showLoginLink || cooldownSeconds > 0) && (
            <Link className="auth-secondary-link" to="/login">
              Go to login
            </Link>
          )}

          <button
            className="auth-button"
            type="submit"
            disabled={loading || cooldownSeconds > 0 || signupCompleted}
          >
            {loading
              ? "Creating account..."
              : cooldownSeconds > 0
                ? `Try again in ${cooldownSeconds}s`
                : signupCompleted
                  ? "Check your email"
                : "Sign up"}
          </button>
        </form>

        <p className="auth-switch">
          Already have an account? <Link to="/login">Login</Link>
        </p>
      </section>
    </main>
  );
}
