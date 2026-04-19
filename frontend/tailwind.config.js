/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Clinical palette — high contrast for ward-lighting legibility.
        clinical: {
          50: "#f0f7ff",
          600: "#0b5ad9",
          700: "#0a4aa8",
          900: "#05265a",
        },
        warn: {
          500: "#d97706",
          700: "#b25400",
        },
        danger: {
          500: "#dc2626",
          700: "#991b1b",
        },
      },
    },
  },
  plugins: [],
};
