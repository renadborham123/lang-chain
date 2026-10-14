# وظّفني / Wazzefni — UI/UX Design Scope

> وثيقة جاهزة للتسليم إلى مصمم UI/UX. المطلوب تصميم الواجهات والتجربة فقط في Figma، بدون كتابة كود أو تغيير وظائف المنتج.

## Implemented employment workspace

النسخة الحالية أصبحت Responsive PWA، والـroutes التالية هي مصدر الحقيقة لجولة التصميم القادمة. المطلوب تصميمها كنظام واحد هادئ ومترابط، وليس مجموعة dashboard cards منفصلة.

| Route | المهمة الأساسية | الحالات المطلوبة |
|---|---|---|
| `/today` | عرض مهمة تأهيل أو تقديم واحدة فقط كخطوة اليوم | loading, no target role, qualification task, application task, approval pending |
| `/readiness` | عرض Role Readiness وEvidence Strength وCV Representation | no target, calculating, development, apply while improving, apply now |
| `/development` | خطة التأهيل والـto-do list والـCareer Ladder | pending, in progress, awaiting assessment, remediation, complete |
| `/proof` | concept/scenario/project-defense assessment واقتراح تعديل CV | active turn, evaluating, Pass, Partial, Not yet, CV approval |
| `/opportunities` | Apply now / Apply while improving / Unlock later / Training | saved, closed, hard gap, missing evidence, official source unverified |
| `/applications` | Kanban/List مع inspector وtimeline لكل تقديم | كل حالات lifecycle، no results، blocked، failed |
| `/interviews` | تدريب Text/Voice مرتبط بالوظيفة وعرض feedback | setup, recording, transcribing, evaluating, complete, model unavailable |
| `/offers` | تسجيل ومقارنة وتوضيح وتفاوض وقبول أو رفض العرض | not stated, incompatible currencies, draft, approval pending |
| `/profile` | إدارة الحقائق المؤكدة والسوق واللغة والتكاملات | connected, disconnected, syncing, token expired |
| `/settings` | اختيار local/cloud model والخصوصية | local available, cloud consent, provider offline |

على الموبايل يوجد bottom navigation من: Today، Readiness، Plan، Jobs، More. على Desktop توجد left rail ثابتة. واجهة العربية يجب أن تكون RTL فعلية، مع بقاء ترتيب الـpipeline زمنيًا. أي external action يعرض النص أو البيانات كاملة ثم خطوة موافقة صريحة.

## 1. نبذة عن المنتج

**وظّفني / Wazzefni** وكيل شخصي للتأهيل والتوظيف بالذكاء الاصطناعي. البراند لا يعد المستخدم بالقبول؛ هو يوضح أين يقف، ماذا ينقصه، كيف يثبت المهارة، ومتى يصبح التقديم منطقيًا.

المنتج يستطيع أن:

- يستقبل CV بصيغة PDF أو TXT، أو يساعد المستخدم على إنشاء CV جديد.
- يبحث عن فرص عمل حقيقية ويستبعد الوظائف المغلقة أو غير المناسبة.
- يرتب النتائج حسب مدى توافقها مع خبرة ومهارات المستخدم.
- يعرض ملخصًا موثوقًا لكل وظيفة وتفاصيلها الأساسية.
- ينشئ CV مخصصًا للوظيفة، ويساعد في ملء نموذج التقديم.
- يحفظ إجابات المستخدم المتكررة محليًا لإعادة استخدامها.
- يقدم خطة عملية لتحسين فرص القبول بناءً على الوظائف الحالية.
- يساعد المستخدم في الوصول إلى مسؤول توظيف وكتابة رسالة تواصل قابلة للمراجعة.

### المستخدم الأساسي

- طالب أو خريج جديد يبحث عن Internship / Trainee / Graduate role.
- باحث عن عمل في بداية أو منتصف مسيرته المهنية.
- يريد تقليل الوقت الضائع في البحث والتقديم المتكرر.

### هدف التجربة

