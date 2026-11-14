import fs from "node:fs";
import path from "node:path";

const root = path.resolve(import.meta.dirname, "..");
const srcDir = path.join(root, "node_modules", "cesium", "Build", "Cesium");
const destDir = path.join(root, "public", "cesium");

const folders = ["Assets", "ThirdParty", "Widgets", "Workers"];

if (!fs.existsSync(srcDir)) {
  console.error("Cesium build directory not found:", srcDir);
  process.exit(1);
}

fs.mkdirSync(destDir, { recursive: true });

for (const folder of folders) {
  const from = path.join(srcDir, folder);
  const to = path.join(destDir, folder);
  if (fs.existsSync(from)) {
    fs.cpSync(from, to, { recursive: true, force: true });
  }
}

console.log("Synced CesiumJS static assets to public/cesium/");
