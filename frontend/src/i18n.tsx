import { createContext, ReactNode, useContext, useLayoutEffect, useMemo, useState } from 'react'

export type Locale = 'en' | 'ar'

const STORAGE_KEY = 'wazzefni-locale'
const LOCALE_EVENT = 'wazzefni:locale-change'

const ar: Record<string, string> = {
  // Shared navigation and workspace chrome
  'Workspace': 'مساحة العمل',
  'Your step today': 'خطوتك اليوم',
  'Develop': 'طوّر نفسك',
  'Career development': 'التطوير المهني',
  'Find work': 'ابحث عن عمل',
  'Opportunities': 'الفرص',
  'Applications': 'طلبات التقديم',
  'Saved': 'المحفوظة',
  'Saved roles': 'الوظائف المحفوظة',
  'Offers': 'العروض',
  'Settings': 'الإعدادات',
  'Today': 'اليوم',
  'Jobs': 'الوظائف',
  'Pipeline': 'مسار التقديم',
  'More': 'المزيد',
  'Notifications': 'الإشعارات',
  'You’re all caught up': 'لا توجد تحديثات جديدة',
  'New application and interview updates will appear here.': 'ستظهر هنا تحديثات طلبات التقديم والمقابلات.',
  'Search Wazzefni': 'ابحث في وظّفني',
  'Search jobs, companies, or skills...': 'ابحث عن وظائف أو شركات أو مهارات...',
  'Open settings': 'فتح الإعدادات',
  'Primary navigation': 'التنقل الرئيسي',
  'Application pipeline': 'مسار التقديم',
  'Open profile': 'فتح الملف الشخصي',
  'How Wazzefni helps': 'كيف يساعدك وظّفني',
  'Wazzefni helping someone build job readiness': 'مساعد وظّفني يساعد في بناء الجاهزية للعمل',

  // Page headings
  'TODAY': 'اليوم',
  'DEVELOPMENT': 'التطوير المهني',
  'READINESS': 'الجاهزية',
  'QUALIFICATION PLAN': 'خطة التأهيل',
  'SKILL PROOF': 'إثبات المهارة',
  'MARKET RESEARCH': 'بحث السوق',
  'APPLICATIONS': 'طلبات التقديم',
  'DEVELOPMENT · PRACTICE': 'التطوير · التدريب',
  'OFFERS': 'العروض',
  'PROFILE': 'الملف الشخصي',
  'SETTINGS': 'الإعدادات',
  'One qualification or application action, chosen from your real evidence.': 'خطوة تأهيل أو تقديم واحدة مبنية على أدلتك الحقيقية.',
  'Build your path to the role': 'ابنِ مسارك نحو الوظيفة',
  'Readiness, qualification, skill proof, and interview practice in one connected workspace.': 'الجاهزية والتأهيل وإثبات المهارات وتدريب المقابلات في مساحة مترابطة واحدة.',
  'Your readiness': 'جاهزيتك',
  'See what is proved, what is missing, and which path is realistic now.': 'اعرف ما تم إثباته وما ينقصك وما هو المسار الواقعي الآن.',
  'Your qualification plan': 'خطة تأهيلك',
  'Build the evidence that unlocks stronger training and job opportunities.': 'ابنِ الأدلة التي تفتح لك تدريبات وفرص عمل أقوى.',
  'Prove what you can do': 'أثبت ما يمكنك إنجازه',
  'Assessment based on your explanation, reasoning, and inspectable work.': 'تقييم مبني على شرحك وطريقة تفكيرك وعمل يمكن مراجعته.',
  'Opportunity workspace': 'مساحة الفرص',
  'Search, compare, and act on roles matched to your actual profile.': 'ابحث وقارن وتعامل مع وظائف مناسبة لملفك الحقيقي.',
  'Your saved roles': 'وظائفك المحفوظة',
  'Keep your favorite opportunities in one place.': 'احتفظ بفرصك المفضلة في مكان واحد.',
  'Find useful growth opportunities.': 'اكتشف فرص تطوير مفيدة.',
  'Research is supporting evidence for your qualification plan.': 'بحث السوق دليل داعم لخطة تأهيلك.',
  'Every application, one history': 'كل طلب تقديم له سجل واحد',
  'Track the evidence, conversations, next action, and outcome.': 'تابع الأدلة والمحادثات والخطوة القادمة والنتيجة.',
  'Practice against the actual role': 'تدرّب للوظيفة الفعلية',
  'Text and voice coaching grounded in your confirmed experience.': 'تدريب نصي وصوتي مبني على خبرتك المؤكدة.',
  'Decide with the full picture': 'اتخذ قرارك بالصورة الكاملة',
  'Compare stated terms and prepare a response without invented leverage.': 'قارن الشروط المعلنة وجهّز ردًا من دون ادعاءات غير حقيقية.',
  'Your trusted career memory': 'ذاكرتك المهنية الموثوقة',
  'Confirmed facts and connected services power every agent.': 'الحقائق المؤكدة والخدمات المتصلة تدعم كل مساعد.',
  'Manage your account, preferences, notifications, and AI runtime.': 'أدر حسابك وتفضيلاتك وإشعاراتك ومحرك الذكاء الاصطناعي.',

  // Search and live activity
  'Find your next opportunity': 'ابحث عن فرصتك القادمة',
  "Upload your CV and tell us what you're looking for. We'll find and match the best opportunities for you.": 'ارفع سيرتك الذاتية وحدد ما تبحث عنه، وسنبحث عن أنسب الفرص ونطابقها مع ملفك.',
  'Choose your CV': 'اختر سيرتك الذاتية',
  'Saved and ready to reuse': 'محفوظة وجاهزة للاستخدام',
  'Generated CV selected': 'تم اختيار السيرة المُنشأة',
  'Upload a PDF or TXT file (max 5 MB)': 'ارفع ملف PDF أو TXT بحد أقصى 5 ميجابايت',
  'Or': 'أو',
  'Build a CV instead': 'أنشئ سيرة ذاتية',
  'Upload CV': 'رفع السيرة الذاتية',
  'Location': 'الموقع',
  'Cairo or Remote': 'القاهرة أو عن بُعد',
  'Results per page': 'عدد النتائج في الصفحة',
  'Search preferences': 'تفضيلات البحث',
  '(optional)': '(اختياري)',
  'Specific roles': 'وظائف محددة',
  'e.g. Product Designer, Data Analyst': 'مثال: مصمم منتجات، محلل بيانات',
  'Exclude titles': 'استبعاد مسميات',
  'e.g. Intern, Volunteer': 'مثال: متدرب، متطوع',
  'Show search browser': 'إظهار متصفح البحث',
  'Show live search results in a new tab': 'عرض نتائج البحث الحية في تبويب جديد',
  'Find roles': 'ابحث عن وظائف',
  'Searching...': 'جارٍ البحث...',
  'Get ready, then get hired.': 'تأهّل أولًا، ثم احصل على الوظيفة.',
  'Wazzefni finds the gaps, helps you prove the missing skills, then brings the right opportunities into reach.': 'يحدد وظّفني الفجوات، ويساعدك على إثبات المهارات، ثم يقرّب لك الفرص المناسبة.',
  'Check readiness': 'افحص جاهزيتك',
  'Personalized matches': 'مطابقات مخصصة',
  'Opportunities that fit your skills': 'فرص تناسب مهاراتك',
  'Save time': 'وفّر وقتك',
  'We do the searching for you': 'نبحث نيابةً عنك',
  'More relevant results': 'نتائج أكثر صلة',
  'From top companies, worldwide': 'من شركات مميزة حول العالم',
  'Start with your CV.': 'ابدأ بسيرتك الذاتية.',
  "Upload your CV and we'll match opportunities to your skills and goals.": 'ارفع سيرتك الذاتية وسنطابق الفرص مع مهاراتك وأهدافك.',
  'Live search activity': 'نشاط البحث المباشر',
  'Preparing your search': 'نجهّز بحثك',
  'Connecting your CV to the live search workflow.': 'نربط سيرتك الذاتية بمسار البحث المباشر.',
  'Reading your CV': 'نقرأ سيرتك الذاتية',
  'Extracting only the experience, skills, and preferences you provided.': 'نستخرج فقط الخبرات والمهارات والتفضيلات التي قدمتها.',
  'What I know so far': 'ما توصلنا إليه حتى الآن',
  'Source counts will appear here as soon as each live search returns. Nothing is estimated.': 'ستظهر أعداد كل مصدر فور وصول نتائج البحث الفعلية. لا توجد أرقام تقديرية.',
  'Your CV stays factual.': 'سيرتك الذاتية تظل واقعية.',
  'I can recommend stronger wording and tailoring, but I won’t add skills, results, or experience you didn’t provide.': 'يمكنني اقتراح صياغة أقوى وتخصيص أفضل، لكنني لن أضيف مهارات أو نتائج أو خبرات لم تقدمها.',
  'Building a search plan from your CV': 'نبني خطة بحث من سيرتك الذاتية',
  'Searching live job sources': 'نبحث في مصادر الوظائف المباشرة',
  'Search complete': 'اكتمل البحث',
  'Your results are ready': 'نتائجك جاهزة',
  'Search paused': 'توقف البحث مؤقتًا',
  'CV-matched roles': 'وظائف مطابقة للسيرة',
  'current listings checked': 'إعلانًا حاليًا تمت مراجعته',
  'Active CV': 'السيرة النشطة',
  'Ready for applications': 'جاهزة للتقديم',
  'Open to current search': 'ضمن نطاق البحث الحالي',
  'Build proof before you apply': 'ابنِ دليلك قبل التقديم',
  'Our AI separates what you can apply for now from what you can unlock next.': 'يفصل النظام بين ما يمكنك التقديم له الآن وما يمكنك الوصول إليه بعد التطوير.',
  'Learn how it works': 'اعرف كيف يعمل',
  'Opportunities for You': 'فرص مناسبة لك',
  'Ranked by readiness and verified evidence—not acceptance probability': 'مرتبة حسب الجاهزية والأدلة الموثقة، وليس احتمال القبول',
  'Best readiness': 'الأعلى جاهزية',
  'All': 'الكل',
  'Apply now': 'قدّم الآن',
  'Apply while improving': 'قدّم وطوّر نفسك',
  'Unlock later': 'متاحة بعد التطوير',
  'Training': 'تدريب',
  'Match': 'تطابق',
  'Load more jobs': 'عرض وظائف إضافية',
  'Tailor CV & Apply': 'خصّص السيرة وقدّم',
  'Save': 'حفظ',
  'Unsave': 'إزالة الحفظ',
  'About the role': 'عن الوظيفة',
  'Key facts': 'معلومات أساسية',
  'Matched skills': 'المهارات المطابقة',
  'View all': 'عرض الكل',
  'Source quality': 'جودة المصدر',
  'High confidence': 'ثقة عالية',
  'Original listing': 'الإعلان الأصلي',
  'opens in a new tab': 'يفتح في تبويب جديد',
  'Not stated': 'غير مذكور',

  // Development lobby
  'YOUR DEVELOPMENT PATH': 'مسار تطويرك',
  'Build readiness before pressure.': 'ابنِ جاهزيتك قبل ضغط التقديم.',
  'Diagnosis, focused learning, proof, and interview practice now live in one connected path.': 'التشخيص والتعلّم المركّز وإثبات المهارة وتدريب المقابلات أصبحت في مسار واحد مترابط.',
  'Diagnose my readiness': 'حلّل جاهزيتي',
  'Continue today’s step': 'أكمل خطوة اليوم',
  'Start role-based practice': 'ابدأ تدريبًا للوظيفة',
  'RECOMMENDED NEXT': 'الخطوة المقترحة',
  'Set your target role': 'حدد الوظيفة المستهدفة',
  'A target lets Wazzefni measure actual gaps instead of giving generic advice.': 'تحديد الوظيفة يساعد وظّفني على قياس الفجوات الحقيقية بدلًا من تقديم نصائح عامة.',
  'Open': 'فتح',
  'Development tools': 'أدوات التطوير',
  'Readiness diagnosis': 'تشخيص الجاهزية',
  'See what is proven, missing, and realistic for your target role.': 'اعرف ما تم إثباته وما ينقصك وما هو واقعي لوظيفتك المستهدفة.',
  'Start here': 'ابدأ من هنا',
  'Qualification plan': 'خطة التأهيل',
  'Work through the smallest useful tasks that close real evidence gaps.': 'أنجز أصغر المهام المفيدة التي تسد فجوات الأدلة الحقيقية.',
  'Built after diagnosis': 'تُبنى بعد التشخيص',
  'Skill proof': 'إثبات المهارة',
  'Show reasoning and inspectable work before a skill is added to your CV.': 'اعرض طريقة تفكيرك وعملًا يمكن مراجعته قبل إضافة المهارة إلى سيرتك.',
  'Opened from a plan task': 'يُفتح من مهمة في الخطة',
  'Interview practice': 'تدريب المقابلات',
  'Practice for the role using only your confirmed experience and evidence.': 'تدرّب للوظيفة باستخدام خبرتك وأدلتك المؤكدة فقط.',
  'Part of your development path': 'جزء من مسار تطويرك',
  'Need market context?': 'تحتاج صورة أوضح عن السوق؟',
  'Research demand, training, and role signals without leaving your development path.': 'ابحث عن الطلب والتدريب وإشارات الوظائف من داخل مسار تطويرك.',
  'Open market research': 'فتح بحث السوق',

  // Settings and account
  'Account': 'الحساب',
  'Preferences': 'التفضيلات',
  'Workspace & AI': 'مساحة العمل والذكاء الاصطناعي',
  'Private workspace': 'مساحة خاصة',
  'Settings sections': 'أقسام الإعدادات',
  'Sign out': 'تسجيل الخروج',
  'ACCOUNT': 'الحساب',
  'Profile and identity': 'الملف الشخصي والهوية',
  'This information personalizes the workspace. It is never invented from application data.': 'تُستخدم هذه المعلومات لتخصيص مساحة العمل، ولا يتم استنتاجها من بيانات التقديم.',
  'Profile photo': 'الصورة الشخصية',
  'PNG, JPG, or WebP. Maximum 5 MB.': 'PNG أو JPG أو WebP بحد أقصى 5 ميجابايت.',
  'Uploading…': 'جارٍ الرفع…',
  'Upload photo': 'رفع صورة',
  'Remove': 'إزالة',
  'Display name': 'الاسم المعروض',
  'Your name': 'اسمك',
  'Email address': 'البريد الإلكتروني',
  'Professional headline': 'المسمى المهني',
  'e.g. Product designer': 'مثال: مصمم منتجات',
  'Phone number': 'رقم الهاتف',
  'City, country': 'المدينة، الدولة',
  'Time zone': 'المنطقة الزمنية',
  'Used for interview reminders and follow-up timing.': 'تُستخدم لمواعيد تذكير المقابلات والمتابعة.',
  'Short bio': 'نبذة قصيرة',
  'A concise summary used to personalize recommendations.': 'ملخص موجز يُستخدم لتخصيص التوصيات.',
  'What should Wazzefni know about your goals and experience?': 'ما الذي ينبغي أن يعرفه وظّفني عن أهدافك وخبرتك؟',
  'Changes saved': 'تم حفظ التغييرات',
  'Saving…': 'جارٍ الحفظ…',
  'Save changes': 'حفظ التغييرات',
  'PREFERENCES': 'التفضيلات',
  'Search defaults': 'إعدادات البحث الافتراضية',
  'Set stable defaults once. You can still override them for any individual search.': 'حدد الإعدادات الافتراضية مرة واحدة، ويمكنك تغييرها لأي عملية بحث.',
  'Default location': 'الموقع الافتراضي',
  'City, country, or Remote': 'مدينة أو دولة أو عن بُعد',
  'Market': 'السوق',
  'Egypt': 'مصر',
  'Saudi Arabia': 'السعودية',
  'United Arab Emirates': 'الإمارات العربية المتحدة',
  'Prioritize remote roles': 'أولوية للوظائف عن بُعد',
  'Ranks remote opportunities first without hiding strong local matches.': 'يرتب فرص العمل عن بُعد أولًا دون إخفاء الفرص المحلية القوية.',
  'Save preferences': 'حفظ التفضيلات',
  'LANGUAGE': 'اللغة',
  'Interface language': 'لغة الواجهة',
  'Changes labels and reading direction across the product.': 'تغيّر كل النصوص واتجاه القراءة في المنتج.',
  'English': 'الإنجليزية',
  'Arabic': 'العربية',
  'NOTIFICATIONS': 'الإشعارات',
  'Only the updates that matter': 'التحديثات المهمة فقط',
  'Wazzefni stays quiet unless a status changes or your action is required.': 'يبقى وظّفني هادئًا ما لم تتغير حالة أو يُطلب منك إجراء.',
  'Application updates': 'تحديثات التقديم',
  'Replies, status changes, and forms that need input.': 'الردود وتغيرات الحالة والنماذج التي تحتاج تدخلك.',
  'Interview reminders': 'تذكيرات المقابلات',
  'Reminders before scheduled interviews and preparation sessions.': 'تذكيرات قبل المقابلات وجلسات التحضير المجدولة.',
  'Weekly progress digest': 'ملخص التقدم الأسبوعي',
  'A concise summary of applications, conversion, and next actions.': 'ملخص موجز لطلبات التقديم والنتائج والخطوات التالية.',
  'WORKSPACE': 'مساحة العمل',
  'Appearance and runtime': 'المظهر ومحرك التشغيل',
  'Tune information density and the AI runtime without changing your underlying career data.': 'اضبط كثافة المعلومات ومحرك الذكاء الاصطناعي دون تغيير بياناتك المهنية.',
  'Information density': 'كثافة المعلومات',
  'Comfortable works best on touch devices. Compact fits more rows on larger screens.': 'الوضع المريح أفضل للمس، والمضغوط يعرض صفوفًا أكثر على الشاشات الكبيرة.',
  'Comfortable': 'مريح',
  'Compact': 'مضغوط',
  'AI runtime': 'محرك الذكاء الاصطناعي',
  'Configure': 'إعداد',
  'PRIVACY': 'الخصوصية',
  'Control stays with you': 'التحكم يظل بيدك',
  'External submission, messaging, calendar changes, and offer responses always require approval.': 'التقديم والمراسلة وتغييرات التقويم والرد على العروض تتطلب موافقتك دائمًا.',
  'Database-backed private account': 'حساب خاص مرتبط بقاعدة البيانات',
  'Passwords are hashed, sessions stay in an HttpOnly cookie, and profile data is isolated by your account ID.': 'كلمات المرور مشفرة، والجلسات محفوظة في ملفات HttpOnly، وبيانات ملفك معزولة بمعرّف حسابك.',

  // Authentication
  'About Wazzefni': 'عن وظّفني',
  'YOUR AI QUALIFICATION AGENT': 'مساعدك الذكي للتأهيل المهني',
  'Get ready for work, step by step.': 'تأهّل للعمل خطوة بخطوة.',
  'Diagnose what is missing, build proof, update your CV, then apply when the evidence is ready.': 'اكتشف ما ينقصك، وابنِ الدليل، وحدّث سيرتك، ثم قدّم عندما تصبح أدلتك جاهزة.',
  'A personal qualification to-do list': 'قائمة تأهيل مخصصة لك',
  'Skill proof before a CV claim': 'إثبات المهارة قبل إضافتها للسيرة',
  'Human approval before external actions': 'موافقتك قبل أي إجراء خارجي',
  'Your data stays in your workspace.': 'بياناتك تظل داخل مساحة عملك.',
  'Secure workspace': 'مساحة عمل آمنة',
  'Sign in to your workspace': 'سجّل الدخول إلى مساحة عملك',
  'Create your Wazzefni workspace': 'أنشئ مساحة عملك على وظّفني',
  'Reset your password': 'إعادة تعيين كلمة المرور',
  'Continue your qualification plan, skill proof, and applications in one place.': 'تابع خطة تأهيلك وإثبات مهاراتك وطلبات التقديم في مكان واحد.',
  'Start with a private workspace that keeps every career fact under your control.': 'ابدأ بمساحة خاصة تُبقي كل معلوماتك المهنية تحت سيطرتك.',
  'Enter your email to create a secure password-reset request.': 'أدخل بريدك لإنشاء طلب آمن لإعادة تعيين كلمة المرور.',
  'Back to sign in': 'العودة لتسجيل الدخول',
  'Recovery request recorded': 'تم تسجيل طلب الاستعادة',
  'If this email belongs to an account, its secure reset request is now active.': 'إذا كان البريد مرتبطًا بحساب، فقد تم تفعيل طلب الاستعادة الآمن.',
  'Full name': 'الاسم الكامل',
  'Password': 'كلمة المرور',
  'Use 8+ characters with a mix of letters and numbers.': 'استخدم 8 أحرف على الأقل مع حروف وأرقام.',
  'Enter your password': 'أدخل كلمة المرور',
  'Hide password': 'إخفاء كلمة المرور',
  'Show password': 'إظهار كلمة المرور',
  'Keep me signed in': 'إبقائي مسجلًا',
  'Forgot password?': 'نسيت كلمة المرور؟',
  'Opening workspace…': 'جارٍ فتح مساحة العمل…',
  'Sign in': 'تسجيل الدخول',
  'Create workspace': 'إنشاء مساحة العمل',
  'Send recovery link': 'إرسال رابط الاستعادة',
  'New to Wazzefni?': 'جديد على وظّفني؟',
  'Already have a workspace?': 'لديك مساحة عمل بالفعل؟',
  'Create an account': 'إنشاء حساب',
  'By continuing, you agree to the Terms and acknowledge the Privacy Policy.': 'بالمتابعة، أنت توافق على الشروط وتقر بسياسة الخصوصية.',
  'Enter a valid email address.': 'أدخل بريدًا إلكترونيًا صحيحًا.',
  'Enter the name you want shown in Wazzefni.': 'أدخل الاسم الذي تريد عرضه في وظّفني.',
  'Use at least 8 characters with a letter and a number.': 'استخدم 8 أحرف على الأقل تتضمن حرفًا ورقمًا.',
  'Could not open the workspace.': 'تعذر فتح مساحة العمل.',

  // CV builder, application assistant, and career questions
  'What is your name, email, phone, city, and LinkedIn/GitHub link?': 'ما اسمك وبريدك ورقم هاتفك ومدينتك ورابط LinkedIn أو GitHub؟',
  'A full name and at least one email or phone number are required.': 'يلزم الاسم الكامل وبريد إلكتروني أو رقم هاتف واحد على الأقل.',
  'What role or internship are you targeting, and are you currently a student?': 'ما الوظيفة أو التدريب الذي تستهدفه؟ وهل أنت طالب حاليًا؟',
  'Include your current career stage so internships and graduate roles can be prioritised.': 'اذكر مرحلتك المهنية الحالية لترتيب فرص التدريب ووظائف الخريجين.',
  'Tell me about work, freelance experience, volunteering, or internships.': 'حدثنا عن خبراتك في العمل أو العمل الحر أو التطوع أو التدريب.',
  'This can be empty if you have strong projects and education.': 'يمكن ترك هذا فارغًا إذا كانت لديك مشاريع وتعليم قويان.',
  'What are your best technical or non-technical projects?': 'ما أفضل مشاريعك التقنية أو غير التقنية؟',
  'State the problem, what you did, tools used, and the factual result.': 'اذكر المشكلة وما نفذته والأدوات المستخدمة والنتيجة الفعلية.',
  'Which skills and tools can you genuinely use?': 'ما المهارات والأدوات التي يمكنك استخدامها فعليًا؟',
  'Add at least three comma-separated skills.': 'أضف ثلاث مهارات على الأقل مفصولة بفواصل.',
  'What education, graduation date, certificates, languages, or achievements should be included?': 'ما التعليم وتاريخ التخرج والشهادات واللغات والإنجازات التي ينبغي إضافتها؟',
  'Current education matters, especially when you are a student.': 'التعليم الحالي مهم، خصوصًا إذا كنت طالبًا.',
  'Upload a CV or create an ATS CV first.': 'ارفع سيرة ذاتية أو أنشئ سيرة متوافقة مع أنظمة التوظيف أولًا.',
  'Generated ATS CV': 'سيرة ذاتية مُنشأة ومتوافقة مع أنظمة التوظيف',
  'ATS CV ready': 'السيرة المتوافقة جاهزة',
  'Close CV builder': 'إغلاق منشئ السيرة الذاتية',
  'ATS PDF READY': 'ملف السيرة PDF جاهز',
  'Your CV is ready to review.': 'سيرتك الذاتية جاهزة للمراجعة.',
  'Only facts from your answers were used.': 'تم استخدام الحقائق الواردة في إجاباتك فقط.',
  'Download PDF': 'تحميل PDF',
  'Use for search': 'استخدامها في البحث',
  'ATS CV builder': 'منشئ سيرة ذاتية متوافقة مع أنظمة التوظيف',
  'VERIFIED': 'تم التحقق',
  'Write factual information here...': 'اكتب معلومات حقيقية هنا...',
  'Back': 'السابق',
  'Next': 'التالي',
  'Building ATS PDF...': 'جارٍ إنشاء ملف PDF...',
  'Generate ATS PDF': 'إنشاء ملف PDF',
  'One useful question': 'سؤال واحد مفيد',
  'This helps us find more relevant opportunities for you.': 'يساعدنا هذا في العثور على فرص أكثر ملاءمة لك.',
  'Type your answer': 'اكتب إجابتك',
  'Save and continue': 'حفظ ومتابعة',
  'I already have enough information for the next application.': 'لدينا بالفعل معلومات كافية لطلب التقديم التالي.',
  'Answer once': 'أجب مرة واحدة',
  'View plan': 'عرض الخطة',
  'Application Assistant': 'مساعد التقديم',
  'All set to submit.': 'كل شيء جاهز للتقديم.',
  'You’re in control. You can review everything below before submitting. We’ll handle the rest.': 'التحكم بيدك. يمكنك مراجعة كل شيء قبل الإرسال وسنتولى الباقي.',
  'Find job': 'البحث عن وظيفة',
  'Fill application': 'ملء الطلب',
  'Review': 'مراجعة',
  'Ready to submit': 'جاهز للإرسال',
  'Everything looks good! You can now submit your application.': 'كل شيء يبدو جيدًا. يمكنك الآن إرسال طلبك.',
  'CV uploaded': 'تم رفع السيرة',
  'Yes': 'نعم',
  'No': 'لا',
  'Fields filled': 'الحقول المكتملة',
  'Saved answers reused': 'إجابات محفوظة أُعيد استخدامها',
  'Missing question answered': 'تمت الإجابة عن السؤال الناقص',
  'We filled in your work authorization based on your saved profile.': 'تم ملء تصريح العمل بناءً على ملفك المحفوظ.',
  'There might be one extra step': 'قد توجد خطوة إضافية',
  'Some companies may show an additional step, like a CAPTCHA or a login screen. We’ll pause the flow for you to complete it, then continue automatically.': 'قد تعرض بعض الشركات خطوة إضافية مثل CAPTCHA أو تسجيل الدخول. سنوقف المسار لتكملها ثم نتابع تلقائيًا.',
  'Review answers': 'مراجعة الإجابات',
  'Closing...': 'جارٍ الإغلاق...',
  'Close browser': 'إغلاق المتصفح',
  'Submitting...': 'جارٍ الإرسال...',
  'Confirm submit': 'تأكيد الإرسال',
  'Continuing...': 'جارٍ المتابعة...',
  'Save answers & continue': 'حفظ الإجابات والمتابعة',
  'Retrying...': 'جارٍ إعادة المحاولة...',
  'Retry after review': 'إعادة المحاولة بعد المراجعة',
  'Restoring...': 'جارٍ الاستعادة...',
  'Resume saved session': 'استكمال الجلسة المحفوظة',
  'Choose an answer': 'اختر إجابة',
  'Application draft': 'مسودة التقديم',
  'Close application draft': 'إغلاق مسودة التقديم',
  'APPLICATION DRAFT': 'مسودة التقديم',
  'Copy draft': 'نسخ المسودة',
  'Open listing': 'فتح الإعلان',

  // Employment operating system
  'Prepare': 'التحضير',
  'Applied': 'تم التقديم',
  'Interview': 'مقابلة',
  'Decision': 'القرار',
  'Ready to apply': 'جاهز للتقديم',
  'Needs input': 'يحتاج معلومات',
  'Recruiter replied': 'رد مسؤول التوظيف',
  'Final interview': 'المقابلة النهائية',
  'On hold': 'معلّق',
  'Loading workspace…': 'جارٍ تحميل مساحة العمل…',
  "Building today's priorities…": 'جارٍ ترتيب أولويات اليوم…',
  'Employment agent': 'مساعد التوظيف',
  'Evidence-led': 'مبني على الأدلة',
  'YOUR STEP TODAY · QUALIFICATION': 'خطوتك اليوم · التأهيل',
  'Open task': 'فتح المهمة',
  'NEXT BEST ACTION': 'أفضل خطوة تالية',
  'Snooze': 'تأجيل',
  'Mark done': 'تحديد كمكتمل',
  'Recommendation feedback': 'تقييم التوصية',
  'Was this useful?': 'هل كان هذا مفيدًا؟',
  'Useful': 'مفيد',
  'Wrong': 'غير صحيح',
  'Already done': 'تم بالفعل',
  'Not relevant': 'غير مناسب',
  'Choose the role you want to reach.': 'حدد الوظيفة التي تريد الوصول إليها.',
  'Start with a readiness diagnosis, then Wazzefni will choose one useful qualification or application move.': 'ابدأ بتشخيص الجاهزية، ثم سيختار وظّفني خطوة تأهيل أو تقديم مفيدة.',
  'Diagnose readiness': 'تحليل الجاهزية',
  'NEEDS YOUR APPROVAL': 'تحتاج موافقتك',
  'Approve': 'موافقة',
  'Loading application history…': 'جارٍ تحميل سجل التقديم…',
  'No applications tracked yet.': 'لا توجد طلبات تقديم مسجلة بعد.',
  'Start an application from Opportunities. Wazzefni will preserve every status, CV, answer, and outcome here.': 'ابدأ التقديم من صفحة الفرص، وسيحتفظ وظّفني هنا بكل حالة وسيرة وإجابة ونتيجة.',
  'Company not stated': 'الشركة غير مذكورة',
  'Location not stated': 'الموقع غير مذكور',
  'APPLICATION RECORD': 'سجل التقديم',
  'Current status': 'الحالة الحالية',
  'Drafting…': 'جارٍ إعداد المسودة…',
  'Draft follow-up': 'إعداد رسالة متابعة',
  'REVIEW BEFORE SENDING': 'راجع قبل الإرسال',
  'A pending approval was created. Nothing was sent.': 'تم إنشاء موافقة معلقة، ولم يتم إرسال أي شيء.',
  'TIMELINE': 'التسلسل الزمني',
  'PRACTICE HISTORY': 'سجل التدريب',
  'Interview sessions': 'جلسات المقابلات',
  'Practice session': 'جلسة تدريب',
  'NEW MOCK INTERVIEW': 'مقابلة تدريبية جديدة',
  'Practice against the actual role.': 'تدرّب للوظيفة الفعلية.',
  'Questions use the selected application and confirmed evidence. Feedback never infers emotion or personality.': 'تستخدم الأسئلة طلب التقديم المحدد والأدلة المؤكدة، ولا تستنتج الملاحظات مشاعرك أو شخصيتك.',
  'Application': 'طلب التقديم',
  'General practice': 'تدريب عام',
  'Interview type': 'نوع المقابلة',
  'Language': 'اللغة',
  'العربية': 'العربية',
  'Building plan…': 'جارٍ بناء الخطة…',
  'Build interview plan': 'إنشاء خطة المقابلة',
  'Opening interview session…': 'جارٍ فتح جلسة المقابلة…',
  'Session complete': 'اكتملت الجلسة',
  'Read aloud': 'قراءة بصوت عالٍ',
  'Type your answer or record it…': 'اكتب إجابتك أو سجّلها صوتيًا…',
  'Stop recording': 'إيقاف التسجيل',
  'Record answer': 'تسجيل الإجابة',
  'words': 'كلمة',
  'Evaluating…': 'جارٍ التقييم…',
  'Submit answer': 'إرسال الإجابة',
  'Practice complete.': 'اكتمل التدريب.',
  'Review the feedback below, then repeat the session to measure improvement.': 'راجع الملاحظات أدناه، ثم كرر الجلسة لقياس التحسن.',
  'ANSWER FEEDBACK': 'ملاحظات الإجابة',
  'Specific improvements': 'تحسينات محددة',
  'Working well': 'نقاط جيدة',
  'Improve next': 'التحسين التالي',
  'DECISION WORKSPACE': 'مساحة القرار',
  'Compare the full offer, not just salary.': 'قارن العرض كاملًا، وليس الراتب فقط.',
  'Wazzefni keeps stated facts separate from assumptions and never sends a response without approval.': 'يفصل وظّفني الحقائق المذكورة عن الافتراضات، ولا يرسل ردًا دون موافقتك.',
  'Add offer': 'إضافة عرض',
  'No offers recorded yet.': 'لا توجد عروض مسجلة بعد.',
  'When an offer arrives, capture its terms here to compare, clarify, and negotiate with evidence.': 'عند وصول عرض، سجل شروطه هنا للمقارنة والاستفسار والتفاوض بالأدلة.',
  'Record an offer': 'تسجيل عرض',
  'Compare': 'مقارنة',
  'Compensation not stated': 'التعويض غير مذكور',
  'Clarify': 'استفسار',
  'Negotiate': 'تفاوض',
  'Comparing…': 'جارٍ المقارنة…',
  'SIDE-BY-SIDE': 'مقارنة مباشرة',
  'Comparable stated terms': 'شروط معلنة قابلة للمقارنة',
  'Comparison needs one more fact': 'المقارنة تحتاج معلومة إضافية',
  'Not comparable': 'غير قابل للمقارنة',
  'A pending approval was created. Nothing was sent automatically.': 'تم إنشاء موافقة معلقة، ولم يُرسل أي شيء تلقائيًا.',
  'RECORD OFFER': 'تسجيل العرض',
  'Capture only stated terms.': 'سجل الشروط المذكورة فقط.',
  'Related application': 'طلب التقديم المرتبط',
  'Choose application': 'اختر طلب تقديم',
  'Company': 'الشركة',
  'Role': 'الوظيفة',
  'Base salary': 'الراتب الأساسي',
  'Currency': 'العملة',
  'Period': 'الفترة',
  'Save offer': 'حفظ العرض',
  'TRUSTED CAREER MEMORY': 'الذاكرة المهنية الموثوقة',
  'Your facts power every agent.': 'حقائقك تدعم كل مساعد.',
  'Wazzefni can reuse confirmed facts. It never converts a preference or AI guess into a CV claim.': 'يمكن لوظّفني إعادة استخدام الحقائق المؤكدة، ولا يحول تفضيلًا أو تخمينًا إلى معلومة في سيرتك.',
  'CONFIRMED FACTS': 'حقائق مؤكدة',
  'Reusable evidence': 'أدلة قابلة لإعادة الاستخدام',
  'CV safe': 'آمن للسيرة',
  'Fact name, e.g. notice period': 'اسم المعلومة، مثل مدة الإشعار',
  'Confirmed answer': 'إجابة مؤكدة',
  'Add fact': 'إضافة معلومة',
  'CONNECTED WORKFLOW': 'الخدمات المتصلة',
  'Email, calendar, and Telegram': 'البريد والتقويم وتليجرام',
  'Tokens stay in the operating system keyring. External messages still require approval.': 'تظل الرموز محفوظة في مخزن النظام الآمن، وتحتاج الرسائل الخارجية إلى موافقتك.',
  'Connected': 'متصل',
  'Not connected': 'غير متصل',
  'Update': 'تحديث',
  'Connect': 'اتصال',
  'Sync': 'مزامنة',
  'Human approval stays on': 'موافقتك مطلوبة دائمًا',
  'Submission, sending, calendar changes, and offer responses cannot bypass the approval layer.': 'لا يمكن للتقديم أو الإرسال أو تغييرات التقويم أو الرد على العروض تجاوز طبقة الموافقة.',
  'TELEGRAM CONTROL': 'إعداد تليجرام',
  'Connect your private bot.': 'اربط بوتك الخاص.',
  'Use BotFather to create a bot, then provide the token and your chat ID. The token is stored in the OS keyring.': 'استخدم BotFather لإنشاء بوت، ثم أدخل الرمز ومعرّف المحادثة. يُحفظ الرمز في مخزن النظام الآمن.',
  'Bot token': 'رمز البوت',
  'Chat ID': 'معرّف المحادثة',
  'Connecting…': 'جارٍ الاتصال…',
  'Connect Telegram': 'ربط تليجرام',

  // Common operational UI
  'Ready': 'جاهز',
  'Local and ready': 'محلي وجاهز',
  'Cloud ready': 'السحابة جاهزة',
  'Offline': 'غير متصل',
  'Open application pipeline': 'فتح مسار التقديم',
  'Build the first qualified application.': 'أنشئ أول طلب تقديم مؤهل.',
  'QUEUE': 'قائمة الانتظار',
  'After the first move': 'بعد الخطوة الأولى',
  'pending': 'قيد الانتظار',
  'The queue updates from real application events, not generic career advice.': 'تتحدث القائمة من أحداث التقديم الفعلية، لا من نصائح عامة.',
  'FUNNEL': 'مسار النتائج',
  'What is converting': 'ما الذي يحقق نتيجة',
  'applied': 'تم التقديم',
  'replies': 'ردود',
  'interviews': 'مقابلات',
  'offers': 'عروض',
  'No saved roles yet.': 'لا توجد وظائف محفوظة بعد.',
  'Save an opportunity and it will appear here.': 'احفظ فرصة وستظهر هنا.',
  'Browse opportunities': 'تصفح الفرص',
  'Recently saved': 'المحفوظة حديثًا',
}

