# Demo 影片：3 分鐘講稿＋分鏡（英文旁白）

評分：Impact 30%、Use of Meta AI Tooling 25%、Technical Depth 20%、**Demo 25%**（「Is the demo video genuinely cool to watch? Does the product hold up live?」）

## 評審 3 分鐘要看到的亮點（依序）

1. **決策鏈節點圖即時亮起**：研究員 → 方案 → 5 位大師 → 魔鬼代言人 → 風控 → 決策；每個節點都是一次真的 Muse Spark 呼叫
2. **程式否決模型**：A、B 方案變紅「VETO · 94% in 1 fund」：模型可以辯論，但說服不了程式
3. **API 全紀錄**：右側即時列出每次呼叫（模型、秒數、token、推理 token）；點節點展開「Exact API request & response」原文
4. **Meta API 優勢用數字證明**：同一把 key 9 個模型、OpenAI 相容、推理 token 96%、平行 3.1× 加速
5. **一句話翻轉決策**：輸入「dentist bill 9,000 due on the 9th」→ Muse Spark 解析成帳單 → 現金流重算 → 本月改為不投資

## 素材

- 錄影：`python -m finagent.web`（另一視窗）＋ `python scripts/record_demo.py` → `out/video/*.webm`（無聲，1600×900）
- 封面／結尾：`docs/slides/` 的封面、Meta、結尾頁
- 剪輯：剪映／CapCut／Clipchamp（Windows 內建）；把等待模型的空檔加速 2–4×，總長 ≤ 3:00
- 旁白：照下面念，或用 CapCut「文字轉語音」

## 分鏡＋旁白

| 時間 | 畫面 | 旁白（英文，照念） |
|---|---|---|
| 0:00–0:12 | 簡報封面 | Hi, I’m Ming-An, a grad student in Taiwan. This is Paycheck Committee: a finance agent for people who live paycheck to paycheck. Bills first — then a committee of Muse Spark agents debates the rest. |
| 0:12–0:20 | 簡報架構頁（5） | Every agent here is a live call to Muse Spark through the Meta Model API. The money math and the risk rules are plain, tested code. |
| 0:20–0:45 | 錄影第一幕：Short On Cash 按 Run；現金流圖掉進紅區，Cash engine 節點變紅「bills first: invest 0」 | First, a user whose card bill and rent land before payday. The engine simulates every day: they hit minus ten thousand six hundred on November 12th. It tells them to move nine thousand from the emergency fund — and the committee gets zero to invest. Bills always come first. |
| 0:45–1:25 | 第二幕：Student 按 Run；節點一個個亮起，右側 API 呼叫一筆筆跳出 | Now a student who can invest eight thousand seven hundred. Watch the decision chain. Four researcher agents read the market data in parallel — each one is a Muse Spark call, and they may only cite numbers we gave them. Then five investor personas — Buffett, Lynch, Bogle, Dalio and Kostolany — score three proposals, also in parallel. On the right you see every call live: model, latency, tokens — and ninety-six percent are reasoning tokens. Muse Spark is actually thinking. |
| 1:25–1:50 | 魔鬼代言人亮起 → 風控：A、B 變紅 VETO，C 綠色 APPROVED | The devil’s advocate attacks the leading plan and states what would prove it wrong. Then the risk officer — which is code, not an LLM — vetoes A and B: they would put seventy to ninety percent of the portfolio in a single fund. The models can argue. They can’t argue past the rules. |
| 1:50–2:15 | 點 A（否決原因）→ 點 Risk → 點 Devil → 展開「Exact API request & response」捲動 | Every node is auditable. Click it and you see the exact prompt we sent to the Meta Model API and the exact JSON that came back. Every run is saved as a trace file, so next month we can check who was right. |
| 2:15–2:45 | 第三幕：打字「dentist bill 9,000 due on the 9th」→ Add → 重跑；可投資金額變 0 | Life changes. I type one sentence: a dentist bill of nine thousand on the 9th. Muse Spark turns it into a structured bill, the whole plan reruns, and this month’s investment drops to zero — the committee is told to sit this one out. |
| 2:45–3:00 | 錄影最後的統計卡（calls / tokens / 3.1× speed-up）→ 簡報結尾頁 | One key, nine Meta models, an OpenAI-compatible API, and parallel calls that run the whole meeting in under a minute. Paycheck Committee: bills first, then a debate, then a veto. It’s open source — thanks for watching. |

## 中文對照（自己理解用）

- 0:00 自我介紹；帳單優先，剩下的交給 Muse Spark 委員會
- 0:12 每個 agent 都是真的 Meta API 呼叫；金額與規則是有測試的程式
- 0:20 缺錢人設：11/12 最低 −10,600，建議從預備金搬 9,000，委員會拿到 0
- 0:45 學生人設：研究員平行讀數據（只能引用給的數字）、5 位大師平行打分；右側即時看每次呼叫，96% 是推理 token
- 1:25 魔鬼代言人攻擊領先方案；風控（程式不是 LLM）否決 A、B（單一基金 70–90%）。模型能辯論，但辯不過規則
- 1:50 每個節點可稽核：看到送出的 prompt 與回傳 JSON；每次都存 trace 檔
- 2:15 打一句「牙醫 9,000 九號繳」→ Muse Spark 解析 → 全部重算 → 本月不投資
- 2:45 一把 key 9 個模型、OpenAI 相容、平行一分鐘內開完會；開源

## 數字出處

全部來自真實執行（muse-spark-1.3）：`examples/real_run/`。人設與市場價格都是假資料。若重錄後數字不同（模型每次打分可能不同），以畫面為準改旁白。
