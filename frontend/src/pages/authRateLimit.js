export const AUTH_RATE_LIMIT_SECONDS = 600;

export function isRateLimitError(error) {
  return (error?.message || "")
    .toLowerCase()
    .includes("rate limit");
}

export function getRateLimitMessage(seconds = AUTH_RATE_LIMIT_SECONDS) {
  if (seconds >= 60) {
    const minutes = Math.ceil(seconds / 60);
    return `Too many confirmation emails were requested. Please wait about ${minutes} minute${minutes === 1 ? "" : "s"}, then try again.`;
  }

  return `Too many confirmation emails were requested. Please wait ${seconds} seconds, then try again.`;
}

export function getCooldownSeconds(storageKey) {
  const retryAt = Number(window.localStorage.getItem(storageKey));

  if (!retryAt) return 0;

  const seconds = Math.ceil((retryAt - Date.now()) / 1000);

  if (seconds <= 0) {
    window.localStorage.removeItem(storageKey);
    return 0;
  }

  return seconds;
}

export function startCooldown(
  setSeconds,
  seconds = AUTH_RATE_LIMIT_SECONDS,
  storageKey = ""
) {
  if (storageKey) {
    window.localStorage.setItem(
      storageKey,
      String(Date.now() + seconds * 1000)
    );
  }

  setSeconds(seconds);

  const intervalId = window.setInterval(() => {
    setSeconds((currentSeconds) => {
      if (currentSeconds <= 1) {
        window.clearInterval(intervalId);

        if (storageKey) {
          window.localStorage.removeItem(storageKey);
        }

        return 0;
      }

      return currentSeconds - 1;
    });
  }, 1000);

  return intervalId;
}

export function resumeCooldown(setSeconds, storageKey) {
  const seconds = getCooldownSeconds(storageKey);

  if (seconds <= 0) {
    setSeconds(0);
    return undefined;
  }

  setSeconds(seconds);

  const intervalId = window.setInterval(() => {
    const remainingSeconds = getCooldownSeconds(storageKey);
    setSeconds(remainingSeconds);

    if (remainingSeconds <= 0) {
      window.clearInterval(intervalId);
    }
  }, 1000);

  return intervalId;
}
