import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "1.5rem",
      screens: {
        "2xl": "1280px",
      },
    },
    // Outside `extend`, so it replaces Tailwind's scale: `shadow-sm` and friends stop
    // compiling, and what is left is four named levels declared per theme in globals.css.
    // There were seventeen hand-written shadows, most in a fixed slate that ignored the
    // dark appearance. `none` stays for switching one off.
    boxShadow: {
      none: "none",
      raised: "var(--shadow-raised)",
      lifted: "var(--shadow-lifted)",
      floating: "var(--shadow-floating)",
      overlay: "var(--shadow-overlay)",
    },
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      colors: {
        /* The Gates Foundation's brand yellow, for the page shell.

           Named rather than written as an arbitrary value, so `tone.test.ts` can assert where
           it appears: it is seven degrees from `--tone-marked`, which means "a result cites
           this passage", and so must never reach a result. */
        brand: {
          DEFAULT: "hsl(var(--brand-accent))",
          foreground: "hsl(var(--brand-accent-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // The assistant's mark. Named, like `brand`, so a test can say where it may appear.
        assistant: {
          DEFAULT: "hsl(var(--assistant))",
          foreground: "hsl(var(--assistant-foreground))",
        },
      },
      // One motion vocabulary for the whole app. Components reference these
      // tokens instead of inventing durations, and lib/motion.ts maps each
      // kind of state change to exactly one recipe.
      transitionDuration: {
        fast: "120ms",
        base: "180ms",
        slow: "320ms",
      },
      transitionTimingFunction: {
        enter: "cubic-bezier(0.2, 0, 0, 1)",
        exit: "cubic-bezier(0.4, 0, 1, 1)",
      },
      keyframes: {
        "pixel-wave": {
          "0%, 100%": { opacity: "0.25" },
          "35%": { opacity: "1" },
        },
        // The assistant closing its eyes once, as a reply starts.
        blink: {
          "0%, 100%": { transform: "scaleY(1)" },
          "50%": { transform: "scaleY(0.1)" },
        },
        "fade-rise": {
          from: { opacity: "0", transform: "translateY(2px)" },
          to: { opacity: "1", transform: "none" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "pixel-wave": "pixel-wave 650ms ease-in-out infinite",
        "fade-rise": "fade-rise 180ms cubic-bezier(0.2, 0, 0, 1)",
        blink: "blink 240ms ease-in-out 1",
        shimmer: "shimmer 1.6s infinite",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
        // Overlays: a dialog, a sheet, the assistant. On the same variable, so the ladder
        // moves as one when `--radius` does.
        "2xl": "calc(var(--radius) + 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
