// Docs: https://vitest.dev/config/environment (vitest 5.1.0)
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
  },
});
