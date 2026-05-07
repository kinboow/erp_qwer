const fs = require('fs');
const path = require('path');
const PdfPrinter = require('pdfmake');

// 1mm = 2.834645669291339pt
const mm = (v) => v * 2.834645669291339;

// ── 常量 ──
const PAGE_W = mm(297);
const PAGE_H = mm(210);
const MARGIN_L = mm(15);
const MARGIN_R = mm(15);
const MARGIN_T = mm(12);
const MARGIN_B = mm(14);
const CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R;
const GRIDCODE_SIZE = mm(30);  // GridCode 方块码尺寸（正方形）

const HEADER_ROW_H = mm(9);
const DATA_ROW_H = mm(7);

// 第一页：标题(~12mm) + 信息区(~24mm) + 表头
const FIRST_PAGE_TABLE_BODY_H = PAGE_H - MARGIN_T - MARGIN_B - mm(12) - mm(24) - HEADER_ROW_H;
// 后续页：标题(~12mm) + 间距(~6mm) + 表头
const OTHER_PAGE_TABLE_BODY_H = PAGE_H - MARGIN_T - MARGIN_B - mm(12) - mm(6) - HEADER_ROW_H;

// ── stdin ──
function readStdin() {
  return new Promise((resolve, reject) => {
    const chunks = [];
    process.stdin.on('data', (c) => chunks.push(c));
    process.stdin.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    process.stdin.on('error', reject);
  });
}

// ── 字体（全局强制：等线） ──
function resolveFonts() {
  const windir = process.env.WINDIR || 'C:\\Windows';
  const dengNormal = path.join(windir, 'Fonts', 'Deng.ttf');
  const dengBold   = path.join(windir, 'Fonts', 'Dengb.ttf');
  if (!fs.existsSync(dengNormal)) {
    throw new Error('未找到等线字体: C:/Windows/Fonts/Deng.ttf');
  }
  return {
    normal: dengNormal,
    bold: fs.existsSync(dengBold) ? dengBold : dengNormal,
    italics: dengNormal,
    bolditalics: fs.existsSync(dengBold) ? dengBold : dengNormal,
  };
}

// ── 列宽（固定值） ──
const CELL_PAD = 0; // 设为 0，避免列宽被 padding 额外撑大
const PNO_W = mm(20);        // 款号 2cm
const COLOR_W = mm(25);      // 颜色 2.5cm
const SIZE_SUB_W = mm(16); // 尺码每小列 1.65cm
const TABLE_LINE_W = 0.5;

function calcTableOuterWidth(widths) {
  const contentW = widths.reduce((sum, w) => sum + w, 0);
  return contentW + TABLE_LINE_W * (widths.length + 1);
}

function buildWidths(nSizes) {
  const widths = [PNO_W, COLOR_W];
  for (let i = 0; i < nSizes; i++) {
    widths.push(SIZE_SUB_W, SIZE_SUB_W);
  }

  const maxOuterW = CONTENT_W;
  const outerW = calcTableOuterWidth(widths);
  if (outerW > maxOuterW) {
    const overflow = outerW - maxOuterW;
    const sizeCols = Math.max(nSizes * 2, 1);
    const reduceEach = overflow / sizeCols;
    for (let i = 2; i < widths.length; i++) {
      widths[i] = Math.max(widths[i] - reduceEach, mm(10));
    }
  }

  return widths;
}

