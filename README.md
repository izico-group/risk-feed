# risk-feed

جمع‌آورنده خودکار داده برای «اتاق پایش ریسک منطقه». هر ۵ دقیقه روی GitHub Actions اجرا می‌شود و نتیجه را در `data/feed.json` و `data/alerts.json` می‌نویسد.

| منبع | فایل تنظیم |
|---|---|
| هواپیماهای نظامی (adsb.lol) | خودکار، محدوده عرض ۱۲ تا ۴۰ و طول ۳۰ تا ۶۲ |
| کانال‌های عمومی تلگرام | `config/telegram.txt` |
| خبرخوان‌ها و Google News چهارزبانه | `config/rss.txt` |
| حساب‌های X (فقط با کلید API پولی) | `config/x_accounts.txt` |
| کلیدواژه‌ها و ایموجی‌های هشدار | `config/keywords.txt`، `config/emojis.txt` |

کلید X را فقط در Settings → Secrets and variables → Actions با نام `X_BEARER_TOKEN` بگذارید. `X_PER_RUN` (پیش‌فرض ۲۵) تعداد حساب در هر اجرا را تعیین می‌کند تا از سقف API عبور نکنید.

زمان‌بندی GitHub برای هر ۵ دقیقه تضمینی نیست و ممکن است چند دقیقه دیر اجرا شود.
