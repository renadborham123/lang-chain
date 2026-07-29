"""
تشغيل دوري تلقائي (مثلاً: كل يوم الساعة 9 الصبح) بيبحث عن وظائف جديدة
ويطبعها (أو تقدر تعدّل send_report لتبعتها على إيميل/Slack/Telegram).

الاستخدام:
    python scheduler.py --user-id ahmed
(لازم يكون البروفايل محفوظ بالفعل من تشغيلة أولى بـ main.py --cv ...)
"""
import argparse
import time
import schedule  # pip install schedule

from graph import graph


def send_report(report: str, user_id: str):
    # TODO: استبدل ده بإرسال فعلي (Email / Slack / Telegram bot / إلخ)
    print(f"\n===== تقرير الوظائف لـ {user_id} =====")
    print(report)


def run_job(user_id: str):
    config = {"configurable": {"thread_id": user_id}}
    state = {"user_id": user_id, "cv_text": "", "refresh_profile": False}
    result = graph.invoke(state, config=config)
    send_report(result["final_report"], user_id)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--time", default="09:00", help="وقت التشغيل اليومي (HH:MM)")
    args = parser.parse_args()

    schedule.every().day.at(args.time).do(run_job, user_id=args.user_id)
    print(f"⏰ السيستم هيشتغل كل يوم الساعة {args.time} لصالح المستخدم {args.user_id}")

    # تشغيلة فورية أول مرة
    run_job(args.user_id)

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