يجب أن يشعر المستخدم أن المنتج:

- موثوق وشفاف، ولا يخترع معلومات غير موجودة.
- يقلل المجهود، لكن يترك القرارات النهائية للمستخدم.
- يعرض خطوة واحدة واضحة في كل مرة.
- احترافي وهادئ، وليس Dashboard مزدحمًا.

---

## 2. المطلوب من المصمم

إنشاء ملف Figma كامل يشمل:

- Desktop screens بعرض مرجعي 1440px.
- Tablet screens بعرض مرجعي 1024px.
- Mobile screens بعرض مرجعي 390px.
- Responsive behavior لكل شاشة أساسية.
- جميع الـcomponents والـvariants والحالات التفاعلية.
- Prototype للـmain user flow.
- Design system مصغر: colors, typography, spacing, grids, buttons, fields, chips, status badges, cards, modals, icons, feedback messages, skeletons.
- أسماء الـframes والـcomponents بالإنجليزية لسهولة التسليم إلى المطور.

واجهة المنتج تدعم **الإنجليزية والعربية** مع LTR/RTL. يجب تصميم أهم الرحلات باللغتين، مع مراعاة تمدد النص العربي، محاذاة الأيقونات، وترتيب حقول النماذج على الموبايل.

---

## 3. Information Architecture

التطبيق Single Page Application بواجهة رئيسية ثابتة، وتتغير مساحة العمل حسب القسم المختار.

### Sidebar / Main Navigation

1. **Opportunities**
   - قائمة الوظائف المقترحة.
   - البحث والفلترة.
   - تفاصيل الوظيفة وإجراءات التقديم.
2. **Acceptance Plan**
   - خطة تحسين فرص القبول.
   - سؤال واحد مهم في كل مرة.
   - توصيات مبنية على سوق العمل الحالي.
3. **Saved**
   - نفس واجهة Opportunities، لكن تعرض الوظائف المحفوظة فقط.
4. **Settings**
   - تفتح Modal لإعداد نموذج الذكاء الاصطناعي.
5. **System Status** أسفل الـsidebar
   - Ready / Offline.
   - اسم النموذج المستخدم وLocal أو Cloud.

على الموبايل يجب اقتراح Navigation مناسبة بدل الـsidebar الدائم، مثل bottom navigation أو compact drawer، مع إبقاء Settings متاحة بوضوح.

---

## 4. الشاشات المطلوبة بالتفصيل

## Screen 01 — Opportunities / Initial State

هذه أول شاشة يراها المستخدم قبل بدء البحث.

### Header

- Eyebrow: `OPPORTUNITIES`
- Title: `Jobs worth your time`
- Description قصيرة تشرح أن وظّفني يشخّص النواقص، يبني دليلًا، ثم يساعد في التقديم.

### Search Panel

- Title: `Find your next role`
- Supporting text: النظام يستطيع اقتراح المسميات المناسبة من الـCV.
- **Choose your CV** upload area:
  - يقبل PDF أو TXT.
  - حالة no file.
  - حالة selected file.
  - حالة saved reusable CV.
  - حالة generated CV selected.
- **Build a CV** secondary action.
- **Target location** text input، مثال: Cairo or Remote.
- **Number of results** select: 3 / 5 / 10 roles.
- **Find roles** primary CTA.
- Collapsible **Search preferences**:
  - Specific roles — optional.
  - Exclude titles.
  - Show the search browser — checkbox/toggle مع شرح قصير.

### Initial Empty State

مطلوب 3 variants:

- لا يوجد CV: `Start with your CV.`
- يوجد CV محفوظ: `Your CV is ready.`
- تم البحث ولا توجد نتائج: `No current matches yet.` مع زر Adjust search.

---

## Screen 02 — Search in Progress

نفس شاشة Opportunities أثناء البحث، مع:

- Disabled form state.
- CTA loading state: `Searching…`
- Progress panel أو progress strip يوضح:
  - Checking current listings.
  - Removing closed or unsuitable jobs.
  - Matching jobs to the CV.
