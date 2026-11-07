import fs from "node:fs";
import path from "node:path";

const IMAGE_TYPES = new Map([
  [".png", "image/png"],
  [".jpg", "image/jpeg"],
  [".jpeg", "image/jpeg"],
  [".gif", "image/gif"],
  [".webp", "image/webp"],
]);

export async function loadAttachments(files, workspace, processPiFiles) {
  const textFiles = [];
  const images = [];
  let text = "";
  for (const file of files || []) {
    const absolute = path.resolve(workspace, file);
    if (!fs.existsSync(absolute) || !fs.statSync(absolute).isFile()) throw new Error(`附件不存在或不是文件: ${absolute}`);
    const mimeType = IMAGE_TYPES.get(path.extname(absolute).toLowerCase());
    if (mimeType) {
      images.push({ type: "image", mimeType, data: fs.readFileSync(absolute).toString("base64") });
      text += `<file name="${absolute}"></file>\n`;
    } else {
      textFiles.push(absolute);
    }
  }
  if (textFiles.length) {
    if (processPiFiles) {
      const processed = await processPiFiles(textFiles);
      text += processed.text;
      images.push(...processed.images);
    } else {
      for (const file of textFiles) text += `<file name="${file}">\n${fs.readFileSync(file, "utf8")}\n</file>\n`;
    }
  }
  return { text, images };
}
