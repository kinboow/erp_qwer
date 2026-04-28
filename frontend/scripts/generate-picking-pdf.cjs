const fs = require('fs');
const path = require('path');
const PdfPrinter = require('pdfmake');

const mm = (value) => value * 2.834645669291339;

function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (chunk) => chunks.push(chunk));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    process.stdin.on('error', reject);
  });
}

function resolveFontPath() {
  const windir = process.env.WINDIR || 'C:\\Windows';
  const candidates = [
    path.join(windir, 'Fonts', 'simhei.ttf'),
    path.join(windir, 'Fonts', 'simkai.ttf'),
    path.join(windir, 'Fonts', 'simfang.ttf'),
    path.join(windir, 'Fonts', 'simsun.ttc'),
    path.join(windir, 'Fonts', 'msyh.ttc'),
  ];
  const fontPath = candidates.find((item) => fs.existsSync(item));
  if (!fontPath) {
    throw new Error('未找到可用中文字体');
  }
  return fontPath;
}

function buildWidths(allSizes) {
  const pageWidth = mm(297);
  const contentWidth = pageWidth - mm(12) - mm(12);
  const productWidth = mm(18);
  const colorWidth = mm(18);
  const pairWidth = (contentWidth - productWidth - colorWidth) / Math.max(allSizes.length, 1);
  const qtyWidth = pairWidth * 0.55;
  const blankWidth = pairWidth * 0.45;
  const widths = [productWidth, colorWidth];
  for (const _size of allSizes) {
    widths.push(qtyWidth);
    widths.push(blankWidth);
  }
  return widths;
}

function buildInfo(order) {
  const blocks = [];
  const contentWidth = mm(297) - mm(12) - mm(12);
  blocks.push({
    columns: [
      { width: contentWidth * 0.35, text: `单号：${order.order_no || ''}` },
      { width: contentWidth * 0.35, text: `制单人：${order.creator || ''}` },
      { width: '*', text: '' }
    ],
    margin: [0, 0, 0, mm(1.2)],
  });
  blocks.push({
    columns: [
      { width: contentWidth * 0.35, text: `订单日期：${order.order_date || ''}` },
      { width: contentWidth * 0.35, text: `客户：${order.customer_name || ''}` },
      { width: '*', text: `客户电话：${order.customer_tel || ''}` }
    ],
    margin: [0, 0, 0, mm(1.2)],
  });
  if (order.customer_addr) {
    blocks.push({ text: `客户地址：${order.customer_addr}`, margin: [0, 0, 0, mm(1.2)] });
  }
  if (order.remark) {
    blocks.push({ text: `备注：${order.remark}`, margin: [0, 0, 0, mm(1.2)] });
  }
  return blocks;
}

