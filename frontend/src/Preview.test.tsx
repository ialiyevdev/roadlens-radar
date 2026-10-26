import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import Preview from "./Preview";
import { initialSession } from "./useSession";
import type { Session } from "./types";

const session: Session = {
  ...initialSession,
  state: "running",
  session_id: "preview-session",
  frame_index: 20,
  preview_revision: 22,
  width: 640,
  height: 480,
};

describe("observation preview transport", () => {
  it("streams while running and requests the final JPEG when paused or finished", () => {
    const { rerender } = render(<Preview session={session} />);
    const preview = screen.getByRole("img", { name: /Processed source/ });
    expect(preview).toHaveAttribute(
      "src",
      "/api/stream?session=preview-session&retry=0",
    );
    for (const state of ["paused", "completed", "stopped", "error"] as const) {
      rerender(<Preview session={{ ...session, state }} />);
      expect(preview).toHaveAttribute(
        "src",
        "/api/frame?session=preview-session&revision=22&retry=0",
      );
    }
    rerender(<Preview session={session} />);
    expect(preview).toHaveAttribute(
      "src",
      "/api/stream?session=preview-session&retry=0",
    );
  });
  it("reloads a paused frame when its rendered overlay revision changes", () => {
    const { rerender } = render(
      <Preview session={{ ...session, state: "paused" }} />,
    );
    const preview = screen.getByRole("img", { name: /Processed source/ });
    expect(preview).toHaveAttribute(
      "src",
      "/api/frame?session=preview-session&revision=22&retry=0",
    );
    rerender(
      <Preview
        session={{ ...session, state: "paused", preview_revision: 23 }}
      />,
    );
    expect(preview).toHaveAttribute(
      "src",
      "/api/frame?session=preview-session&revision=23&retry=0",
    );
  });
});