// ── 客户信息区 ──
function buildInfoBlock(order) {
  const infoRowGap = mm(1.5) + 3;
  const col1W = CONTENT_W * 0.32;
  const col2W = CONTENT_W * 0.28;
  const rows = [];
  rows.push({
    columns: [
      {
        width: col1W,
        text: [
          { text: '单号：', bold: true },
          { text: `${order.order_no || ''}` },
        ],
      },
      {
        width: col2W,
        text: [
          { text: '制单人：', bold: true },
          { text: `${order.creator || ''}` },
        ],
      },
      { width: '*', text: '' },
    ],
    margin: [0, 0, 0, infoRowGap],
  });
  rows.push({
    columns: [
      {
        width: col1W,
        text: [
          { text: '订单日期：', bold: true },
          { text: `${order.order_date || ''}` },
        ],
      },
      {
        width: col2W,
        text: [
          { text: '客户：', bold: true },
          { text: `${order.customer_name || ''}` },
        ],
      },
      {
        width: '*',
        text: [
          { text: '客户电话：', bold: true },
          { text: `${order.customer_tel || ''}` },
        ],
      },
    ],
    margin: [0, 0, 0, infoRowGap],
  });
  if (order.customer_addr) {
    rows.push({
      text: [
        { text: '客户地址：', bold: true },
        { text: `${order.customer_addr}` },
      ],
      margin: [0, 0, 0, infoRowGap],
    });
  }
  rows.push({
    text: [
      { text: '备注：', bold: true },
      { text: `${order.remark || '无'}` },
    ],
    margin: [0, 0, 0, infoRowGap],
  });
  return rows;
}

function calcPageTotalQty(page) {
  let total = 0;
  for (const blk of (page.blocks || [])) {
    for (const cr of (blk.color_rows || [])) {
      const qtyMap = cr.qty_map || {};
      for (const v of Object.values(qtyMap)) {
        const n = Number(v) || 0;
        total += n;
      }
    }
  }
  return total;
}

function calcDocumentTotalQty(payload) {
  let total = 0;
  for (const page of (payload.pages || [])) {
    total += calcPageTotalQty(page);
  }
  return total;
}

// ── 表格 ──
function buildTable(page, payload) {
  const nSizes = payload.all_sizes.length;
  const nCols = 2 + nSizes * 2;
  const widths = buildWidths(nSizes);

  // 表头行
  const header = [
    { text: '款号', style: 'th' },
    { text: '颜色', style: 'th' },
  ];
  for (const sz of payload.all_sizes) {
    header.push({ text: sz, style: 'th', colSpan: 2 });
    header.push({ text: '' }); // colSpan 占位
  }

  const body = [header];

  // 记录每个款号组的起始行（1-based，因为 0 是表头）
  const groupBoundaries = new Set();
  let rowIdx = 1;

  for (const blk of page.blocks) {
    const nRows = blk.color_rows.length;
    groupBoundaries.add(rowIdx); // 组首行
    for (let ci = 0; ci < nRows; ci++) {
      const cr = blk.color_rows[ci];
      const row = [];
      // 款号列：首行 rowSpan 合并
      if (ci === 0) {
        row.push({ text: blk.product_no || '', rowSpan: nRows, style: 'tdKey', alignment: 'center', valign: 'middle' });
      } else {
        row.push({ text: '', style: 'tdKey', valign: 'middle' });
      }
      // 颜色
      row.push({ text: cr.color || '', style: 'tdKey', alignment: 'center', valign: 'middle' });
      // 尺码数量 + 空白
      for (const sz of payload.all_sizes) {
        const qty = (cr.qty_map && cr.qty_map[sz] != null) ? String(cr.qty_map[sz]) : '0';
        row.push({
          text: qty,
          style: 'tdQty',
          alignment: 'center',
          fillColor: qty !== '' ? '#e6e6e6' : null,
        });
        row.push({ text: '', style: 'td' });
      }
      body.push(row);
      rowIdx++;
    }
  }

  // 判断某行是否是组分隔线位置
  const isGroupBorder = (lineIdx) => groupBoundaries.has(lineIdx);

  return {
    table: {
      headerRows: 1,
      widths,
      body,
      heights: (ri) => (ri === 0 ? HEADER_ROW_H : DATA_ROW_H),
      dontBreakRows: true,
      keepWithHeaderRows: 1,
    },
    layout: {
      hLineWidth: () => 0.5,
      vLineWidth: () => 0.5,
      hLineColor: () => '#000000',
      vLineColor: () => '#000000',
      paddingLeft: () => CELL_PAD,
      paddingRight: () => CELL_PAD,
      paddingTop: () => 0,
      paddingBottom: () => 0,
      fillColor: () => null,
    },
    _outerWidth: calcTableOuterWidth(widths),
    margin: [0, 0, 0, 0],
  };
}

