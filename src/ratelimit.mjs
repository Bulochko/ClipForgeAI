/**
 * Sliding-window rate limiter.
 * Free tiers are limited per minute, and a single chatty user must not burn the
 * whole quota for everyone else.
 */
export function createLimiter({ limit, windowMs }) {
  const hits = new Map();

  return {
    /** Returns true when the request is allowed; records it otherwise. */
    allow(key, now = Date.now()) {
      if (limit <= 0) return true;
      const recent = (hits.get(key) ?? []).filter((time) => now - time < windowMs);
      if (recent.length >= limit) {
        hits.set(key, recent);
        return false;
      }
      recent.push(now);
      hits.set(key, recent);
      return true;
    },

    /** Seconds until the next request would be allowed. */
    retryAfter(key, now = Date.now()) {
      const recent = (hits.get(key) ?? []).filter((time) => now - time < windowMs);
      if (recent.length < limit) return 0;
      const oldest = Math.min(...recent);
      return Math.max(1, Math.ceil((oldest + windowMs - now) / 1000));
    },
  };
}
