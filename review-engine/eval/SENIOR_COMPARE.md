# Senior comparison — <repo> @ <base>..<head>

> 對齊北極星：先由資深工程師獨立寫下「我會提出的風險」，再跟引擎輸出比對兩個方向。

## A) 資深工程師會提出的風險（先寫，別偷看引擎輸出）
- [ ] (severity) file:line — 描述
- ...

## B) 引擎輸出（貼上 run_ab.py 的 BLAST-RADIUS 段）
...

## C) 比對
- **不漏 (recall)**：A 有、引擎也抓到 ___ / ___ 條（blocker/major 要逼近全中）
  - 漏掉的：（是 context 不夠？還是被 verify 誤殺？）
- **不吵 (precision)**：引擎提的，資深認同「值得提」___ / ___ 條（目標 FP < 10%）
  - 其中「聽起來合理、源碼一讀就垮」(diff-myopia) ___ 條
- **深度佐證**：引擎抓到、DIFF-ONLY baseline 漏掉的跨檔/影響風險 ___ 條

## D) 判定（Phase 1 Go/No-Go）
- [ ] 資深能說「這些我都認同，而且我會抓的它沒漏」→ 可完全信任 → **GO**
- [ ] 否 → 記錄主要失效模式，回 §9 風險調整