const textOriginals = new WeakMap<Text, string>()
const attributeOriginals = new WeakMap<Element, Map<string, string>>()
const translatedValues = new Set(Object.values(ar))
const translatedAttributes = ['placeholder', 'aria-label', 'title', 'alt']

export function getLocale(): Locale {
  const stored = localStorage.getItem(STORAGE_KEY) || localStorage.getItem('jobflow-locale')
  return stored === 'ar' ? 'ar' : 'en'
}

export function translateText(value: string, locale: Locale): string {
  if (locale === 'en') return value
  const direct = ar[value]
  if (direct) return direct
  const patterns: Array<[RegExp, (...groups: string[]) => string]> = [
    [/^(\d+) roles$/, count => `${count} وظائف`],
    [/^(\d+) role$/, count => `${count} وظيفة`],
    [/^(\d+) pending$/, count => `${count} قيد الانتظار`],
    [/^(\d+) current listings checked$/, count => `تمت مراجعة ${count} إعلانًا حاليًا`],
    [/^Showing (\d+) of (\d+) matched roles · (\d+) listings checked$/, (shown, total, checked) => `عرض ${shown} من ${total} وظائف مطابقة · تمت مراجعة ${checked} إعلانًا`],
    [/^Found (\d+) current roles$/, count => `تم العثور على ${count} وظيفة حالية`],
    [/^Found (\d+) current role$/, count => `تم العثور على وظيفة حالية واحدة`],
    [/^Matched (\d+) roles to your CV$/, count => `تمت مطابقة ${count} وظائف مع سيرتك الذاتية`],
    [/^Screened down to (\d+) relevant listings$/, count => `تمت تصفية النتائج إلى ${count} إعلانات مناسبة`],
    [/^(\d+)% match$/, count => `تطابق ${count}%`],
  ]
  for (const [pattern, formatter] of patterns) {
    const match = value.match(pattern)
    if (match) return formatter(...match.slice(1))
  }
  return value
}

