# 🤖 AI Agent — منصة ذكاء اصطناعي متكاملة

منصة وكيل ذكاء اصطناعي متكاملة مبنية على **Claude Opus 4.7** مع حلقة أدوات وكيلية، ذاكرة دائمة، خطوط أنابيب متعددة الوكلاء، ولوحة تحكم عربية بنمط داكن.

---

## ✨ المميزات

| # | الميزة | الوصف |
|---|--------|-------|
| 1 | **تنفيذ المهام الوكيلية** | حلقة Claude مع 9 أدوات، تفكير تكيفي، وتخزين مؤقت للبرومبت |
| 2 | **محادثة متعددة الأدوار** | تاريخ محادثة لكل جلسة مع دعم تبديل الشخصيات |
| 3 | **RAG (أسئلة على المستندات)** | رفع PDF/TXT/CSV → تقطيع → تضمين → بحث دلالي + إجابة Claude |
| 4 | **رؤية وتحليل الصور** | تحليل الصور، OCR، مقارنة الصور، تحليل من URL |
| 5 | **تحليل البيانات والمخططات** | رفع CSV/Excel → تحليل AI + توليد مخططات matplotlib |
| 6 | **شخصيات الوكيل** | 8 شخصيات مدمجة + إنشاء شخصيات مخصصة |
| 7 | **قوالب البرومبت** | 6 قوالب مدمجة + قوالب مخصصة مع استبدال المتغيرات |
| 8 | **المهام المتوازية (Batch)** | تنفيذ حتى 10 مهام بالتوازي باستخدام ThreadPoolExecutor |
| 9 | **أداة قاعدة البيانات** | استعلامات SQLite / PostgreSQL مع حماية من SQL Injection |
| 10 | **أتمتة المتصفح** | تحكم Playwright كامل: لقطات شاشة، كشط، ملء نماذج |
| 11 | **اختبار API** | تشغيل طلبات HTTP + تحليل الاستجابة بالذكاء الاصطناعي |
| 12 | **أداة Docker** | إدارة الحاويات والصور من داخل الوكيل |
| 13 | **لوحة المراقبة** | استخدام الرموز، التكلفة (USD)، زمن الاستجابة، ملخصات بالساعة |
| 14 | **تحديد المعدل** | Token-bucket لكل IP مع دعم Flask-Limiter |
| 15 | **جدولة المهام** | وظائف cron مبنية على APScheduler |
| 16 | **خط أنابيب متعدد الوكلاء** | Planner → Researcher → Writer → Reviewer |
| 17 | **صندوق رمل Python** | تنفيذ آمن عبر subprocess مع قائمة حظر الاستيراد |
| 18 | **ذاكرة دائمة** | مخزن متجهات ChromaDB للاسترجاع الدلالي |
| 19 | **مصادقة JWT** | HMAC-HS256 يدوي — بدون تبعية PyJWT |
| 20 | **Webhooks والبريد الإلكتروني** | تسليم webhook موقّع + إشعارات SMTP |
| 21 | **تكامل GitHub** | مستودعات، مشاكل، PRs، محتوى الملفات، بحث الكود |
| 22 | **Slack / Discord** | دعم Webhook + Bot Token، دالة `notify()` موحدة |

---

## 🏗️ المعمارية