function buildTable(page, payload) {
  const body = [];
  const header = [
    { text: '款号', style: 'th' },
    { text: '颜色', style: 'th' },
  ];
  for (const size of payload.all_sizes) {
    header.push({ text: size, style: 'th' });
    header.push({ text: '', style: 'th' });
  }
  body.push(header);

  const groupSpans = []; // [{startRow: 1, count: 2}]
  let currentRowIndex = 1;
  page.blocks.forEach((block, blockIndex) => {
    const nRows = block.color_rows.length;
    groupSpans.push({ startRow: currentRowIndex, count: nRows });
    
    block.color_rows.forEach((colorRow, colorIndex) => {
      const row = [
        { text: colorIndex === 0 ? (block.product_no || '') : '', rowSpan: colorIndex === 0 ? nRows : 1, style: 'tdCenter' },
        { text: colorRow.color || '', style: 'tdCenter' },
      ];
      for (const size of payload.all_sizes) {
        const qty = colorRow.qty_map && colorRow.qty_map[size] ? String(colorRow.qty_map[size]) : '';
        row.push({ text: qty, style: 'qty' });
        row.push({ text: '', style: 'blank' });
      }
      body.push(row);
      currentRowIndex += 1;
    });
  });

  const availableBodyHeight = page.show_info ? mm(145) : mm(165); 
  const rowHeight = mm(6.5);
  const usedHeight = currentRowIndex * rowHeight;
  if (usedHeight < availableBodyHeight) {
    const emptyRows = Math.floor((availableBodyHeight - usedHeight) / rowHeight);
    for (let i = 0; i < emptyRows; i++) {
      const row = [{ text: '', style: 'tdCenter' }, { text: '', style: 'tdCenter' }];
      for (const size of payload.all_sizes) {
        row.push({ text: '', style: 'qty' }, { text: '', style: 'blank' });
      }
      body.push(row);
      currentRowIndex += 1;
    }
  }

  const isGroupStartRow = (rowIndex) => groupSpans.some(g => g.startRow === rowIndex);

  return {
    table: {
      headerRows: 1,
      widths: buildWidths(payload.all_sizes),
      body,
      heights: (rowIndex) => (rowIndex === 0 ? mm(8) : rowHeight),
    },
    layout: {
      hLineWidth: (i, node) => {
        if (i === 0 || i === 1 || i === node.table.body.length) {
          return 1.0;
        }
        return isGroupStartRow(i) ? 1.0 : 0.5;
      },
      vLineWidth: (i, node) => {
        if (i === 0 || i === node.table.widths.length) {
          return 1.0;
        }
        return 0.5;
      },
      hLineColor: (i, node) => {
        if (i === 0 || i === 1 || i === node.table.body.length || isGroupStartRow(i)) {
          return '#000000';
        }
        return '#888888';
      },
      vLineColor: (i, node) => {
         if (i === 0 || i === node.table.widths.length) {
            return '#000000';
         }
         return '#888888';
      },
      paddingLeft: () => 4,
      paddingRight: () => 4,
      paddingTop: () => 3,
      paddingBottom: () => 3,
      fillColor: (rowIndex, columnIndex) => {
        if (rowIndex === 0) {
          return null;
        }
        if (columnIndex >= 2 && columnIndex % 2 === 0) {
          return '#ececec';
        }
        return null;
      },
    },
    margin: [0, 0, 0, 0],
  };
}

function buildDocument(payload) {
  const content = [];
  const qrWidth = mm(20);
  payload.pages.forEach((page, pageIndex) => {
    content.push({
      image: page.qr_data_url,
      width: qrWidth,
      absolutePosition: { x: mm(297) - mm(12) - qrWidth, y: mm(10) },
    });
    content.push({
      text: payload.title || '韩酷服饰-拣货单',
      fontSize: 18,
      bold: true,
      alignment: 'center',
      margin: [0, mm(2), 0, mm(2)],
    });
    if (page.show_info) {
      content.push({ stack: buildInfo(payload.order), fontSize: 9.5, margin: [0, mm(4), 0, mm(2)] });
    } else {
      content.push({ text: '', margin: [0, mm(8), 0, 0] });
    }
    content.push(buildTable(page, payload));
    if (pageIndex < payload.pages.length - 1) {
      content.push({ text: '', pageBreak: 'after' });
    }
  });

  return {
    pageSize: 'A4',
    pageOrientation: 'landscape',
    pageMargins: [mm(12), mm(10), mm(12), mm(10)],
    content,
    defaultStyle: {
      font: 'ChineseFont',
      fontSize: 9,
      lineHeight: 1.1,
    },
    styles: {
      th: { alignment: 'center', bold: true, fontSize: 10 },
      tdCenter: { alignment: 'center', margin: [0, 2, 0, 0] },
      qty: { alignment: 'center', margin: [0, 2, 0, 0] },
      blank: { alignment: 'center' },
    },
    footer(currentPage, pageCount) {
      return {
        text: `${currentPage} / ${pageCount}`,
        alignment: 'center',
        font: 'ChineseFont',
        fontSize: 9,
        margin: [0, 0, 0, 6],
      };
    },
  };
}

async function main() {
  const raw = await readStdin();
  const payload = JSON.parse(raw);
  const fontPath = resolveFontPath();
  const printer = new PdfPrinter({
    ChineseFont: {
      normal: fontPath,
      bold: fontPath,
      italics: fontPath,
      bolditalics: fontPath,
    },
  });
  const docDefinition = buildDocument(payload);
  const pdfDoc = printer.createPdfKitDocument(docDefinition);
  const chunks = [];
  pdfDoc.on('data', (chunk) => chunks.push(chunk));
  pdfDoc.on('end', () => {
    process.stdout.write(Buffer.concat(chunks));
  });
  pdfDoc.on('error', (error) => {
    console.error(error);
    process.exit(1);
  });
  pdfDoc.end();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
