import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "./App";

vi.mock("./useSession", async (importOriginal) => {
  const original = await importOriginal<typeof import("./useSession")>();
  return {
    ...original,
    useSession: () => ({
      session: original.initialSession,
      health: null,
      connected: false,
      busy: false,
      actionError: null,
      setActionError: vi.fn(),
      start: vi.fn(),
      control: vi.fn(),
      perform: vi.fn(),
    }),
  };
});

describe("Main workspace showcase navigation", () => {
  it("opens from the dashboard without a backend and links to the real calibration workspace", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Start guided demo" }));
    expect(
      screen.getByRole("heading", { name: "Guided showcase" }),
    ).toBeVisible();
    expect(
      screen.queryByText("The local backend is unavailable."),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "03 Perspective calibration" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Open Calibration & gates" }),
    );
    expect(
      screen.getByRole("heading", { name: "Calibration & gates" }),
    ).toBeVisible();
    expect(screen.getByText("The local backend is unavailable.")).toBeVisible();
  });
});
