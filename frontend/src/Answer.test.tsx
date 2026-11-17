import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { Answer } from "./Answer";
import type { LawMessage } from "./types";

afterEach(cleanup);

describe("Answer", () => {
  it("shows the user's question while the chat is streaming", () => {
    const message: LawMessage = {
      id: "user-1",
      role: "user",
      parts: [{ type: "text", text: "How is end of service calculated?" }],
    };

    render(<Answer message={message} language="en" streaming={true} />);

    expect(
      screen.getByText("How is end of service calculated?"),
    ).toBeTruthy();
  });
});
