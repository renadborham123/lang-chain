"""
تشغيل السيستم من الـ command line.

الاستخدام:
    python main.py --cv path/to/cv.pdf --user-id ahmed
    python main.py --cv path/to/cv.pdf --user-id ahmed --refresh-profile

أول مرة: هيقرأ الـ CV ويستخرج البروفايل ويحفظه في الـ memory.
المرات الجاية: مش لازم تدّي --cv تاني، هيستخدم البروفايل المحفوظ،
ويجيب بس الوظائف الجديدة اللي لسه ماشافهاش.
"""
import argparse
import sys
from pypdf import PdfReader

from graph import graph


def read_cv_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        reader = PdfReader(path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description="Job Matcher Agent")
    parser.add_argument("--user-id", required=True, help="معرف فريد للمستخدم (يُستخدم لحفظ الذاكرة)")
    parser.add_argument("--cv", help="مسار ملف الـ CV (PDF أو txt). مطلوب أول مرة فقط.")
    parser.add_argument("--refresh-profile", action="store_true",
                         help="أعد استخراج البروفايل من الـ CV حتى لو محفوظ من قبل")
    args = parser.parse_args()

    cv_text = ""
    if args.cv:
        cv_text = read_cv_text(args.cv)
    elif args.refresh_profile:
        print("لازم تدّي --cv لو عايز تعمل refresh للبروفايل.", file=sys.stderr)
        sys.exit(1)

    initial_state = {
        "user_id": args.user_id,
        "cv_text": cv_text,
        "refresh_profile": args.refresh_profile,
    }

    config = {"configurable": {"thread_id": args.user_id}}

    result = graph.invoke(initial_state, config=config)

    print(result["final_report"])


if __name__ == "__main__":
    main()