function replacePreservingSpace(value: string, translated: string): string {
  const start = value.match(/^\s*/)?.[0] || ''
  const end = value.match(/\s*$/)?.[0] || ''
  return `${start}${translated}${end}`
}

function localizeTextNode(node: Text, locale: Locale) {
  const current = node.nodeValue || ''
  const clean = current.trim()
  if (!clean) return
  if (locale === 'en') {
    const original = textOriginals.get(node)
    if (original !== undefined && current !== original) node.nodeValue = original
    return
  }
  if (translatedValues.has(clean)) return
  const translated = translateText(clean, locale)
  if (translated === clean) return
  textOriginals.set(node, current)
  node.nodeValue = replacePreservingSpace(current, translated)
}

function localizeElement(element: Element, locale: Locale) {
  for (const attribute of translatedAttributes) {
    const current = element.getAttribute(attribute)
    if (!current) continue
    let originals = attributeOriginals.get(element)
    if (!originals) { originals = new Map(); attributeOriginals.set(element, originals) }
    if (locale === 'en') {
      const original = originals.get(attribute)
      if (original !== undefined && current !== original) element.setAttribute(attribute, original)
      continue
    }
    if (translatedValues.has(current)) continue
    const translated = translateText(current, locale)
    if (translated !== current) { originals.set(attribute, current); element.setAttribute(attribute, translated) }
  }
}

