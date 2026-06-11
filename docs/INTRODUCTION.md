# CAD Translate CLI — 使用介绍

## 这是什么？

CAD Translate CLI 是一个命令行工具，帮你把 CAD 图纸（DWG/DXF）中的外文文字翻译成你需要的语言。

**典型场景**：你收到一份俄文/英文的施工图，需要翻译成中文（或反过来），手动改太慢，这个工具可以自动完成。

## 它能做什么？

```
DWG 图纸 → 提取文字 → AI 翻译 → 回填到图纸
```

四步搞定：
1. **转换**：把 DWG 转成 DXF（可编辑格式）
2. **提取**：把图纸里所有文字抓出来，存到 Excel 表格
3. **翻译**：用 AI 批量翻译 Excel 里的文字
4. **回填**：把翻译结果写回图纸，生成新文件

## 我需要准备什么？

| 需要 | 说明 |
|------|------|
| Python 3.10+ | 运行环境 |
| CAD 软件 或 ODA | 把 DWG 转成 DXF（见下方说明） |
| AI API 密钥 | 用来翻译文字（见下方说明） |

### CAD 软件（DWG 转换）

DWG 是 AutoCAD 的私有格式，需要借助工具转换：

- **AutoCAD**（推荐）— 如果你电脑上装了，工具会自动调用
- **浩辰 CAD / GStarCAD** — 国产替代，同样支持
- **ODA File Converter**（免费）— 从 [opendesign.com](https://www.opendesign.com/guestfiles/oda_file_converter) 下载安装
- **LibreDWG**（免费）— 已经捆绑在工具里，兼容性一般

如果不想装 CAD 软件，安装 ODA File Converter 就行，免费且够用。

### AI API 密钥

翻译需要调用大语言模型，你需要一个 API 密钥。支持的厂商：

| 厂商 | 注册地址 | 说明 |
|------|----------|------|
| DeepSeek | platform.deepseek.com | 国内直连，便宜 |
| 阿里百炼 | bailian.console.aliyun.com | 国内直连 |
| OpenRouter | openrouter.ai | 聚合平台，选择多 |
| 智谱 | open.bigmodel.cn | 国内直连 |
| MiniMax | api.minimax.chat | 国内直连 |
| OpenAI | platform.openai.com | 需要代理 |

拿到密钥后，运行 `cad-translate onboard` 按提示配置即可。

## 快速上手

```bash
# 1. 安装
pip install -r requirements.txt
pip install -e .

# 2. 配置（跟着提示走）
cad-translate onboard

# 3. 翻译一张图
cad-translate pipeline convert -i 图纸.dwg
cad-translate pipeline extract -i 输出/图纸.dxf
cad-translate pipeline translate-excel -i 输出/图纸_extracted_texts.xlsx --target-language zh
cad-translate pipeline apply -i 输出/图纸.dxf -e 输出/图纸_extracted_texts_translated.xlsx --translation-mode replace
```

翻译结果在 `输出/translated_图纸.dxf`，用 AutoCAD 或免费的 LibreCAD 打开即可。

## 常见问题

**Q: 翻译出来的文字位置不对？**
A: 回填模式用 `replace`（替换）最干净。`add` 模式会在原文下方追加译文，可能重叠。

**Q: 翻译质量不好？**
A: 试试换个更强的模型，比如 DeepSeek-V3 或 GPT-4o。配置时用 `--model` 指定。

**Q: 支持批量翻译多张图吗？**
A: 可以。把所有 DWG 放一个文件夹，对每个文件重复执行 4 步流程即可。

**Q: 不装 CAD 软件能用吗？**
A: 能。安装免费的 ODA File Converter 就行。或者如果你已经有 DXF 文件，直接从第 2 步开始。