- يفضل استخدام indeterminate progress مع micro-animation هادئة.

### حالات الخطأ

- Generic search error مع dismiss.
- Backend offline.
- CAPTCHA / verification blocked:
  - رسالة واضحة.
  - CTA: `Retry with the browser hidden`.
- Success notice / informational notice.

---

## Screen 03 — Opportunities / Results Workbench

الشاشة الأساسية بعد نجاح البحث.

### Collapsed Search Summary

بدل نموذج البحث الكبير يظهر شريط مختصر يحتوي على:

- الدور أو `CV-recommended roles`.
- الموقع.
- اسم ملف الـCV.
- عدد النتائج.
- `Change` action.
- `Refresh` action.

### Results Summary

- Title يوضح عدد الوظائف المقترحة.
- نص يتغير إذا كان المستخدم طالبًا؛ يتم توضيح أن internships وgraduate roles لها أولوية.
- Statistics:
  - Checked.
  - Matched.
  - Ready.

### Acceptance Agent Strip

شريط ذكي بين البحث والنتائج يحتوي على:

- حالة تحليل الخطة.
- رسالة مختصرة عن أفضل خطوة تالية.
- CTA: `Answer once` أو `View plan`.
- Variants: loading / ready / error.

### Results Toolbar

- Tabs:
  - All + count.
  - Ready + count.
  - Saved + count.
- Search داخل النتائج حسب role / company / skill.
- Search strategy chips: أول 3 queries استخدمها النظام.

### Desktop Workbench Layout

تقسيم الشاشة إلى عمودين:

- العمود الأيسر: قائمة الوظائف.
- العمود الأيمن: Job Details Inspector ثابت أو sticky.

على الموبايل تصبح القائمة شاشة، واختيار وظيفة يفتح تفاصيلها كصفحة كاملة أو bottom sheet/full-screen sheet.

---

## Component — Job Result Card

كل كارت وظيفة يحتوي على:

- Opportunity type: job / internship / graduate program / trainee.
- Match percentage.
- Job title.
- Company.
- Location.
- سبب مختصر للترشيح.
- Status badge:
  - `Ready to apply`.
  - `Review first`.
- Save / unsave icon.
- Selected state واضح.
- Hover / focus / pressed states.

---

## Screen 04 — Job Details Inspector

تظهر عند اختيار وظيفة من القائمة.

### Top Section

- Opportunity type.
- Match percentage.
- Job title.
- Company + location.
- Primary action:
  - `Autofill & review` للوظائف المباشرة.
  - `Open application` إذا كان التقديم خارجيًا فقط.
- Save / Saved.
- Open original listing icon.

### Role Brief

- Source quality badge:
  - Detailed source.
  - Partial source.
  - Limited source.
- Role summary.
- Facts grid:
  - Salary أو Pay / stipend.
  - Work setup.
  - Employment type.
  - Hours / schedule.
  - Duration عند الحاجة.
  - Experience.
  - Posted date.
  - Apply-by deadline.
- أي معلومة غير موجودة يجب أن تظهر `Not stated`، وليس كأنها خطأ.

### Content Sections

- What you would do.
- What they are looking for.
- What this listing values، مع supporting quote من الإعلان.
- Why it was recommended.
- Matched skill chips.
- About the company:
  - Company snapshot.
  - Industry.
  - Team size.
  - Founded year.
  - Company page link.
- Original listing link.
- Company website link.
- Source / verification note.

### Secondary Actions

- `Draft note`.
- `Find a person`.
- `Download CV` أو `Download tailored CV`.
- `Auto-apply` إذا كانت الوظيفة جاهزة للتقديم.

### Required States

- No job selected.
- Brief loading skeleton.
- Brief loaded.
- Partial data / missing facts.
- Brief error + retry.
- Tailored CV generating.
- Tailored CV ready.
- Tailored CV error.

---

## Screen 05 — Saved Opportunities