```
ai-agent/
├── core/
│   ├── app.py              # Flask REST API (860+ سطر، 50+ endpoint)
│   ├── orchestrator.py     # AIOrchestrator — حلقة Claude الوكيلية
│   ├── config.py           # إعدادات مركزية من متغيرات البيئة
│   ├── chat.py             # محادثة متعددة الأدوار مع دعم الشخصيات
│   ├── rag.py              # محرك RAG (تقطيع/تضمين/استعلام)
│   ├── vision.py           # تحليل الصور عبر Claude متعدد الوسائط
│   ├── data_analysis.py    # تحليل CSV/Excel + مخططات matplotlib
│   ├── personas.py         # CRUD شخصيات الوكيل (8 مدمجة)
│   ├── prompt_templates.py # CRUD القوالب + تصيير/تشغيل (6 مدمجة)
│   ├── batch.py            # تنفيذ المهام المتوازية
│   ├── monitoring.py       # تتبع الرموز/التكلفة/زمن الاستجابة
│   ├── rate_limit.py       # Token-bucket للتحديد
│   ├── scheduler.py        # وظائف APScheduler
│   ├── auth.py             # مصادقة JWT (HMAC-HS256 يدوي)
│   ├── notifications.py    # Webhooks + بريد SMTP
│   └── integrations.py     # Slack + Discord
├── agents/
│   ├── planner_agent.py    # تحليل المهمة → خطة JSON
│   ├── executor_agent.py   # مرسّل الأدوات خطوة بخطوة
│   ├── memory_agent.py     # تخزين/استرجاع/تلخيص الجلسات
│   └── pipeline.py         # خط أنابيب متعدد الوكلاء
├── tools/
│   ├── os_tools.py         # تنفيذ bash آمن
│   ├── file_tools.py       # قراءة/كتابة/بحث الملفات
│   ├── web_tools.py        # HTTP + BeautifulSoup + DuckDuckGo
│   ├── llm_tools.py        # توليد/تصنيف/تلخيص
│   ├── code_sandbox.py     # صندوق رمل Python عبر subprocess
│   ├── db_tools.py         # استعلامات SQLite/PostgreSQL
│   ├── browser_tools.py    # أتمتة Playwright
│   ├── api_tester.py       # اختبار HTTP API + تحليل AI
│   ├── docker_tools.py     # إدارة حاويات Docker
│   └── github_tools.py     # تكامل GitHub API
├── memory/
│   ├── chromadb_client.py  # مخزن متجهات ChromaDB الدائم
│   └── memory_manager.py   # واجهة ذاكرة عالية المستوى
├── templates/
│   └── index.html          # SPA عربية بنمط داكن (11 تبويب)
├── static/
│   ├── css/main.css        # واجهة بنمط داكن
│   └── js/main.js          # Vanilla JS (700+ سطر)
├── orchestrator.py         # نقطة دخول CLI
└── requirements.txt
```

---

## 🚀 البداية السريعة

### 1. تثبيت التبعيات

```bash
pip install -r requirements.txt
playwright install chromium   # لأتمتة المتصفح
```

### 2. إعداد البيئة

```bash
cp .env.example .env
# عدّل .env وأضف ANTHROPIC_API_KEY
```

### 3. التشغيل

```bash
# خادم الويب + API
python orchestrator.py serve

# تنفيذ مهمة من CLI
python orchestrator.py run "اكتب سكريبت Python يحسب أول 20 رقم فيبوناتشي"

# عرض الخطة فقط
python orchestrator.py plan "ابنِ REST API لتطبيق قائمة مهام"

# Docker
docker compose up --build
```

افتح **http://localhost:5000** ← لوحة تحكم عربية بنمط داكن مع 11 تبويب.

---

## 🌐 مرجع API

### المهام الأساسية

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| GET | `/health` | فحص الحالة |
| POST | `/api/task` | إرسال مهمة غير متزامنة |
| GET | `/api/task/<id>` | استطلاع حالة المهمة |
| GET | `/api/task/<id>/stream` | بث SSE لمخرجات المهمة |
| POST | `/api/task/run` | تنفيذ مهمة متزامن |
| GET | `/api/tasks` | قائمة المهام الأخيرة |

### المحادثة والشخصيات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| POST | `/api/chat` | محادثة متعددة الأدوار |
| POST | `/api/chat/persona` | محادثة بشخصية محددة |
| POST | `/api/chat/clear` | مسح تاريخ الجلسة |
| GET | `/api/personas` | قائمة جميع الشخصيات |
| POST | `/api/personas` | إنشاء شخصية مخصصة |
| DELETE | `/api/personas/<id>` | حذف شخصية مخصصة |

### القوالب

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| GET | `/api/templates` | قائمة القوالب |
| POST | `/api/templates` | إنشاء قالب |
| POST | `/api/templates/<id>/render` | تصيير (معاينة) القالب |
| POST | `/api/templates/<id>/run` | تصيير + تنفيذ القالب |

