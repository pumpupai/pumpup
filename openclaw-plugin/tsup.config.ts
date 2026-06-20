import { defineConfig } from "tsup";

/// Bundle the plugin + the local Pump Up Fern SDK source into a single ESM file.
/// `openclaw` and node builtins are provided by the host gateway, so they stay external.
export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  platform: "node",
  target: "node22",
  bundle: true,
  external: ["openclaw", /^openclaw\//, /^node:/],
  clean: true,
  outDir: "dist",
});