نفس Results Workbench لكن الفلتر يكون Saved افتراضيًا.

### حالات مطلوبة

- Saved jobs موجودة.
- لا توجد saved jobs:
  - Empty state: `Save a role to keep it here.`
  - CTA للعودة لكل الوظائف.
- إزالة وظيفة من Saved وتحديث العدد مباشرة.

---

## Screen 06 — Acceptance Plan

مساحة عمل مستقلة، هدفها توجيه المستخدم إلى الخطوة التي تزيد فرصة القبول فعلًا.

### State A — Before First Search

- Empty state يشرح أن الخطة تحتاج عينة فعلية من السوق.
- CTA: `Find roles first`.

### State B — Building the Plan

- Loading state / skeleton.
- رسالة: النظام يقرأ الـCV والوظائف الحالية.

### State C — Plan Ready

#### Agent Summary

- Acceptance agent identity.
- Main plan message.
- Source note.
- Activity stepper يوضح المراحل المكتملة والحالية.

#### One Useful Question

- سؤال واحد فقط في الشاشة.
- سبب طرح السؤال.
- أحد الشكلين:
  - Multiple-choice options.
  - Text input + Save answer.
- توضيح هل الإجابة:
  - ستضاف للـCV لأنها حقيقة مهنية آمنة.
  - أم ستُحفظ كتفضيل فقط ولن تكتب داخل الـCV.
- State بعد عدم الحاجة إلى سؤال: `I already have enough information…`.

#### Trade-off Decision

- سؤال قرار مثل توسيع الموقع أو نوع الوظيفة.
- أكثر من خيار.
- كل خيار قد يعرض تأثيره: `+X current roles`.

#### CV Update Success

- Success card.
- عرض الأقسام أو الحقائق التي أضيفت.
- `Open PDF` action.

#### Market Signals

- قائمة توصيات مرتبة حسب الأولوية.
- عنوان التوصية.
- شرح مختصر.
- عدد الوظائف المتأثرة.
- Evidence quote + اسم الوظيفة.
- Empty state عند عدم وجود gap متكرر.

#### External Proof / Growth Opportunities

- بطاقة توضح لماذا قد تساعد event / fair / competition / meetup.
- CTA: `Find relevant events`.
- Loading state.
- Results list، وكل نتيجة تحتوي على:
  - Type.
  - Title.
  - Snippet.
  - Verification note.
  - External link.
- `Full search` link.
- Empty research results state.

### Error State

- فشل إنشاء الخطة.
- رسالة واضحة مع CTA للعودة إلى البحث أو المحاولة مرة أخرى.

---

## Modal 01 — CV Builder Wizard

Wizard من 6 خطوات لإنشاء ATS-friendly CV.

### Shared Layout

- Progress bar + percentage verified.
- Step number: 1/6 إلى 6/6.
- سؤال رئيسي.
- Hint / supporting text.
- Large textarea.
- Back / Next.
- Close.

### الخطوات

1. **Identity & contact**
   - Full name, email, phone, city, LinkedIn/GitHub.
2. **Career goal**
   - Target role أو internship، وهل المستخدم طالب.
3. **Experience**
   - Work, freelance, volunteering, internships.
4. **Projects**
   - Problem, contribution, tools, factual result.
5. **Skills**
   - Skills and tools the user can genuinely use.
6. **Education & extras**
   - Education, graduation date, certificates, languages, achievements.

### Final Step States

- Missing requirements list.
- Generate disabled until readiness = 100%.
- `Building ATS PDF…` loading.
- Error state.

### CV Ready State

- Title: `Your CV is ready to review.`
- Read-only CV text preview.
- `Download PDF`.
- `Use for search`.
- Trust message: only facts from the user's answers were used.

---

## Modal 02 — Model Settings

### المحتوى

- Tabs: Local / Cloud.
- Base URL field.
- Cloud only: API key password field.
- Refresh models button.
- Model select.
- Save model CTA.
- Security note: cloud key remains in backend memory and is not saved to the settings file.

