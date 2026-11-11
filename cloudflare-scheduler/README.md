# MovieNotice 外部週檢排程器

此 Cloudflare Worker 於台灣時間每週三、週六 06:37 呼叫 GitHub
`workflow_dispatch`，啟動 `Weekly Atmovies Audit`。Cloudflare Cron 使用 UTC，
因此排程為 `37 22 * * TUE,FRI`。

GitHub 內建的週檢 `schedule` 已移除，避免 GitHub 延遲數小時後又重複執行。
原有 Watchdog 保留為台灣時間 13:07、15:07 的下午備援；它會先確認當日
Google Sheet 完整稽核標記，只有尚未完成時才補跑。

## 首次設定

1. 在 GitHub 建立 Fine-grained personal access token：
   - Repository access：只選 `kaxisch/movienotice`
   - Repository permissions：`Actions` 設為 `Read and write`
   - 設定到期日並記錄日後更新時間
2. 登入 Cloudflare：

   ```bash
   cd cloudflare-scheduler
   npx wrangler login
   ```

3. 部署 Worker：

   ```bash
   npx wrangler deploy
   ```

4. 將 GitHub token 存入 Cloudflare Secret。依提示貼上 token；不要寫入檔案：

   ```bash
   npx wrangler secret put GITHUB_TOKEN
   ```

5. 再部署一次，確認 Cron Trigger 與最新 Worker 版本一致：

   ```bash
   npx wrangler deploy
   ```

## 驗證

在 Cloudflare Dashboard 開啟：

`Workers & Pages` → `movienotice-weekly-audit-scheduler` → `Settings` →
`Triggers`，確認 Cron 為 `37 22 * * TUE,FRI`。

可在 `Triggers` 的 Cron 測試介面按 `Trigger` 做一次測試。測試後到 GitHub
Actions 確認 `Weekly Atmovies Audit` 出現 `workflow_dispatch` 執行紀錄。

## Token 更新

Token 到期或撤銷後，重新建立 token，再執行：

```bash
cd cloudflare-scheduler
npx wrangler secret put GITHUB_TOKEN
```

程式碼與 Git repository 不應包含 token；Secret 只保存在 Cloudflare。
