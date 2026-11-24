// The access token lives in memory only. The refresh token is kept in localStorage so a
// reload does not log the user out; it is rotated and blacklisted server side on every
// refresh and on logout, which limits what a stolen copy is worth.
const REFRESH_KEY = "inventra_refresh";

let accessToken: string | null = null;

export const tokens = {
  get access() {
    return accessToken;
  },
  get refresh(): string | null {
    try {
      return localStorage.getItem(REFRESH_KEY);
    } catch {
      return null;
    }
  },
  set(access: string, refresh?: string) {
    accessToken = access;
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
  },
  clear() {
    accessToken = null;
    try {
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* storage unavailable */
    }
  },
};
