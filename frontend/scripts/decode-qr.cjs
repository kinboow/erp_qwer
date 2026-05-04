/**
 * Node.js QR 解码脚本
 * 用法: node decode-qr.cjs <image_path>
 * 
 * 读取图片 → sharp 转灰度 RGBA → jsQR 解码
 * 输出 JSON: { "texts": ["decoded_text", ...] }
 * 
 * 也支持 stdin 传入图片字节：
 *   cat image.jpg | node decode-qr.cjs --stdin
 */

const jsQR = require('jsqr');
const sharp = require('sharp');
const fs = require('fs');
const path = require('path');

async function decodeFromBuffer(buf) {
  const results = [];

  // 策略：多种预处理变体
  const variants = [
    { name: 'raw', fn: (s) => s },
    { name: 'sharpen', fn: (s) => s.sharpen({ sigma: 2 }) },
    { name: 'normalize', fn: (s) => s.normalize() },
    { name: 'sharp+norm', fn: (s) => s.sharpen({ sigma: 2 }).normalize() },
    { name: 'clahe', fn: (s) => s.clahe({ width: 8, height: 8 }) },
    { name: 'clahe+sharp', fn: (s) => s.clahe({ width: 8, height: 8 }).sharpen({ sigma: 2 }) },
    { name: 'threshold', fn: (s) => s.threshold(128) },
    { name: 'median', fn: (s) => s.median(3) },
    { name: 'median+sharp', fn: (s) => s.median(3).sharpen({ sigma: 2 }) },
  ];

  // 先尝试全图
  for (const v of variants) {
    try {
      const img = v.fn(sharp(buf).grayscale().toColorspace('b-w'));
      const { data, info } = await img.ensureAlpha().raw().toBuffer({ resolveWithObject: true });
      const code = jsQR(new Uint8ClampedArray(data), info.width, info.height, { inversionAttempts: 'attemptBoth' });
      if (code && code.data) {
        results.push(code.data);
        return results; // 成功即返回
      }
    } catch (e) { /* skip */ }
  }

  // 全图失败 → 尝试角落裁切
  const meta = await sharp(buf).metadata();
  const w = meta.width, h = meta.height;

  const corners = [
    { name: 'br', left: Math.floor(w * 0.55), top: Math.floor(h * 0.55), width: w - Math.floor(w * 0.55), height: h - Math.floor(h * 0.55) },
    { name: 'tr', left: Math.floor(w * 0.55), top: 0, width: w - Math.floor(w * 0.55), height: Math.floor(h * 0.45) },
    { name: 'bl', left: 0, top: Math.floor(h * 0.55), width: Math.floor(w * 0.45), height: h - Math.floor(h * 0.55) },
    { name: 'tl', left: 0, top: 0, width: Math.floor(w * 0.45), height: Math.floor(h * 0.45) },
  ];

  for (const corner of corners) {
    for (const scale of [1, 2, 3, 4]) {
      for (const v of variants) {
        try {
          let pipe = sharp(buf).extract(corner);
          if (scale > 1) {
            pipe = pipe.resize(corner.width * scale, corner.height * scale, { kernel: 'lanczos3' });
          }
          pipe = v.fn(pipe.grayscale().toColorspace('b-w'));

          // 加白边
          const intermediate = await pipe.toBuffer();
          const bordered = await sharp(intermediate)
            .extend({ top: 40, bottom: 40, left: 40, right: 40, background: { r: 255, g: 255, b: 255, alpha: 1 } })
            .ensureAlpha()
            .raw()
            .toBuffer({ resolveWithObject: true });

          const code = jsQR(
            new Uint8ClampedArray(bordered.data),
            bordered.info.width,
            bordered.info.height,
            { inversionAttempts: 'attemptBoth' },
          );
          if (code && code.data) {
            results.push(code.data);
            return results;
          }
        } catch (e) { /* skip */ }
      }
    }
  }

  return results;
}

async function main() {
  let buf;
  const args = process.argv.slice(2);

  if (args.includes('--stdin')) {
    // 从 stdin 读取
    const chunks = [];
    for await (const chunk of process.stdin) {
      chunks.push(chunk);
    }
    buf = Buffer.concat(chunks);
  } else if (args.length > 0 && !args[0].startsWith('-')) {
    buf = fs.readFileSync(args[0]);
  } else {
    console.error('Usage: node decode-qr.cjs <image_path> | node decode-qr.cjs --stdin');
    process.exit(1);
  }

  const texts = await decodeFromBuffer(buf);
  process.stdout.write(JSON.stringify({ texts }));
}

main().catch((err) => {
  console.error(err.message);
  process.exit(1);
});