### الرؤية والبيانات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| POST | `/api/vision/analyze` | تحليل صورة (ملف أو URL) |
| POST | `/api/vision/ocr` | استخراج نص من صورة |
| POST | `/api/vision/compare` | مقارنة صورتين |
| POST | `/api/data/upload` | رفع CSV/Excel → ملخص |
| POST | `/api/data/analyze` | تحليل AI للبيانات |
| POST | `/api/data/chart` | توليد مخطط (bar/line/pie/scatter) |

### الذاكرة و RAG

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| POST | `/api/memory` | حفظ ذاكرة |
| POST | `/api/memory/search` | بحث دلالي |
| POST | `/api/rag/upload` | استيعاب مستند |
| POST | `/api/rag/query` | سؤال وجواب على المستندات |
| GET | `/api/rag/documents` | قائمة المستندات |

### الأدوات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| POST | `/api/batch` | تنفيذ مهام متوازية (حتى 10) |
| POST | `/api/code/run` | تنفيذ Python في صندوق رمل |
| POST | `/api/db/query` | استعلام SQL |
| GET | `/api/db/tables` | قائمة الجداول |
| POST | `/api/browser/screenshot` | لقطة شاشة لـ URL |
| POST | `/api/browser/text` | استخراج نص الصفحة |
| POST | `/api/test/request` | اختبار HTTP API |
| POST | `/api/docker/<action>` | إدارة Docker |

### المراقبة والإشعارات

| الطريقة | المسار | الوصف |
|---------|--------|-------|
| GET | `/api/monitoring/stats` | استخدام الرموز + التكلفة |
| GET | `/api/monitoring/requests` | سجل الطلبات الأخيرة |
| GET | `/api/monitoring/hourly` | ملخص بالساعة |
| POST | `/api/notify/slack` | إرسال رسالة Slack |
| POST | `/api/notify/discord` | إرسال رسالة Discord |
| POST | `/api/webhooks` | تسجيل webhook |
| POST | `/api/scheduler/jobs` | إضافة وظيفة cron |

---

## ⚙️ الإعداد

جميع الإعدادات عبر `.env` (انظر `.env.example`):

```env
# مطلوب
ANTHROPIC_API_KEY=sk-ant-...

# أساسي
MODEL=claude-opus-4-7
MAX_TOKENS=16000
MAX_AGENT_ITERATIONS=30
BASH_TIMEOUT=30
WEB_TIMEOUT=15

# المصادقة
AUTH_DISABLED=true          # اضبط false لتفعيل JWT
ADMIN_USER=admin
ADMIN_PASS=admin123

# تكاملات اختيارية
GITHUB_TOKEN=ghp_...
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
DATABASE_URL=               # postgresql://... (فارغ = SQLite)
```

---

## 🔒 الأمان

- **Bash**: قائمة أنماط محظورة (rm -rf, dd, mkfs, curl pipe...)
- **SQL**: يحجب الاستعلامات المتراكمة، UNION SELECT، التعليقات المضمنة، xp_cmdshell
- **صندوق الرمل**: يحجب subprocess، os.system، shutil.rmtree، ctypes
- **تحديد المعدل**: Token-bucket (60 طلب/دقيقة لكل IP)
- **JWT**: HMAC-SHA256، انتهاء 24 ساعة، تجزئة SHA256 لكلمة المرور
- **Webhooks**: حمولات موقّعة بـ HMAC-SHA256

---

## 🛠️ مجموعة التقنيات

| الطبقة | التقنية |
|--------|---------|
| LLM | Claude Opus 4.7 (تفكير تكيفي + تخزين مؤقت للبرومبت) |
| API | Flask 3.x + بث SSE |
| الذاكرة | ChromaDB (تشابه جيب التمام، دائم) |
| المتصفح | Playwright (Chromium بدون واجهة) |
| المخططات | matplotlib |
| الجدولة | APScheduler |
| المصادقة | HMAC-HS256 JWT يدوي |
| الواجهة | Vanilla JS + CSS (بدون إطار عمل) |

---

## 📊 إحصائيات

- **37 ملف Python** — 4,224 سطر
- **50+ endpoint REST API**
- **لوحة تحكم عربية بـ 11 تبويب**
- **9 أدوات وكيلية** في حلقة Claude
- **44 اختبار وحدة** — جميعها ناجحة ✅
- **60 اختبار endpoint حي** — جميعها ناجحة ✅