// ── 文档 ──
function buildDocument(payload) {
  const content = [];
  const totalPages = payload.pages.length;
  const docTotalQty = calcDocumentTotalQty(payload);

  payload.pages.forEach((page, pi) => {
    // 标题行：左侧空白平衡 + 居中标题 + 右侧 GridCode 方块码
    // 非首页通过 pageBreak:'before' 强制分到新一页
    content.push({
      columns: [
        { width: GRIDCODE_SIZE, text: '' },
        {
          width: '*',
          text: payload.title || '韩酷服饰-拣货单',
          fontSize: 20,
          bold: true,
          alignment: 'center',
        },
        page.gridcode_data_url
          ? {
              width: GRIDCODE_SIZE,
              stack: [
                { image: page.gridcode_data_url, fit: [GRIDCODE_SIZE, GRIDCODE_SIZE], alignment: 'right' },
                {
                  text: page.barcode_content || '',
                  width: GRIDCODE_SIZE,
                  alignment: 'center',
                  fontSize: 9.5,
                  bold: true,
                  margin: [0, mm(1.2), 0, 0],
                },
              ],
            }
          : { width: GRIDCODE_SIZE, text: '' },
      ],
      margin: [0, pi > 0 ? 25 : 0, 0, mm(3)],
      pageBreak: pi > 0 ? 'before' : undefined,
    });
    // 信息区（仅首页）
    if (pi === 0) {
      content.push({
        stack: buildInfoBlock(payload.order),
        fontSize: 11.5,
        margin: [0, -20, 0, mm(2)],
      });
    } else {
      content.push({ text: '', margin: [0, mm(3) - 15, 0, mm(1)] });
    }
    // 表格（X 轴居中）
    const tableNode = buildTable(page, payload);
    const leftOffset = Math.max((CONTENT_W - (tableNode._outerWidth || CONTENT_W)) / 2, 0);
    tableNode.margin = [leftOffset, 0, 0, 0];
    content.push(tableNode);
    if (pi === totalPages - 1) {
      content.push({
        text: `总计：${docTotalQty} 件`,
        alignment: 'right',
        bold: true,
        fontSize: 11,
        margin: [0, mm(3), 0, 0],
      });
    }
  });

  return {
    pageSize: 'A4',
    pageOrientation: 'landscape',
    pageMargins: [MARGIN_L, MARGIN_T, MARGIN_R, MARGIN_B],
    content,
    defaultStyle: {
      font: 'ChineseFont',
      fontSize: 9,
      lineHeight: 1,
    },
    styles: {
      th:     { alignment: 'center', bold: true, fontSize: 12.5, lineHeight: 1, margin: [0, 6.5, 0, 0] },
      td:     { alignment: 'center', fontSize: 9, lineHeight: 1, margin: [0, 3.5, 0, 0] },
      tdQty:  { alignment: 'center', fontSize: 11.5, lineHeight: 1, margin: [0, 4.2, 0, 0] },
      tdKey:  { alignment: 'center', valign: 'middle', fontSize: 11, bold: true, lineHeight: 1, margin: [0, 3.5, 0, 0] },
      tdBold: { alignment: 'center', fontSize: 9, bold: true, lineHeight: 1, margin: [0, 3.5, 0, 0] },
    },
    footer(currentPage, pageCount) {
      return {
        text: `${currentPage} / ${pageCount}`,
        alignment: 'center',
        font: 'ChineseFont',
        fontSize: 9,
        margin: [0, 0, 0, 0],
      };
    },
  };
}

// ── main ──
async function main() {
  const raw = await readStdin();
  const payload = JSON.parse(raw);
  const fonts = resolveFonts();
  const printer = new PdfPrinter({
    ChineseFont: fonts,
  });
  const doc = printer.createPdfKitDocument(buildDocument(payload));
  const chunks = [];
  doc.on('data', (c) => chunks.push(c));
  doc.on('end', () => process.stdout.write(Buffer.concat(chunks)));
  doc.on('error', (e) => { console.error(e); process.exit(1); });
  doc.end();
}

main().catch((e) => { console.error(e); process.exit(1); });
