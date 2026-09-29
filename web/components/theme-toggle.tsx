"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

const STORAGE_KEY = "pdis-theme";

function storedTheme(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function applyTheme(dark: boolean) {
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
}

/** Drawn by its caller, so it takes the shape of the controls beside it. */
export function ThemeToggle({ className }: { className?: string }) {
  const [dark, setDark] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const stored = storedTheme();
    const initialDark = stored === "dark";
    applyTheme(initialDark);
    setDark(initialDark);
    setMounted(true);
  }, []);

  const toggle = () => {
    const next = !dark;
    applyTheme(next);
    setDark(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next ? "dark" : "light");
    } catch {
      // The visual preference still applies for this page when storage is unavailable.
    }
  };

  const label = dark ? "Switch to light mode" : "Switch to dark mode";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={className}
    >
      {mounted && dark ? (
        <Sun className="h-3.5 w-3.5" aria-hidden="true" />
      ) : (
        <Moon className="h-3.5 w-3.5" aria-hidden="true" />
      )}
    </button>
  );
}
