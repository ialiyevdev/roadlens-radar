import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const application =
  import.meta.env.MODE === "showcase"
    ? import("./StaticShowcase")
    : import("./App");

void application.then(({ default: Application }) => {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <Application />
    </StrictMode>,
  );
});