### الحالات

- Initial loading.
- No model selected.
- Refreshing models.
- Model list loaded.
- Existing configured API key.
- Validation or connection error.
- Saved successfully.

---

## Modal 03 — Application Draft

- Label: `APPLICATION DRAFT`.
- Job title.
- Company.
- Read-only draft textarea.
- Copy draft.
- Open listing.
- Copy success feedback.

---

## Modal 04 — Review-first Outreach

يساعد المستخدم في العثور على contact منشور علنًا ثم كتابة رسالة قابلة للتعديل.

### المرحلة الأولى: Finding Contacts

- Job title + company.
- Loading state: checking published contacts and public profiles.
- Contact list item:
  - Email أو LinkedIn icon.
  - Name.
  - Role.
  - `Published` أو `Check profile` status.
- Selected contact state.
- Empty state: لم يتم تخمين أي contact.
- Public search fallback link.

### المرحلة الثانية: Drafting

- CTA: Draft for [name].
- Draft loading state.
- Email subject field، يظهر فقط في email.
- Editable message textarea.
- Safety/review instruction.
- Copy message.
- Open email draft أو Open LinkedIn profile.
- Source note.
- Copied success state.
- Error state.

---

## Modal 05 — Application Assistant

هذا الـmodal يوضح حالة التقديم أثناء فتح browser منفصل لملء نموذج الوظيفة.

### Header and Status

- Label: `APPLICATION ASSISTANT`.
- Current status badge.
- Dynamic status message.
- Summary:
  - CV uploaded أو لا.
  - Number of fields filled.
  - Number of saved answers reused.

### Missing Questions Flow

إذا احتاج النموذج معلومات غير موجودة:

- Question progress: X of Y.
- Answered count.
- Progress bar.
- السؤال الحالي.
- Input أو select حسب نوع السؤال.
- Back / Next.
- `Save answers & continue`.
- الإجابات تحفظ محليًا لإعادة استخدامها.

### Application Status Variants

يجب تصميم badge ورسالة وأزرار مناسبة لكل حالة:

- Starting / running / filling.
- Needs input.
- Ready to submit.
- Needs review.
- Blocked، مثل CAPTCHA أو login.
- Submitted successfully.
- Unavailable / closed job.
- Failed / expired.
- Closed by user.

### Actions by State

- `Confirm submit` عند ready to submit.
- `Save answers & continue` عند needs input.
- `Retry after review` عند blocked أو needs review.
- `Close browser` متاحة دائمًا.
- Blockers and unavailable messages تظهر بوضوح.

يجب أن يظل الـfinal submit قرارًا واضحًا ومقصودًا من المستخدم، بدون تصميم مضلل أو auto-confirm غامض.

---

## 5. Global UI States

يجب توفير component variants واضحة للحالات التالية:

- Default.
- Hover.
- Focus visible.
- Pressed.
- Selected.
- Disabled.
- Loading.
- Success.
- Warning.
- Error.
- Offline.
- Empty.
- Skeleton.
- Long text / overflow.
- Missing data: `Not stated`.

ويجب تصميم Toast / inline alert / status badge بشكل متناسق عبر التطبيق.

---

## 6. Design System Requirements

المصمم حر في الاتجاه البصري، مع الالتزام بالشخصية التالية:

- Professional, calm, intelligent, trustworthy.
- حديث، لكن غير مبالغ في الـgradients أو glassmorphism.
- كثافة معلومات متوسطة ومقروءة.
- Hierarchy قوي بين primary action والمعلومات المساندة.
- استخدام لون Accent رئيسي واحد مع ألوان semantic للحالات.
- AA contrast على الأقل للنصوص والعناصر التفاعلية.

### Foundations

- Color palette:
  - Background / surface / elevated surface.
  - Primary accent.
  - Text primary / secondary / muted.
  - Border / divider.
  - Success / warning / error / info.
