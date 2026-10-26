import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
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
describe("Traffic Intelligence navigation", () => {
  it("opens lazily and retains analyst filters while navigating the existing dashboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    expect(
      screen.queryByRole("tab", { name: "Lines & zones" }),
    ).not.toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Traffic Intelligence" }),
    );
    expect(
      screen.getByRole("heading", { name: "Traffic Intelligence" }),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("Start source time · s"), {
      target: { value: "15" },
    });
    await user.click(screen.getByRole("button", { name: "Dashboard" }));
    expect(screen.getByText("No tracks to inspect yet")).toBeVisible();
    await user.click(
      screen.getByRole("button", { name: "Traffic Intelligence" }),
    );
    expect(screen.getByLabelText("Start source time · s")).toHaveValue(15);
    expect(screen.getByText("PHASE 06")).toBeVisible();
  });
});
