// src/main.tsx
// Application entry point. Mounts the React tree into the #root div.
// Global CSS (Tailwind + design tokens) is imported here once.

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App";

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found in index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