- Typography scale:
  - Display / page title / section title / card title / body / label / caption / mono metadata إن لزم.
- 4px أو 8px spacing system.
- Radius scale.
- Shadow scale محدود.
- Desktop content grid + responsive breakpoints.

### Components

- Sidebar / mobile navigation.
- Page header.
- Primary, secondary, quiet, destructive/icon buttons.
- Text input, password input, search input, textarea, select, checkbox/toggle.
- Upload dropzone.
- Tabs and filter tabs.
- Chips / skill tags / query tags.
- Status badges.
- Job cards.
- Metric summary.
- Progress indicators and stepper.
- Empty states.
- Inline alerts.
- Skeleton loaders.
- Modal / full-screen mobile sheet.
- Tooltip عند الحاجة.
- External link pattern.

---

## 7. Responsive and UX Rules

- Desktop: sidebar ثابت + workbench عمودين.
- Tablet: sidebar مضغوط أو collapsible، مع تقليل عرض التفاصيل.
- Mobile:
  - Navigation مناسبة للشاشة الصغيرة.
  - Search form stacked.
  - Job list منفصلة عن details view.
  - Modals تتحول إلى full-screen sheets عند الحاجة.
  - الأزرار الأساسية واضحة وسهلة اللمس.
- دعم keyboard navigation وfocus states.
- لا يعتمد أي status على اللون وحده؛ يجب وجود text/icon.
- External links واضحة للمستخدم.
- أي فعل حساس مثل submit يحتاج confirmation واضح.
- Save, copy, download, refresh, retry لها feedback فوري.
- الحفاظ على نصوص طويلة بدون كسر الـlayout.

---

## 8. Main Prototype Flow

المطلوب ربط Prototype يوضح المسار التالي:

1. Open Opportunities.
2. Upload CV أو Build a CV.
3. Choose location and search.
4. View loading state.
5. See results.
6. Filter/select a job.
7. Review job details.
8. Save job.
9. Generate/download tailored CV.
10. Start Autofill & review.
11. Answer a missing application question.
12. Reach Ready to submit.
13. Confirm submit / show submitted state.
14. Open Acceptance Plan.
15. Answer one useful question.
16. View updated CV or market recommendation.
17. Open outreach, choose contact, and create/copy a message.

---

## 9. Figma Deliverables Checklist

- Cover page.
- Product overview / flow map.
- Foundations page.
- Components page with variants and states.
- Desktop screens.
- Tablet screens.
- Mobile screens.
- Main clickable prototype.
- Handoff-ready frames using Auto Layout.
- Reusable components and variables/tokens.
- Clear annotations for behavior that cannot be understood from a static frame.
- Exportable icons/assets إن وُجدت.

### الحد الأدنى للـhigh-fidelity frames

- Opportunities — initial.
- Opportunities — searching.
- Opportunities — results.
- Opportunities — no results.
- Saved — populated.
- Saved — empty.
- Job details — loading.
- Job details — full.
- Job details — partial/error.
- Acceptance Plan — before search.
- Acceptance Plan — loading.
- Acceptance Plan — ready with question.
- Acceptance Plan — ready with decision/recommendations.
- CV Builder — representative steps + validation.
- CV ready.
- Settings — Local.
- Settings — Cloud.
- Application Draft.
- Outreach — loading / contacts / draft / no contacts.
- Application Assistant — needs input / ready to submit / blocked / submitted.
- Mobile equivalents لأهم المسارات: search, results, job details, application assistant, acceptance plan.

---

## 10. خارج نطاق التصميم الحالي

لا توجد في النسخة الحالية صفحات مستقلة لـ:

- Login / signup.
- User account أو team management.
- Billing / subscription.
- Admin dashboard.
- Analytics dashboard.
- Notifications center.

لا تتم إضافة هذه الصفحات إلا إذا تم الاتفاق عليها كمرحلة جديدة، حتى يظل التصميم مطابقًا لوظائف المنتج الحالية وقابلًا للتنفيذ مباشرة.
