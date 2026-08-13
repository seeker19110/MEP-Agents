import { defineConfig, devices } from '@playwright/test';

/**
 * Test giao diện Web App.
 *
 * Chạy trên bản BUILD tĩnh (`npm run build` → `vite preview`) chứ không phải dev server:
 * đó mới là thứ thật sự được đóng gói vào container `web` trong docker-compose. Biến
 * `VITE_*` là build-time nên dev server và bản build có thể khác nhau ở đúng chỗ này.
 *
 * Cần một backend đang chạy ở `E2E_API_BASE` (mặc định http://127.0.0.1:8083).
 * Xem docs/E2E.md để dựng: redis + celery worker + uvicorn.
 *
 * Chạy ở cổng 5173 — trùng với danh sách origin mà API cho phép sẵn
 * (`_CORS_ORIGINS` trong `src/api.py`). Đổi sang cổng khác mà quên mở CORS thì trình
 * duyệt chặn phản hồi TRONG KHI server vẫn xử lý xong xuôi: người dùng thấy "Lỗi tải
 * lên" còn worker thì đã chạy hết cả tác vụ.
 */
const API_BASE = process.env.E2E_API_BASE || 'http://127.0.0.1:8083';

export default defineConfig({
  testDir: './tests-ui',
  timeout: 120_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
    ...devices['Desktop Chrome'],
    // Chromium đã cài sẵn trong môi trường này. Trỏ thẳng vào bản có sẵn thay vì để
    // Playwright tải bản riêng: phiên bản @playwright/test và bản trình duyệt cài sẵn
    // không nhất thiết khớp nhau, mà tải thêm thì cần mạng và vài trăm MB.
    // Đặt CHROMIUM_PATH để trỏ chỗ khác.
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH || '/opt/pw-browsers/chromium-1194/chrome-linux/chrome',
      args: ['--no-sandbox'],
    },
  },
  webServer: {
    command: `VITE_API_BASE=${API_BASE} npm run build && npm run preview -- --port 5173 --host 127.0.0.1`,
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 180_000,
  },
});