function localizeTree(root: Node, locale: Locale) {
  if (root.nodeType === Node.TEXT_NODE) { localizeTextNode(root as Text, locale); return }
  if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) return
  if (root.nodeType === Node.ELEMENT_NODE) localizeElement(root as Element, locale)
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    if (node.nodeType === Node.TEXT_NODE) localizeTextNode(node as Text, locale)
    else localizeElement(node as Element, locale)
    node = walker.nextNode()
  }
}

type I18nContextValue = {
  locale: Locale
  setLocale: (locale: Locale) => void
  t: (value: string) => string
}

const I18nContext = createContext<I18nContextValue | null>(null)

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(getLocale)

  useLayoutEffect(() => {
    document.documentElement.lang = locale
    document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
    document.title = locale === 'ar' ? 'وظّفني' : 'Wazzefni'
    document.querySelector('meta[name="description"]')?.setAttribute(
      'content',
      locale === 'ar'
        ? 'وظّفني، مساعدك الذكي للتأهيل والتوظيف. نجهّزك للعمل خطوة بخطوة.'
        : 'Wazzefni, your AI qualification and employment agent. Get ready for work, step by step.',
    )
    localStorage.setItem(STORAGE_KEY, locale)
    const root = document.getElementById('root')
    if (!root) return
    localizeTree(root, locale)
    const observer = new MutationObserver(records => {
      observer.disconnect()
      records.forEach(record => {
        if (record.type === 'characterData') localizeTree(record.target, locale)
        record.addedNodes.forEach(node => localizeTree(node, locale))
      })
      observer.observe(root, { childList: true, subtree: true, characterData: true })
    })
    observer.observe(root, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [locale])

  const value = useMemo<I18nContextValue>(() => ({
    locale,
    setLocale: next => {
      document.documentElement.lang = next
      document.documentElement.dir = next === 'ar' ? 'rtl' : 'ltr'
      localStorage.setItem(STORAGE_KEY, next)
      setLocaleState(next)
      window.dispatchEvent(new CustomEvent(LOCALE_EVENT, { detail: next }))
    },
    t: value => translateText(value, locale),
  }), [locale])

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('useI18n must be used inside I18nProvider')
  return value
}
