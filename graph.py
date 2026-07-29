"""
تجميع الـ StateGraph:

extract_profile -> generate_queries -> search_jobs -> filter_new_jobs
                 -> match_keywords -> rank_and_format

- checkpointer (SqliteSaver): short-term memory -> بيفتكر آخر حالة للـ "thread"
  (مفيد لو حبيت تكمل نفس الجلسة أو تعمل retry من نص الطريق).
- memory_store (JobMatcherMemory): long-term memory -> بيفتكر البروفايل
  والوظائف اللي اتشافت قبل كده *عبر جلسات مختلفة تمامًا*.
"""
import os
import sqlite3

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver

from state import JobSearchState
from nodes import (
    extract_profile_node,
    generate_queries_node,
    search_jobs_node,
    filter_new_jobs_node,
    match_keywords_node,
    rank_and_format_node,
)


def build_graph():
    builder = StateGraph(JobSearchState)

    builder.add_node("extract_profile", extract_profile_node)
    builder.add_node("generate_queries", generate_queries_node)
    builder.add_node("search_jobs", search_jobs_node)
    builder.add_node("filter_new_jobs", filter_new_jobs_node)
    builder.add_node("match_keywords", match_keywords_node)
    builder.add_node("rank_and_format", rank_and_format_node)

    builder.add_edge(START, "extract_profile")
    builder.add_edge("extract_profile", "generate_queries")
    builder.add_edge("generate_queries", "search_jobs")
    builder.add_edge("search_jobs", "filter_new_jobs")
    builder.add_edge("filter_new_jobs", "match_keywords")
    builder.add_edge("match_keywords", "rank_and_format")
    builder.add_edge("rank_and_format", END)

    # short-term / thread-level memory (persisted على SQLite)
    checkpoint_path = "./memory/checkpoints.sqlite"
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    # from_conn_string() is a context manager in current LangGraph releases;
    # keep an explicit connection alive for this module-level compiled graph.
    connection = sqlite3.connect(checkpoint_path, check_same_thread=False, timeout=60)
    connection.execute("PRAGMA journal_mode=WAL")
    checkpointer = SqliteSaver(connection)

    return builder.compile(checkpointer=checkpointer)


graph = build_graph()
