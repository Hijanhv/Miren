import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0a0a0a",
        surface: "#111111",
        raised: "#161616",
        line: "#1f1f1f",
        accent: "#22c55e",
        danger: "#ef4444",
        warn: "#f59e0b",
        fg: "#ffffff",
        muted: "#888888",
        regime: {
          trending: "#3b82f6",
          reverting: "#a855f7",
          volatile: "#ef4444",
          calm: "#22c55e",
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      keyframes: {
        blink: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.2" } },
        dot: { "0%, 80%, 100%": { opacity: "0.2" }, "40%": { opacity: "1" } },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: {
        blink: "blink 1.2s ease-in-out infinite",
        dot: "dot 1.2s ease-in-out infinite",
        shimmer: "shimmer 1.4s linear infinite",
      },
    },
  },
  plugins: [],
};

export default config;
