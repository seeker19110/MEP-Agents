/**
 * Test giao diện Web App — chạy trên trình duyệt thật, gọi backend thật.
 *
 * Đây là mảng duy nhất của dự án trước đây KHÔNG có lớp kiểm thử nào: `web/` chỉ được
 * kiểm bằng mắt. Test ở đây đi đúng đường người dùng thật đi: mở trang → thả file bản vẽ
 * → bấm phân tích → chờ WebSocket báo xong → tải file Excel về.
 *
 * Cần backend đang chạy (redis + celery worker + uvicorn), xem `docs/E2E.md`.
 */
import { expect, test } from '@playwright/test';

/** Bản vẽ DXF tối giản nhưng HỢP LỆ, đủ để ezdxf đọc và bóc ra khối lượng thật. */
function minimalDxf() {
  const lines = [
    '0', 'SECTION', '2', 'HEADER',
    '9', '$ACADVER', '1', 'AC1015',
    '9', '$INSUNITS', '70', '4',
    '0', 'ENDSEC',
    '0', 'SECTION', '2', 'ENTITIES',
    '0', 'LINE', '8', 'P-CHW-SUPPLY',
    '10', '0.0', '20', '0.0', '30', '0.0',
    '11', '12000.0', '21', '0.0', '31', '0.0',
    '0', 'ENDSEC',
    '0', 'EOF',
  ];
  return lines.join('\n') + '\n';
}

/** Thả một file vào vùng kéo-thả (giao diện chỉ nghe sự kiện `drop`). */
async function dropFile(page, selector, name, content) {
  const dataTransfer = await page.evaluateHandle(
    ([fileName, fileContent]) => {
      const dt = new DataTransfer();
      dt.items.add(new File([fileContent], fileName, { type: 'application/dxf' }));
      return dt;
    },
    [name, content],
  );
  await page.dispatchEvent(selector, 'drop', { dataTransfer });
}

const DROP_ZONE = 'div.border-dashed';

test.describe('Web App — bóc khối lượng', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('trang tải được và hiện trạng thái chờ', async ({ page }) => {
    await expect(page.getByRole('heading', { name: 'MEP-Agents Cloud' })).toBeVisible();
    await expect(page.getByText('Auto Quantity Takeoff')).toBeVisible();
    await expect(page.getByText('Waiting for input...')).toBeVisible();
  });

  test('thả file .dxf thì hiện tên file và nút phân tích', async ({ page }) => {
    await dropFile(page, DROP_ZONE, 'tang1.dxf', minimalDxf());

    await expect(page.getByText('tang1.dxf')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Phân tích bản vẽ' })).toBeEnabled();
  });

  test('từ chối file không phải bản vẽ CAD', async ({ page }) => {
    await dropFile(page, DROP_ZONE, 'bao_gia.pdf', 'khong phai ban ve');

    await expect(page.getByText('bao_gia.pdf')).toBeHidden();
    await expect(page.getByText('Kéo thả file CAD vào đây')).toBeVisible();
  });

  test('trọn đường: thả file → phân tích → WebSocket báo xong → tải Excel', async ({ page }) => {
    await dropFile(page, DROP_ZONE, 'tang1.dxf', minimalDxf());
    await page.getByRole('button', { name: 'Phân tích bản vẽ' }).click();

    // Tải lên xong
    await expect(page.getByText('Tải lên thành công!')).toBeVisible();

    // WebSocket đẩy trạng thái về — đây là phần trước đây chưa test nào chạm tới
    await expect(page.getByText('Báo cáo BOQ đã hoàn tất')).toBeVisible({ timeout: 90_000 });
    await expect(page.getByText('✅ Hoàn tất! Bảng BOQ đã sẵn sàng.')).toBeVisible();

    // Tải file về thật
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Tải Excel' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/);
  });

  test('vùng kéo-thả mời "click để chọn file" thì phải mở được hộp chọn file', async ({ page }) => {
    /* Giao diện ghi rõ "hoặc click để chọn file". Người dùng trên máy tính bàn hay bấm
       vào vùng này thay vì kéo thả — nếu không có <input type="file"> thì cú bấm rơi vào
       hư không, không báo lỗi gì, và người dùng tưởng ứng dụng hỏng. */
    // Lời mời phải là NÚT thật, không phải chữ trang trí — bàn phím và trình đọc màn
    // hình mới dùng được.
    const nutChon = page.getByRole('button', { name: 'hoặc click để chọn file' });
    await expect(nutChon).toBeVisible();

    const fileChooserPromise = page.waitForEvent('filechooser', { timeout: 5_000 });
    await nutChon.click();
    expect(await fileChooserPromise).toBeTruthy();
  });
});

test.describe('Web App — chọn file bằng cách bấm', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
  });

  test('chọn file qua hộp thoại cũng nhận đúng như kéo thả', async ({ page }) => {
    // Bấm vào bất kỳ đâu trong vùng kéo-thả cũng mở được hộp chọn file.
    const fileChooserPromise = page.waitForEvent('filechooser');
    await page.locator(DROP_ZONE).click();
    const chooser = await fileChooserPromise;

    await chooser.setFiles({
      name: 'chon_tay.dxf',
      mimeType: 'application/dxf',
      buffer: Buffer.from(minimalDxf()),
    });

    await expect(page.getByText('chon_tay.dxf')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Phân tích bản vẽ' })).toBeEnabled();
  });

  test('bấm nút Phân tích không mở nhầm hộp chọn file', async ({ page }) => {
    /* Nút nằm TRONG vùng kéo-thả vừa được gắn onClick — không chặn nổi bọt thì mỗi lần
       bấm "Phân tích bản vẽ" sẽ bật thêm hộp chọn file đè lên. */
    await dropFile(page, DROP_ZONE, 'tang1.dxf', minimalDxf());

    let chooserOpened = false;
    page.on('filechooser', () => { chooserOpened = true; });
    await page.getByRole('button', { name: 'Phân tích bản vẽ' }).click();
    await page.waitForTimeout(1000);

    expect(chooserOpened).toBe(false);
  });
});
