# Material

Each item below starts with its source id. The page as it stands is source `investigation:page`, and the coverage note is source `investigation:coverage`.

### investigation:coverage
7 messages the user typed in codex sessions in this project's folders, 2026-09-06 to 2026-09-21. The last activity is 2026-09-21. Only the user's own messages: no assistant replies, no tool output, no repository files.

### codex:sessions-mixed-language:1 · 2026-09-06 — user (codex, /Users/alex/code/menu-scan)
这个项目 menu-scan：把餐厅的纸质菜单拍照，OCR 出菜名和价格，导出成 spreadsheet，给 Lucky Dumpling 用。

### codex:sessions-mixed-language:2 · 2026-09-07 — user (codex, /Users/alex/code/menu-scan)
OCR 用 Tesseract，chi_sim + eng 两个语言包都要装。

### codex:sessions-mixed-language:3 · 2026-09-09 — user (codex, /Users/alex/code/menu-scan)
价格有时候识别成 1B.80，其实是 18.80。加一个 fix：B 在数字中间就当 8。

### codex:sessions-mixed-language:4 · 2026-09-11 — user (codex, /Users/alex/code/menu-scan)
Export 成 CSV 就行，老板用 Excel 打开。列：菜名、英文名、价格。

### codex:sessions-mixed-language:5 · 2026-09-15 — user (codex, /Users/alex/code/menu-scan)
测试了 3 张菜单，价格全部对了，菜名错了 2 个。

### codex:sessions-mixed-language:6 · 2026-09-18 — user (codex, /Users/alex/code/menu-scan)
下一步：菜名错的那两个，加一个 dictionary 手动纠正。

### codex:sessions-mixed-language:7 · 2026-09-21 — user (codex, /Users/alex/code/menu-scan)
Decided: 不做 app 了，就是一个 command line，老板让他儿子跑。
